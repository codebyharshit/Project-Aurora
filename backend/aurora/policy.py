"""Policy engine.

1. parse_policies(): one planning-model call turns the customer's own policy, org chart
   and memo documents into a structured rule set (cached by the documents' SHA-256).
2. approver_for(): deterministic resolution of who must approve an action, including
   vacant roles (falls back to the role the policy names for exceptions).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from aurora.agents import llm
from aurora.world import World

S = {"type": ["string", "null"]}
N = {"type": ["number", "null"]}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


ROLES = ["Buyer", "Category Lead", "Head of Procurement", "Chief Procurement Officer",
         "Chief Financial Officer", "Supplier Quality Lead", "Quality & Compliance Manager",
         "Site Lead", "Logistics Planner", "IT & Systems Lead", "Senior Buyer"]

POLICY_SCHEMA = _obj({
    "approval_limits": {"type": "array", "items": _obj({
        "role": {"type": "string", "enum": ROLES}, "max_eur_exclusive": N, "jointly_with": S})},
    "people": {"type": "array", "items": _obj({
        "name": {"type": "string"}, "role": {"type": "string", "enum": ROLES},
        "category": S, "site": S, "from_date": S, "until_date": S})},
    "site_leads": {"type": "array", "items": _obj({"site": {"type": "string"}, "lead": {"type": "string"}, "deputy": S})},
    "air_freight": _obj({"monthly_limit_eur_per_category": N, "approver_role": S, "above_limit_role": S}),
    "conditional_release_days": N,
    "release_extension": _obj({"max_days": N, "roles": {"type": "array", "items": {"type": "string", "enum": ROLES}}}),
    "supplier_release_roles": {"type": "array", "items": {"type": "string", "enum": ROLES}},
    "exception_role": {"type": "string", "enum": ROLES},
    "quality_final_say_role": S,
    "escalations": {"type": "array", "items": _obj({"trigger": {"type": "string"}, "to_person": S, "within": S})},
    "priority_rules": {"type": "array", "items": _obj({"text": {"type": "string"}, "source": {"type": "string"}})},
    "release_rules": {"type": "array", "items": _obj({"text": {"type": "string"}, "source": {"type": "string"}})},
})

SYSTEM = """You turn a company's procurement policies, org charts and management memos into a
structured rule set. Use only what the documents say. Map job titles to the closest role in the
allowed list (e.g. "Category Lead Collector's Items" -> role "Category Lead", category
"Collector's Items"; "Site Lead DC Hamburg" -> role "Site Lead", site "DC-HAM"). When an org chart
says a person holds a role only from a date, set from_date. If several versions of an org chart
exist, use the newest. For each priority or release rule, set source to the document file name."""


@dataclass
class Approver:
    person: str | None
    role: str
    reason: str
    policy_ref: str
    fallback_for: str | None = None


@dataclass
class ApproverChain:
    approvers: list[Approver]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"approvers": [asdict(a) for a in self.approvers], "notes": self.notes}


class PolicyEngine:
    def __init__(self, world: World, rules: dict):
        self.w = world
        self.rules = rules

    # ---- parsing -----------------------------------------------------------------
    @classmethod
    def load(cls, world: World) -> "PolicyEngine":
        docs = [d for d in world.documents if d.get("doc_type") in ("policy", "org_chart", "memo")]
        key = hashlib.sha256("".join(sorted(d["_sha256"] for d in docs)).encode()).hexdigest()[:16]
        cache = world.tenant.state_dir / f"policy_rules_{key}.json"
        if cache.exists():
            return cls(world, json.loads(cache.read_text()))
        text = "\n\n".join(f"### {d['_source']} ({d.get('document_date')})\n" + "\n".join(d.get("rules", []))
                           + f"\nSummary: {d.get('summary_en', '')}" for d in docs)
        rules = llm.structured(system=SYSTEM, content=text, schema=POLICY_SCHEMA, role="plan", effort="medium")
        rules["_sources"] = [d["_source"] for d in docs]
        cache.write_text(json.dumps(rules, indent=1, ensure_ascii=False))
        return cls(world, rules)

    # ---- resolution --------------------------------------------------------------
    def _active(self, p: dict, as_of: date) -> bool:
        f, u = p.get("from_date"), p.get("until_date")
        return (not f or date.fromisoformat(f[:10]) <= as_of) and (not u or date.fromisoformat(u[:10]) >= as_of)

    @staticmethod
    def _cat_match(a: str, b: str) -> bool:
        x, y = a.lower(), b.lower()
        words = lambda t: {w for w in t.replace("&", " ").replace("'", "").split() if len(w) > 3}
        return x == y or x in y or y in x or bool(words(x) & words(y))

    def holder(self, role: str, as_of: date, category: str | None = None, site: str | None = None) -> tuple[str | None, str | None]:
        """Return (person, vacancy_note)."""
        if category is None and role == "Category Lead":
            return None, "Category Lead: category unknown, using the exception role"
        cands = [p for p in self.rules["people"] if p["role"] == role
                 and (category is None or not p.get("category") or self._cat_match(p["category"], category))
                 and (site is None or not p.get("site") or p["site"] == site)]
        active = [p for p in cands if self._active(p, as_of)]
        if active:
            return active[0]["name"], None
        if cands:
            nxt = cands[0]
            return None, f"{role}{' ' + category if category else ''} vacant until {nxt.get('from_date')} ({nxt['name']} starts then)"
        return None, f"{role}{' ' + category if category else ''} not staffed"

    def _with_fallback(self, role: str, as_of: date, reason: str, ref: str, category: str | None = None) -> tuple[Approver, list[str]]:
        person, vacancy = self.holder(role, as_of, category)
        if person:
            return Approver(person, role, reason, ref), []
        ex_role = self.rules.get("exception_role") or "Head of Procurement"
        ex_person, _ = self.holder(ex_role, as_of)
        return (Approver(ex_person, ex_role, f"{reason} (stand-in: documented exception)", "policy: exceptions",
                         fallback_for=f"{role}{' ' + category if category else ''}"), [vacancy] if vacancy else [])

    def approver_for(self, kind: str, as_of: datetime, value_eur: float = 0.0, category: str | None = None,
                     site: str | None = None, required_roles: list[str] | None = None) -> ApproverChain:
        d = as_of.date()
        chain, notes = [], []
        if kind == "purchase":
            limits = sorted((l for l in self.rules["approval_limits"] if l.get("max_eur_exclusive")),
                            key=lambda l: l["max_eur_exclusive"])
            role = next((l["role"] for l in limits if value_eur < l["max_eur_exclusive"]), limits[-1]["role"])
            cat = category if role in ("Buyer", "Category Lead") else None
            a, n = self._with_fallback(role, d, f"PO value €{value_eur:,.0f} is within the {role} limit",
                                       "approval limits", cat)
            chain.append(a); notes += n
        elif kind == "dock_slot":
            for s in self.rules.get("site_leads", []):
                if site is None or s["site"] == site or (site and site in s["site"]):
                    chain.append(Approver(s["lead"], "Site Lead", "Dock slot at the receiving site", "receiving site",
                                          None))
                    if s.get("deputy"):
                        notes.append(f"Deputy: {s['deputy']}")
                    break
        elif kind in ("concession", "po_extension"):
            roles = required_roles or (self.rules.get("release_extension", {}).get("roles") if kind == "po_extension"
                                       else self.rules.get("supplier_release_roles")) or []
            for role in roles:
                cat = category if role == "Category Lead" else None
                a, n = self._with_fallback(role, d, f"Required sign-off: {role}", "supplier release", cat)
                chain.append(a); notes += n
            q = self.rules.get("quality_final_say_role")
            if kind == "concession" and q:
                notes.append(f"Final say on release: {q}")
        elif kind == "air_freight":
            af = self.rules.get("air_freight") or {}
            role = af.get("approver_role") or "Category Lead"
            a, n = self._with_fallback(role.replace(" (responsible)", ""), d, "Unplanned air freight", "air freight", category)
            chain.append(a); notes += n
        else:  # information requests need no approval beyond the case owner
            chain.append(Approver(None, "Buyer", "Information request, no commitment", "autonomy: ask"))
        return ApproverChain(chain, notes)

    def required_roles_from_text(self, text: str) -> list[str]:
        """Map free text such as 'signed by Supplier Quality and the Category Lead' to roles."""
        t = (text or "").lower()
        hits = []
        for role in ROLES:
            words = [w for w in role.lower().replace("&", " ").split() if w not in ("lead", "manager", "the")]
            if words and all(w in t for w in words) and role not in hits:
                hits.append(role)
        if "supplier quality" in t and "Supplier Quality Lead" not in hits:
            hits.append("Supplier Quality Lead")
        return hits
