"""Onboarding agent: proposes a customer's whole setup from their own files.

Five sections, each with its sources and a human confirmation:
1. Sources       — where data and email come from
2. Data          — what every file is (configured, or understood by the Schema Mapper)
3. Goal          — deadline, what "done" means, product priorities (proposed by the planning model
                   from onboarding notes, memos, plans and the product master)
4. Rules         — approval limits, roles, vacancies, release and priority rules (Policy agent)
5. Autonomy      — what agents do alone, mandates, who gets notified (playbooks + config)
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import yaml

from aurora.agents import llm
from aurora.config import Tenant
from aurora.ingest.schema_mapper import SchemaMapper
from aurora.world import World

S = {"type": ["string", "null"]}

GOAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["objective", "deadline_at", "deadline_name", "deadline_meaning", "site", "shifts", "products",
                 "success_metric", "tolerances", "open_questions"],
    "properties": {
        "objective": {"type": "string"},
        "deadline_at": S, "deadline_name": S, "deadline_meaning": S, "site": S,
        "shifts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["start", "end"],
                                              "properties": {"start": {"type": "string"}, "end": {"type": "string"}}}},
        "products": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["id", "name", "priority", "demand", "reason", "source"],
                     "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                                    "priority": {"type": "integer"}, "demand": {"type": ["number", "null"]},
                                    "reason": {"type": "string"}, "source": {"type": "string"}}}},
        "success_metric": {"type": "string"},
        "tolerances": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
}

GOAL_SYSTEM = """You onboard a new customer into a deadline-driven supply product. From their own documents,
propose the goal the agents will optimise for: the hard deadline (ISO 8601 with offset), what the deadline
means operationally, the site, the working shifts before it, each finished product with its demand and a
priority (1 = protect first) with the reason and the source file, a one-sentence objective, how success is
measured, any stated tolerances, and open questions a human must answer (e.g. value of a missed unit).
Use only what the documents say; cite file names."""


class Onboarding:
    def __init__(self, tenant: Tenant, world: World):
        self.t = tenant
        self.w = world
        self.conf_path = tenant.state_dir / "setup_confirmations.json"
        self.confirmations = json.loads(self.conf_path.read_text()) if self.conf_path.exists() else {}

    def confirm(self, section: str, by: str) -> dict:
        self.confirmations[section] = {"by": by, "at": datetime.now().astimezone().isoformat(timespec="minutes")}
        self.conf_path.write_text(json.dumps(self.confirmations, indent=1))
        return self.confirmations[section]

    # ---- 1. sources -------------------------------------------------------------
    def sources(self) -> dict:
        src = self.t.cfg["source"]
        files = [p for p in self.t.data_root.rglob("*") if p.is_file()]
        return {"items": [
            {"kind": "File portal", "detail": src["base_url"], "status": "connected",
             "note": f"{len(files)} files, checked every 60 s"},
            {"kind": "Mailbox", "detail": os.environ.get("GMAIL_USER", "not configured"),
             "status": "connected" if os.environ.get("GMAIL_APP_PASSWORD") else "missing",
             "note": "supplier emails out and in; untagged mail becomes documents"},
            {"kind": "People", "detail": f"{len(self.t.cfg.get('people', {}))} internal contacts",
             "status": "configured", "note": "who receives approval requests"},
        ]}

    # ---- 2. data understood ---------------------------------------------------------
    def data(self) -> dict:
        tables = []
        for name, spec in self.t.cfg.get("tables", {}).items():
            df = self.w.t(name)
            srcs = sorted(df["_source"].unique()) if not df.empty and "_source" in df.columns else []
            learned = sorted(df.loc[df.get("_mapped_by").notna(), "_source"].unique()) \
                if not df.empty and "_mapped_by" in df.columns else []
            tables.append({"table": name, "rows": int(len(df)), "files": len(srcs),
                           "configured": [s for s in srcs if s not in learned], "learned": learned})
        mapper = SchemaMapper(self.t)
        pending = [m for m in mapper.state.values() if m["status"] == "proposed"]
        docs: dict[str, int] = {}
        for d in self.w.documents:
            docs[d.get("doc_type", "other")] = docs.get(d.get("doc_type", "other"), 0) + 1
        names = {"en": "English", "english": "English", "pl": "Polish", "polish": "Polish", "ko": "Korean",
                 "korean": "Korean", "zh": "Chinese", "chinese": "Chinese", "zh-cn": "Chinese", "de": "German",
                 "german": "German"}
        langs: dict[str, int] = {}
        for d in self.w.documents:
            import re as _re
            for tok in set(_re.split(r"[/+;, ]+", str(d.get("language", "")).lower())):
                if tok in names:
                    langs[names[tok]] = langs.get(names[tok], 0) + 1
        return {"tables": tables,
                "learned_sources": [{"path": m["path"], "table": m["table"], "confidence": m["confidence"],
                                     "status": m["status"], "reason": m["reason"]} for m in mapper.state.values()],
                "pending_confirmation": [{"path": m["path"], "table": m["table"], "confidence": m["confidence"],
                                          "reason": m["reason"]} for m in pending],
                "documents": {"total": len(self.w.documents), "by_type": docs, "by_language": langs}}

    # ---- 3. goal ------------------------------------------------------------------
    def goal(self) -> dict:
        docs = [d for d in self.w.documents if d.get("doc_type") in ("memo", "other", "policy")
                or d["_source"].endswith((".md", "launch_plan_GH6.xlsx"))]
        prod = self.w.t("products")
        plan = self.w.t("plan_status")
        material = {
            "documents": [{"file": d["_source"], "summary": d.get("summary_en"), "rules": d.get("rules", [])[:15]}
                          for d in docs],
            "products": prod.drop(columns=[c for c in prod.columns if c.startswith("_")], errors="ignore")
                            .astype(str).to_dict("records"),
            "plan_status": plan.drop(columns=[c for c in plan.columns if c.startswith("_") and c != "_title"],
                                     errors="ignore").astype(str).head(30).to_dict("records"),
        }
        raw = json.dumps(material, ensure_ascii=False, default=str)
        key = hashlib.sha256(raw.encode()).hexdigest()[:16]
        cache = self.t.state_dir / f"goal_proposal_{key}.json"
        if cache.exists():
            proposal = json.loads(cache.read_text())
        elif llm.available():
            proposal = llm.structured(system=GOAL_SYSTEM, content=raw[:60000], schema=GOAL_SCHEMA,
                                      role="plan", effort="medium")
            cache.write_text(json.dumps(proposal, indent=1, ensure_ascii=False))
        else:
            return {"proposal": None, "live": self._live_goal(), "checks": []}
        return {"proposal": proposal, "live": self._live_goal(), "checks": self._compare(proposal)}

    def _live_goal(self) -> dict:
        c = self.t.cfg
        return {"deadline_at": c["deadline"]["at"], "deadline_name": c["deadline"]["name"],
                "site": c["deadline"].get("site"), "shifts": c.get("shifts", []),
                "products": [{"id": p["id"], "name": p["name"], "priority": p["priority"]} for p in c["products"]],
                "value_at_risk_eur": c.get("value_at_risk_eur", {})}

    def _compare(self, p: dict) -> list[dict]:
        live = self._live_goal()
        checks = []
        same_deadline = bool(p.get("deadline_at")) and \
            datetime.fromisoformat(p["deadline_at"]) == datetime.fromisoformat(live["deadline_at"])
        checks.append({"item": "Deadline", "proposed": p.get("deadline_at"), "live": live["deadline_at"], "match": same_deadline})
        order_p = [x["id"] for x in sorted(p.get("products", []), key=lambda x: x["priority"])]
        order_l = [x["id"] for x in sorted(live["products"], key=lambda x: x["priority"])]
        checks.append({"item": "Product priority", "proposed": order_p, "live": order_l,
                       "match": [i for i in order_p if i in order_l] == [i for i in order_l if i in order_p]})
        checks.append({"item": "Shifts", "proposed": len(p.get("shifts", [])), "live": len(live["shifts"]),
                       "match": len(p.get("shifts", [])) == len(live["shifts"])})
        return checks

    # ---- 4. rules -----------------------------------------------------------------
    def rules(self) -> dict:
        from aurora.policy import PolicyEngine
        r = PolicyEngine.load(self.w).rules
        today = (self.w.tenant.deadline).date()
        people = []
        for p in r.get("people", []):
            vacant_now = bool(p.get("from_date")) and p["from_date"][:10] > str(today)
            people.append({**p, "vacant_until_start": vacant_now})
        return {"sources": r.get("_sources", []), "approval_limits": r.get("approval_limits", []),
                "people": people, "site_leads": r.get("site_leads", []),
                "exception_role": r.get("exception_role"), "quality_final_say": r.get("quality_final_say_role"),
                "conditional_release_days": r.get("conditional_release_days"),
                "priority_rules": r.get("priority_rules", []), "release_rules": r.get("release_rules", [])}

    # ---- 5. autonomy ------------------------------------------------------------------
    def autonomy(self) -> dict:
        from aurora.pipeline import LIBRARY
        lib = yaml.safe_load(LIBRARY.read_text())
        c = self.t.cfg
        return {"playbooks": [{"id": p["id"], "title": p["title"], "tier": p["tier"], "approval": p["approval"]}
                              for p in lib],
                "unknown_problems": "Review by the person the policy names; decision can become a playbook",
                "mandate_tolerance": c.get("comms", {}).get("negotiation_tolerance", 0.10),
                "max_agent_rounds": 3,
                "earned_autonomy_after": c.get("autonomy", {}).get("earned_after_approvals", 3),
                "reply_timeout_minutes_demo": c.get("comms", {}).get("demo_reply_timeout_minutes", 20),
                "notifications": "one digest per person per run, only for decisions they must take; "
                                 "escalation once per case",
                "never": ["payments", "bank-detail changes", "contract changes"]}

    def build(self) -> dict:
        sections = {"sources": self.sources(), "data": self.data(), "goal": self.goal(),
                    "rules": self.rules(), "autonomy": self.autonomy()}
        flow = ["goal", "rules", "autonomy", "data", "sources"]
        return {"tenant": self.t.cfg["display_name"], "sections": sections, "confirmations": self.confirmations,
                "flow": flow, "progress": {"confirmed": sum(1 for f in flow if f in self.confirmations), "total": len(flow)}}
