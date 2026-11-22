"""Investigator: a tool-using agent for problems no playbook covers.

It decides itself which read-only tools to call (plan, parts, suppliers, documents, what-ifs,
policy, open cases), stops when it knows enough, and submits: what happened, whether it hits the
deadline, root cause, 2-3 options with approver and timing, a recommendation, open questions, and a
draft playbook so the next similar case can run by itself.
"""
from __future__ import annotations

import hashlib
import json
import re

from aurora.agents import llm
from aurora.planner import LaunchPlanner
from aurora.policy import PolicyEngine
from aurora.store import Store
from aurora.world import World

SYSTEM = """You are the Investigator in a procurement operations team with a hard deadline.
A problem was flagged that no existing playbook covers. Investigate it like a senior buyer:
check the plan, the affected parts and supplier, the relevant documents, and use what-if runs to
quantify the effect on the deadline before concluding. Prefer evidence over assumptions; cite the
documents you used. Keep options realistic, cheap first, and name who must approve each (use
get_approver). Then call submit_findings. Be concise: plain English for a busy manager."""

S = {"type": ["string", "null"]}
SUBMIT = {
    "name": "submit_findings",
    "description": "Submit the investigation result when you know enough.",
    "parameters": {
        "type": "object", "additionalProperties": False,
        "required": ["summary", "affects_deadline", "impact", "root_cause", "options", "recommendation",
                     "questions_for_human", "evidence", "playbook", "confidence"],
        "properties": {
            "summary": {"type": "string"},
            "affects_deadline": {"type": "boolean"},
            "impact": {"type": "object", "additionalProperties": False, "required": ["copies_at_risk", "when", "explanation"],
                       "properties": {"copies_at_risk": {"type": "integer"}, "when": {"type": "string"},
                                      "explanation": {"type": "string"}}},
            "root_cause": {"type": "string"},
            "options": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["title", "action_kind", "who_approves", "cost_estimate_eur", "effect", "timing"],
                "properties": {"title": {"type": "string"},
                               "action_kind": {"type": "string", "enum": ["purchase", "ask_supplier", "dock_slot", "concession",
                                                                         "internal_instruction", "monitor"]},
                               "who_approves": {"type": "string"}, "cost_estimate_eur": {"type": ["number", "null"]},
                               "effect": {"type": "string"}, "timing": {"type": "string"}}}},
            "recommendation": {"type": "string"},
            "questions_for_human": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "playbook": {"type": "object", "additionalProperties": False,
                         "required": ["title", "trigger_keywords", "steps", "tier"],
                         "properties": {"title": {"type": "string"},
                                        "trigger_keywords": {"type": "array", "items": {"type": "string"}},
                                        "steps": {"type": "array", "items": {"type": "string"}},
                                        "tier": {"type": "string", "enum": ["observe", "ask", "commit"]}}},
            "confidence": {"type": "number"},
        },
    },
}


class Toolbox:
    """Read-only, deterministic tools over the world. Nothing here changes data."""

    def __init__(self, world: World, store: Store):
        self.w, self.store = world, store
        self.planner = LaunchPlanner(world)
        self.base = self.planner.run()
        self.policy = PolicyEngine.load(world)

    def _part_ids(self, q: str) -> list[str]:
        p = self.w.t("parts")
        ql = q.lower()
        return [r["part_id"] for r in p.to_dict("records") if ql in r["part_id"].lower() or ql in str(r["description"]).lower()]

    def get_plan_overview(self) -> dict:
        return {"as_of": self.base["as_of"], "deadline": self.base["deadline"], "pack_hours_left": self.base["hours_left"],
                "products": [{k: p[k] for k in ("product_id", "name", "remaining", "truth_buildable", "bottleneck", "short_by_part")}
                             for p in self.base["products"]],
                "corrections": [e["reason"] for e in self.base["ledger"] if e["kind"] not in ("consumed", "inbound", "erp_stock")][:12]}

    def query_part(self, part: str) -> dict:
        out = []
        for pid in self._part_ids(part)[:3]:
            po = self.w.t("po_lines")
            open_po = po[(po["part_id"] == pid) & po["status"].astype(str).str.lower().isin(["open", "awaiting_approval"])]
            ships = self.w.t("shipments")
            sh = ships[ships["material_ids"].astype(str).str.contains(pid, regex=False)]
            used_in = {p["id"]: self.w.bom(p["id"]).get(pid, 0) for p in self.w.tenant.cfg["products"]}
            out.append({"part_id": pid, "name": self.w.part_name(pid),
                        "available_truth": self.base["supply_truth"].get(pid), "available_erp": self.base["supply_system"].get(pid),
                        "used_per_unit": {k: v for k, v in used_in.items() if v},
                        "suppliers": self.w.t("supplier_parts").query("part_id == @pid")[["supplier_id", "share", "lead_time_days"]]
                                     .drop_duplicates().to_dict("records"),
                        "open_po_lines": open_po[["po_number", "supplier_id", "quantity", "promised_date", "status"]]
                                         .astype(str).head(12).to_dict("records"),
                        "shipments": sh[["shipment_id", "supplier_id", "mode", "eta", "status", "updated_at"]]
                                     .astype(str).to_dict("records")})
        return {"parts": out} if out else {"error": f"no part matches '{part}'"}

    def query_supplier(self, supplier: str) -> dict:
        sup = self.w.t("suppliers")
        ql = supplier.lower()
        rows = [r for r in sup.to_dict("records") if ql in str(r.get("name", "")).lower() or ql in str(r["supplier_id"]).lower()]
        if not rows:
            return {"error": f"no supplier matches '{supplier}'"}
        s = rows[0]
        sid = s["supplier_id"]
        po = self.w.t("po_lines")
        open_po = po[(po["supplier_id"] == sid) & po["status"].astype(str).str.lower().isin(["open", "awaiting_approval"])]
        docs = [{"source": d["_source"], "type": d["doc_type"], "summary": d.get("summary_en", "")[:200]}
                for d in self.w.documents if sid in d["_source"] and d["doc_type"] not in ("order_confirmation",)]
        return {"supplier": {k: s.get(k) for k in ("supplier_id", "name", "country", "status", "qualification_status",
                                                     "preferred_language", "notes")},
                "parts": self.w.t("supplier_parts").query("supplier_id == @sid")["part_id"].unique().tolist(),
                "open_po_lines": open_po[["po_number", "part_id", "quantity", "promised_date", "status"]].astype(str)
                                 .head(15).to_dict("records"),
                "documents": docs[:10]}

    def search_documents(self, query: str) -> dict:
        words = [w for w in re.findall(r"\w{3,}", query.lower())]
        scored = []
        for d in self.w.documents:
            hay = " ".join([d.get("summary_en", ""), " ".join(d.get("rules", [])), " ".join(d.get("supply_risks", [])),
                            d["_source"]]).lower()
            score = sum(hay.count(w) for w in words)
            if score:
                scored.append((score, d))
        scored.sort(key=lambda x: -x[0])
        return {"results": [{"source": d["_source"], "type": d["doc_type"], "summary": d.get("summary_en", "")[:250]}
                            for _, d in scored[:8]]}

    def read_document(self, source: str) -> dict:
        d = next((d for d in self.w.documents if d["_source"] == source or d["_source"].endswith(source)), None)
        if not d:
            return {"error": "not found"}
        return {k: v for k, v in d.items() if not k.startswith("_sha") and v not in (None, [], "")}

    def what_if(self, part: str, qty_change: float, available_at: str | None = None) -> dict:
        pid = (self._part_ids(part) or [part])[0]
        after = self.planner.run(extra_supply=[{"part_id": pid, "qty": qty_change, "available_at": available_at}])
        before = {p["product_id"]: p["truth_buildable"] for p in self.base["products"]}
        return {"part": pid, "qty_change": qty_change, "products": [
            {"product_id": p["product_id"], "before": before[p["product_id"]], "after": p["truth_buildable"],
             "remaining": p["remaining"]} for p in after["products"]]}

    def get_approver(self, action_kind: str, value_eur: float = 0, category: str | None = None) -> dict:
        kind = {"ask_supplier": "ask", "internal_instruction": "ask", "monitor": "ask"}.get(action_kind, action_kind)
        return self.policy.approver_for(kind, self.planner.as_of, value_eur=value_eur, category=category,
                                        site=self.w.tenant.cfg["deadline"].get("site")).to_dict()

    def list_open_cases(self) -> dict:
        return {"cases": [{"id": c["id"], "status": c["status"], "title": c["title"][:120]}
                          for c in self.store.cases() if c["status"] not in ("SUPERSEDED",)]}

    def tools(self) -> list[dict]:
        T = lambda name, desc, props=None, req=None: {
            "name": name, "description": desc, "fn": getattr(self, name),
            "parameters": {"type": "object", "properties": props or {}, "required": req or [], "additionalProperties": False}}
        return [
            T("get_plan_overview", "Current launch plan: remaining per product, truly buildable, bottlenecks, corrections."),
            T("query_part", "Stock (ERP vs truth), BOM usage, suppliers, open POs and shipments for a part (id or name).",
              {"part": {"type": "string"}}, ["part"]),
            T("query_supplier", "Supplier profile, parts, open POs and recent documents.", {"supplier": {"type": "string"}}, ["supplier"]),
            T("search_documents", "Keyword search over all documents read so far.", {"query": {"type": "string"}}, ["query"]),
            T("read_document", "Full extracted facts of one document by its source path.", {"source": {"type": "string"}}, ["source"]),
            T("what_if", "Re-run the plan with a hypothetical supply change for a part (negative = loss).",
              {"part": {"type": "string"}, "qty_change": {"type": "number"}, "available_at": {"type": ["string", "null"]}},
              ["part", "qty_change", "available_at"]),
            T("get_approver", "Who must approve an action under the customer's policy.",
              {"action_kind": {"type": "string"}, "value_eur": {"type": "number"}, "category": {"type": ["string", "null"]}},
              ["action_kind", "value_eur", "category"]),
            T("list_open_cases", "Open cases, to avoid duplicating known problems."),
        ]


def investigate(world: World, store: Store, case: dict) -> dict:
    sig = case["data"]["signal"]
    key = hashlib.sha256(json.dumps([sig["fingerprint"], sig["evidence"], sig["summary"]]).encode()).hexdigest()[:16]
    cache = world.tenant.state_dir / f"investigation_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    tb = Toolbox(world, store)
    user = (f"Customer: {world.tenant.cfg['display_name']}. Deadline: {world.tenant.cfg['deadline']['name']} "
            f"at {world.tenant.cfg['deadline']['at']}.\nFlagged problem ({case['id']}): {sig['title']}\n"
            f"Details: {sig['summary']}\nFindings: {json.dumps(sig['facts'].get('findings', []), ensure_ascii=False)[:2500]}\n"
            f"Evidence files: {sig['evidence']}")
    steps: list[str] = []
    result, trace = llm.tool_loop(system=SYSTEM, user=user, tools=tb.tools(), submit=SUBMIT, role="plan",
                                  effort="medium", max_steps=12,
                                  on_step=lambda name, args: steps.append(f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})"))
    result["trace"] = trace
    cache.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    return result
