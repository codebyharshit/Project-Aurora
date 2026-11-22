"""Eval scorecard: re-find the known findings from the raw files, end to end.

Runs the real pipeline stages (tables, documents, planner, detectors, policy) on the customer's
data and checks the outcomes. Expected values live here, in the test, never in backend/aurora/.
Usage: cd backend && ../.venv/bin/python scripts/eval.py   (writes docs/EVAL.md)
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora.config import ROOT, get_tenant  # noqa: E402
from aurora.detectors import run_all  # noqa: E402
from aurora.planner import LaunchPlanner  # noqa: E402
from aurora.policy import PolicyEngine  # noqa: E402
from aurora.world import World  # noqa: E402

t = get_tenant()
w = World.load(t, read_documents=False)
planner = LaunchPlanner(w)
plan = planner.run()
policy = PolicyEngine.load(w)
signals = run_all(w, plan, policy.rules, planner.as_of)
led = plan["ledger"]
cond = plan["conditional"]
all_plan = LaunchPlanner(w).run(actions=[c["action_id"] for c in cond])
prods = {p["product_id"]: p for p in plan["products"]}
prods_all = {p["product_id"]: p for p in all_plan["products"]}
day_one = {r["product_id"]: float(r["day_one_qty"] or 0) for r in w.t("products").to_dict("records")}


def entry(kind, part, pred=lambda e: True):
    return next((e for e in led if e["kind"] == kind and e["part_id"] == part and pred(e)), None)


def pct_launch(pid, built):
    p = prods[pid]
    return 100 * (day_one[pid] - p["remaining"] + built) / day_one[pid]


checks = []


def check(name, ok, detail, how):
    checks.append((name, bool(ok), detail, how))


e = entry("receipt_correction", "CMP-GAM-008")
check("Art book receipt 80,000 vs delivery note 8,000", e and e["system_value"] == 80000 and e["truth_value"] == 8000,
      e["reason"] if e else "not found", "Document Reader read the handwritten correction; contradiction rule vs goods receipt")
e = entry("rejected_lot", "CMP-GAM-010")
check("Rejected statue lot counted as usable", e and abs(e["qty"]) == 5600, e["reason"] if e else "not found",
      "Inspection report (reject) matched to a stock batch")
s = next((s for s in signals if s.type == "qualification_expired"), None)
check("Supplier conditional release expired", s is not None, s.summary if s else "not found",
      "Policy (90 days, parsed from PP-07) + supplier profile")
e = entry("short_shipment", "CMP-GAM-001")
check("Short shipment 28,000 of 48,000 game cards", e and e["truth_value"] == 28000, e["reason"] if e else "not found",
      "Korean shipping advice matched to the air shipment by reference")
c = next((c for c in cond if c["kind"] == "collect_at_port"), None)
check("Container arrived at port, not collected", c is not None, c["title"] if c else "not found",
      "Shipment status + last update older than threshold")
e = entry("banned_revision", "CMP-GAM-004", lambda e: e["qty"] < 0)
check("Banned sleeve revision in stock (rev B)", e and abs(e["qty"]) == 64000, e["reason"] if e else "not found",
      "ECN (use_up_old_rev=N) + batch → receipt → PO → order confirmation revision")
e = entry("receipt_remark", "CMP-GAM-004")
check("Wrong-part pallet found in a free-text remark", e and abs(e["qty"]) == 4000, e["reason"] if e else "not found",
      "Remark Reader (AI) on warehouse remarks")
check("Magnet alarm is not a shortage", "CMP-MAG-005" not in plan["supply_truth"],
      "supplier-fitted component excluded from requirements", "Order confirmation states magnets are fitted by the supplier")
c = next((c for c in cond if c["kind"] == "accept_offer" and c["part_id"] == "CMP-GAM-008"), None)
check("Supplier rush offer found as an option", c and c["qty"] == 8000, c["title"] if c else "not found",
      "Polish offer read; 4 h loading + 9 h transport from the document")
s = next((s for s in signals if s.type == "receipt_without_po"), None)
check("Goods received without a purchase order", s and s.facts.get("qty") == 78000, s.summary if s else "not found",
      "Receipts without PO / part outside the BOM")
novel = [s for s in signals if s.type.startswith("novel")]
check("New kinds of problems surfaced (not pre-defined)", len(novel) >= 2,
      "; ".join(s.title[:70] for s in novel[:4]), "AI risk triage over all documents + news")
ce, std = "FG-GH6-CE", "FG-GH6-STD"
check("ERP view says fine, reality says short", prods[ce]["system_buildable"] == prods[ce]["remaining"]
      and prods[ce]["truth_buildable"] < prods[ce]["remaining"],
      f"Collector's ERP {prods[ce]['system_buildable']:,} vs reality {prods[ce]['truth_buildable']:,} of {prods[ce]['remaining']:,}",
      "Truth ledger applied to the ERP picture")
check("With the recommended actions: Collector's 100%, Standard ≥ 98.5% of launch",
      prods_all[ce]["truth_buildable"] == prods[ce]["remaining"] and pct_launch(std, prods_all[std]["truth_buildable"]) >= 98.5,
      f"Collector's {prods_all[ce]['truth_buildable']:,}/{prods[ce]['remaining']:,}; Standard "
      f"{pct_launch(std, prods_all[std]['truth_buildable']):.1f}% of launch", "What-if over all conditional supply")
a = policy.approver_for("purchase", planner.as_of, 16800, "Print & Packaging").approvers[0]
check("€16,800 purchase → Buyer Print & Packaging", a.person == "Paul Winter", f"{a.person} ({a.role})", "Approval limits parsed from PP-07")
ch = policy.approver_for("concession", planner.as_of, category="Collector's Items",
                         required_roles=["Supplier Quality Lead", "Category Lead"])
names = [x.person for x in ch.approvers]
check("Vacant Category Lead → documented stand-in", "Dr. Maren Vogt" in names and "Daniel Okafor" in names,
      f"{names}; {ch.notes[:1]}", "Org chart v2 start date + exception rule")
a = policy.approver_for("dock_slot", planner.as_of, site="DC-HAM").approvers[0]
check("Dock slot → site lead", a.person == "Katrin Jansen", a.person, "Receiving-site rule in PP-07")

# business-use-case agents added overnight
oc = [s for s in signals if s.type == "confirmation_mismatch"]
rev = next((s for s in oc if s.entities.get("kind") == "revision"), None)
check("Order Confirmation Agent: banned revision confirmed by a supplier", rev is not None, rev.title if rev else "not found",
      "Supplier confirmation lines vs PO + ECN (use_up_old_rev=N)")
unc = next((s for s in signals if s.type == "po_unconfirmed"), None)
check("Order Confirmation Agent: order due soon never confirmed", unc is not None, unc.summary[:140] if unc else "not found",
      "Open PO lines due within 14 days with no confirmation document")
tc = next((s for s in signals if s.type == "tracking_contradiction"), None)
check("Tracking Agent: tracker contradicts the ERP", tc is not None, tc.summary[:140] if tc else "not found",
      "ERP shipment status vs the learned spreadsheet tracker")
own = {s.type: s.facts.get("owner_person") or s.facts.get("owner_role") for s in signals}
check("Work routed to the people the data names (buyer / logistics)", own.get("tracking_contradiction") == "Logistics Planner"
      and bool(own.get("po_unconfirmed")), f"tracking → {own.get('tracking_contradiction')}, unconfirmed PO → {own.get('po_unconfirmed')}",
      "PO buyer field and the Logistics Planner role from the org chart")

# no customer-specific literals in the product code
pat = r"45003\d{5}|50004\d{5}|CMP-GAM|SUP-00\d\d|NHSU|NHMU|020-4811|Paul Winter|Maren|Katrin|Karton|Hwaseong|PackRight"
hits = subprocess.run(["grep", "-rnE", pat, str(ROOT / "backend" / "aurora"), "--include=*.py"],
                      capture_output=True, text=True).stdout.strip().splitlines()
hits = [h for h in hits if "/tests/" not in h]
check("No customer-specific values in backend/aurora/", not hits, f"{len(hits)} hits" + (": " + hits[0][:120] if hits else ""),
      "grep for PO/batch/part/supplier ids and names")

passed = sum(ok for _, ok, _, _ in checks)
lines = [f"# Eval scorecard · {t.cfg['display_name']}", "",
         f"Run {datetime.now():%Y-%m-%d %H:%M} on {len(w.documents)} documents. **{passed}/{len(checks)} passed.**", "",
         "| # | Check | Result | Found | How |", "|---|---|---|---|---|"]
for i, (name, ok, detail, how) in enumerate(checks, 1):
    lines.append(f"| {i} | {name} | {'✅' if ok else '❌'} | {str(detail).replace('|', '/')[:160]} | {how} |")
out = "\n".join(lines) + "\n"
(ROOT / "docs" / "EVAL.md").write_text(out)
print(out)
sys.exit(0 if passed == len(checks) else 1)
