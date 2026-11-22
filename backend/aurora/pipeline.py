"""Orchestrator: data → world → plan → signals → cases with options, impact and approvers.

Idempotent: re-running without new data updates cases in place (by signal fingerprint) and
never overwrites a human decision.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta

import yaml

from aurora.config import ROOT, Tenant, get_tenant
from aurora.detectors import Signal, run_all
from aurora.planner import LaunchPlanner
from aurora.policy import PolicyEngine
from aurora.store import Store
from aurora.world import World

LIBRARY = ROOT / "backend" / "aurora" / "playbooks" / "library.yaml"


def load_playbooks() -> dict[str, dict]:
    return {p["signal_type"]: p for p in yaml.safe_load(LIBRARY.read_text())}


def learned_playbooks(tenant: Tenant) -> list[dict]:
    """Playbooks created from human decisions on new kinds of problems."""
    f = ROOT / "tenants" / tenant.name / "playbooks_learned.yaml"
    return yaml.safe_load(f.read_text()) or [] if f.exists() else []


def match_learned(tenant: Tenant, sig: Signal) -> dict | None:
    text = " ".join([sig.title, sig.summary] + [f.get("raw", "") for f in sig.facts.get("findings", [])]).lower()
    best = None
    for pb in learned_playbooks(tenant):
        hits = sum(1 for k in pb.get("trigger_keywords", []) if k.lower() in text)
        if hits >= 2 and (not best or hits > best[0]):
            best = (hits, pb)
    return best[1] if best else None


def _eur(world: World, qty: float, part: str, supplier_hint: str | None, price_note: str = "") -> float | None:
    """Estimate cost from the supplier's list price (+ any surcharge stated in the offer)."""
    sp = world.t("supplier_parts")
    rows = sp[sp["part_id"] == part]
    if "_mapped_by" in rows.columns:   # prefer the configured supplier price over learned price lists
        rows = rows.assign(_learned=rows["_mapped_by"].notna()).sort_values("_learned")
    if supplier_hint:
        hit = rows[rows["supplier_id"].map(lambda s: world.supplier_name(s).split()[0].lower() in supplier_hint.lower())]
        rows = hit if len(hit) else rows
    if rows.empty:
        return None
    r = rows.iloc[0]
    fx = world.tenant.cfg.get("fx_to_eur", {}).get(r["currency"], 1.0)
    surcharge = 1.0
    m = re.search(r"\+\s*(\d+(?:[.,]\d+)?)\s*%", price_note or "")
    if m:
        surcharge += float(m.group(1).replace(",", ".")) / 100
    return qty * float(r["unit_price"]) * fx * surcharge


def _full_paths(world: World, items: list[str]) -> list[str]:
    """Turn bare file names ('goods_receipts.csv') into paths the file endpoint can serve."""
    root = world.tenant.data_root
    index: dict[str, str] = {}
    for f in root.rglob("*"):
        if f.is_file():
            index.setdefault(f.name, str(f.relative_to(root)))
    out = []
    for it in items:
        name = str(it).split(" ")[0].rstrip(":")
        out.append(index.get(name, index.get(name.split("/")[-1], it)) if "/" not in str(it) or name in index else it)
    return out


class Pipeline:
    def __init__(self, tenant: Tenant | None = None, store: Store | None = None):
        self.tenant = tenant or get_tenant()
        self.store = store or Store(self.tenant)
        self.playbooks = load_playbooks()

    def run(self, reason: str = "manual") -> dict:
        started = datetime.now().astimezone().isoformat(timespec="seconds")
        from aurora.ingest.schema_mapper import SchemaMapper
        mapped = SchemaMapper(self.tenant).run()          # understand files nobody configured
        world = World.load(self.tenant)
        planner = LaunchPlanner(world)
        base = planner.run()                                   # truth, before any decision
        from aurora.comms import check_deliveries
        delivered = check_deliveries(self.tenant, self.store, world)
        committed = self.store.get("committed_actions", [])
        current = LaunchPlanner(world).run(actions=committed)  # truth incl. approved decisions
        policy = PolicyEngine.load(world)
        signals = run_all(world, base, policy.rules, planner.as_of)

        all_actions = [c["action_id"] for c in base["conditional"]]
        what_if_all = LaunchPlanner(world).run(actions=all_actions)
        created = updated = 0
        for sig in signals:
            case = self._build_case(world, planner, base, policy, sig)
            from aurora.explain import build as explain
            case["explanation"] = explain(world, case, base)
            _, new = self.store.upsert_case(sig.fingerprint, case["title"], case["status"], case["playbook_id"],
                                            sig.type, case, case["rank_score"])
            created += new
            updated += not new
        # cases no longer backed by any signal: newer data resolved or superseded them
        live = {sig.fingerprint for sig in signals}
        for c in self.store.cases():
            if c["fingerprint"] not in live and c["status"] in ("AWAITING_APPROVAL", "READY_TO_ASK", "AWAITING_HUMAN_REVIEW"):
                self.store.set_status(c["id"], "SUPERSEDED", "pipeline", "No longer supported by the latest data")
        investigated = self.investigate_new(world)
        overview = self._overview(world, planner, base, what_if_all, policy, current, committed)
        from aurora.notify import notify_new_cases
        notified = notify_new_cases(self.tenant, self.store,
                                    lambda role: policy.holder(role, planner.as_of.date())[0])
        from aurora.goal import build_goal
        overview["counts"] = {}
        for c in self.store.cases():
            overview["counts"][c["status"]] = overview["counts"].get(c["status"], 0) + 1
        overview["goal"] = build_goal(self.tenant, overview, self.store.cases(), policy.rules)
        self.store.put("overview", overview)
        self.store.put("plan", base)
        report = {"reason": reason, "documents": len(world.documents), "signals": len(signals),
                  "cases_new": created, "cases_updated": updated, "notified": notified, "delivered": delivered, "investigated": investigated,
                  "new_sources": [m["path"] for m in mapped if m.get("status") == "auto"], "errors": world.errors[:5]}
        self.store.log_run(started, reason, report)
        return report

    def investigate_new(self, world: World, limit: int = 3) -> list[str]:
        """Run the Investigator on new kinds of problems that have no playbook yet."""
        from aurora.agents import llm
        from aurora.investigator import investigate
        if not llm.available():
            return []
        done = []
        for c in self.store.cases("AWAITING_HUMAN_REVIEW"):
            if c["playbook_id"] or c["data"].get("investigation") or len(done) >= limit:
                continue
            self.store.event(c["id"], "investigator", "Investigating: checking plan, parts, supplier, documents, what-ifs")
            try:
                inv = investigate(world, self.store, c)
            except Exception as e:
                self.store.event(c["id"], "investigator", f"Investigation failed: {e}")
                continue
            self.store.update_data(c["id"], investigation=inv)
            tools = sorted({t["tool"] for t in inv["trace"] if t["tool"] != "submit"})
            self.store.event(c["id"], "investigator",
                             f"Done after {len(inv['trace']) - 1} tool calls ({', '.join(tools)}). "
                             f"{'Affects' if inv['affects_deadline'] else 'Does not affect'} the deadline. "
                             f"Recommendation: {inv['recommendation'][:200]}")
            done.append(c["id"])
        return done

    # ---- cases -------------------------------------------------------------------
    def _build_case(self, world: World, planner: LaunchPlanner, base: dict, policy: PolicyEngine, sig: Signal) -> dict:
        pb = self.playbooks.get(sig.type) or (match_learned(self.tenant, sig) if sig.type.startswith("novel") else None)
        part = sig.entities.get("part")
        category = None
        if not part and sig.entities.get("supplier"):
            sup = world.t("suppliers")
            hit = sup[sup["supplier_id"] == sig.entities["supplier"]]
            category = hit.iloc[0]["category"] if len(hit) else None
        if part:
            p = world.t("parts")
            hit = p[p["part_id"] == part]
            category = hit.iloc[0]["category"] if len(hit) else None
        impact = self._impact(world, base, part)
        options = self._options(world, planner, base, policy, pb, part, category, impact) if pb else []
        recommended = next((o for o in options if o["feasible"]), None)
        approval = recommended["approver"] if recommended else (
            policy.approver_for(pb["approval"], planner.as_of, category=category).to_dict()
            if pb and pb["approval"] not in ("none",) else None)
        if pb is None:
            status = "AWAITING_HUMAN_REVIEW"
        elif pb["tier"] == "never":
            status = "AWAITING_HUMAN_REVIEW"
        elif pb["tier"] in ("ask", "observe"):
            status = "READY_TO_ASK"
        else:
            status = "AWAITING_APPROVAL"
        owners = [a["person"] for a in (approval or {}).get("approvers", []) if a.get("person")]
        people = {x["name"] for x in policy.rules.get("people", [])}
        if not owners and sig.facts.get("owner_person") in people:      # e.g. the PO's buyer
            owners = [sig.facts["owner_person"]]
        if not owners and sig.facts.get("owner_role"):                  # e.g. Logistics Planner for tracking
            who = policy.holder(sig.facts["owner_role"], planner.as_of.date())[0]
            owners = [who] if who else []
        if not owners:   # ask/review cases: the category buyer, else the policy's exception role
            if category:
                for role in ("Buyer", "Senior Buyer"):
                    who = policy.holder(role, planner.as_of.date(), category)[0]
                    if who:
                        owners = [who]
                        break
            if not owners or pb is None:
                owners = [x for x in [policy.holder(policy.rules.get("exception_role") or "Head of Procurement",
                                                     planner.as_of.date())[0]] if x]
        lum = impact.get("last_useful_moment")
        hours_left = max((datetime.fromisoformat(lum) - planner.as_of).total_seconds() / 3600, 0.5) if lum else 48
        eur_at_risk = impact.get("eur_at_risk", 0) or (sig.severity * 1000)
        sig.evidence = _full_paths(world, sig.evidence)
        for o in options:
            o["evidence"] = _full_paths(world, o["evidence"])
        return {
            "title": recommended["title"] if recommended else sig.title,
            "status": status,
            "playbook_id": pb["id"] if pb else None,
            "playbook_title": pb["title"] if pb else "New kind of problem: needs a human",
            "tier": pb["tier"] if pb else "review",
            "signal": sig.to_dict(),
            "impact": impact,
            "options": options,
            "recommended_option": recommended["id"] if recommended else None,
            "approver": approval,
            "owners": owners,
            "also": pb.get("also", []) if pb else [],
            "supplier_intent": pb.get("supplier_intent") if pb else None,
            "rank_score": round(eur_at_risk / hours_left, 2) * (1.0 if sig.facts.get("affects_deadline", True) else 0.1),
        }

    def _impact(self, world: World, base: dict, part: str | None) -> dict:
        if not part:
            return {}
        value = world.tenant.cfg.get("value_at_risk_eur", {})
        copies, eur, per_product = 0, 0.0, {}
        lum = None
        for prod in base["products"]:
            short = prod["short_by_part"].get(part, 0)
            if short > 0 and prod["bottleneck"] == part or (short > 0 and prod["truth_buildable"] < prod["remaining"]):
                qty = world.bom(prod["product_id"]).get(part, 1)
                lost = min(math.ceil(short / qty), prod["remaining"] - prod["truth_buildable"])
                if lost <= 0:
                    continue
                per_product[prod["product_id"]] = lost
                copies += lost
                eur += lost * value.get(prod["product_id"], 0)
                rate = next(p["rate_per_hour"] for p in world.tenant.cfg["products"] if p["id"] == prod["product_id"])
                buf = float(world.tenant.cfg.get("receiving_buffer_hours", 2))
                moment = world.tenant.deadline - timedelta(hours=lost / rate + buf)
                lum = min(lum, moment) if lum else moment
        return {"copies_at_risk": copies, "eur_at_risk": round(eur), "by_product": per_product, "part": part,
                "part_name": world.part_name(part), "last_useful_moment": lum.isoformat() if lum else None}

    def _options(self, world, planner, base, policy, pb, part, category, impact) -> list[dict]:
        opts = []
        value = world.tenant.cfg.get("value_at_risk_eur", {})
        weights = {p["id"]: p.get("customer_weight", 1) for p in world.tenant.cfg["products"]}
        base_built = {p["product_id"]: p["truth_buildable"] for p in base["products"]}
        lum = datetime.fromisoformat(impact["last_useful_moment"]) if impact.get("last_useful_moment") else world.tenant.deadline
        for c in base["conditional"]:
            if c["part_id"] != part or c["kind"] not in pb["option_kinds"]:
                continue
            # marginal gain: everything we could do vs everything except this option
            all_ids = [x["action_id"] for x in base["conditional"]]
            with_all = LaunchPlanner(world).run(actions=all_ids)
            without = LaunchPlanner(world).run(actions=[a for a in all_ids if a != c["action_id"]])
            w_all = {p["product_id"]: p["truth_buildable"] for p in with_all["products"]}
            gained = {p["product_id"]: w_all[p["product_id"]] - p["truth_buildable"] for p in without["products"]}
            costs = world.tenant.cfg.get("costs", {})
            if c["kind"] == "accept_offer":
                cost = _eur(world, c["qty"], part, c["title"], c["cost_note"])
                kind = "purchase"
            elif c["kind"] == "collect_at_port":
                cost, kind = costs.get("local_pickup_eur"), "dock_slot"
            else:
                cost, kind = (c.get("basis_qty") or c["qty"]) * costs.get("sort_per_unit_eur", 0), "concession"
            req = policy.required_roles_from_text(c.get("owner_hint", "")) if kind == "concession" else None
            chain = policy.approver_for(kind, planner.as_of, value_eur=cost or 0, category=category,
                                        site=world.tenant.cfg["deadline"].get("site"), required_roles=req or None)
            arrival = datetime.fromisoformat(c["available_at"])
            # late but not useless: only the pack hours left after arrival can use the parts
            partial = False
            if arrival > lum:
                for pid, g in list(gained.items()):
                    if g > 0:
                        rate = next(p["rate_per_hour"] for p in world.tenant.cfg["products"] if p["id"] == pid)
                        usable_h = planner.hours_left(arrival + timedelta(hours=float(world.tenant.cfg.get("receiving_buffer_hours", 2))))
                        gained[pid] = min(g, int(rate * usable_h))
                        if gained[pid] < g:
                            partial, ratio = True, gained[pid] / g
                            for other, og in gained.items():   # trade-offs shrink with the gain
                                if og < 0:
                                    gained[other] = int(og * ratio)
            protected = sum(max(g, 0) * value.get(pid, 0) * weights.get(pid, 1) / max(weights.values()) for pid, g in gained.items())
            opts.append({
                "id": c["action_id"], "kind": c["kind"], "title": c["title"], "qty": int(c["qty"]),
                "copies_gained": {k: int(v) for k, v in gained.items() if v}, "cost_eur": round(cost) if cost else None,
                "cost_note": c["cost_note"], "arrival_at": arrival.isoformat(),
                "feasible": arrival <= lum or any(v > 0 for v in gained.values()), "partial": partial,
                "last_useful_moment": lum.isoformat(), "approver": chain.to_dict(), "approval_kind": kind,
                "evidence": c["evidence"], "score": round(protected / max(cost or 1, 1), 2),
                "transit_after_ready_h": c.get("transit_after_ready_h") or 13,
            })
        opts.sort(key=lambda o: (not o["feasible"], -o["score"]))
        return opts

    def _verdict(self, world, base, cur, wf, day_one) -> dict:
        """On time = every product within its agreed tolerance (share of the full launch)."""
        per = []
        for p in base["products"]:
            pid = p["product_id"]
            cfg = next(x for x in world.tenant.cfg["products"] if x["id"] == pid)
            tol = float(cfg.get("max_shortfall_pct_of_launch", 0))
            total = day_one.get(pid) or 1
            for view, built in (("current", cur[pid]), ("with_all", wf[pid])):
                short = max(p["remaining"] - built, 0)
                per.append({"product_id": pid, "name": p["name"], "view": view, "short": int(short),
                            "short_pct_of_launch": round(100 * short / total, 1), "tolerance_pct": tol,
                            "within": 100 * short / total <= tol})
        now_ok = all(x["within"] for x in per if x["view"] == "current")
        all_ok = all(x["within"] for x in per if x["view"] == "with_all")
        late = [x for x in per if x["view"] == "current" and x["short"]]
        text = ("On time: every product within its agreed tolerance."
                if now_ok else "Not yet on time with the decisions taken so far.")
        if now_ok and late:
            text = ("On time: " + "; ".join(f"{x['short']:,} {x['name']} copies follow later "
                                            f"({x['short_pct_of_launch']}% of launch, tolerance {x['tolerance_pct']:g}%)"
                                            for x in late) + ". All other demand ships Sunday.")
        return {"on_time_now": now_ok, "on_time_with_all": all_ok, "text": text, "products": per}

    # ---- overview ------------------------------------------------------------------
    def _overview(self, world, planner, base, what_if_all, policy, current, committed) -> dict:
        wf = {p["product_id"]: p["truth_buildable"] for p in what_if_all["products"]}
        cur = {p["product_id"]: p["truth_buildable"] for p in current["products"]}
        prod = world.t("products")
        day_one = {r["product_id"]: float(r.get("day_one_qty") or 0) for r in prod.to_dict("records")}

        def pct(pid, remaining, built):
            total = day_one.get(pid) or 0
            return round(100 * (total - remaining + built) / total, 1) if total else None
        rules = [{"text": r["text"], "source": r["source"]} for r in policy.rules.get("priority_rules", [])]
        rules += [{"text": r["text"], "source": r["source"]} for r in policy.rules.get("release_rules", [])]
        return {
            "tenant": world.tenant.cfg["display_name"],
            "deadline_name": world.tenant.cfg["deadline"]["name"],
            "deadline": base["deadline"], "as_of": base["as_of"], "hours_left": base["hours_left"],
            "editions": [{**p, "what_if_buildable": wf[p["product_id"]], "current_buildable": cur[p["product_id"]],
                          "day_one_qty": int(day_one.get(p["product_id"]) or 0),
                          "packed_before": int((day_one.get(p["product_id"]) or 0) - p["remaining"]),
                          "day_one_pct": {"system": pct(p["product_id"], p["remaining"], p["system_buildable"]),
                                          "truth": pct(p["product_id"], p["remaining"], p["truth_buildable"]),
                                          "current": pct(p["product_id"], p["remaining"], cur[p["product_id"]]),
                                          "what_if": pct(p["product_id"], p["remaining"], wf[p["product_id"]])}}
                         for p in base["products"]],
            "committed_actions": committed,
            "verdict": self._verdict(world, base, cur, wf, day_one),
            "rules_in_force": [{**r, "source": _full_paths(world, [r["source"]])[0]} for r in rules],
            "corrections": [{**e, "evidence": _full_paths(world, e["evidence"]), "part_name": world.part_name(e["part_id"])}
                            for e in base["ledger"] if e["kind"] not in ("consumed", "inbound")],
            "part_names": {pid: world.part_name(pid) for pid in world.t("parts")["part_id"]},
            "pack_hours_left": base["hours_left"],
            "autonomy_threshold": world.tenant.cfg.get("autonomy", {}).get("earned_after_approvals", 3),
            "documents_read": len(world.documents),
        }
