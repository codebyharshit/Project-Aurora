"""Notifications to internal people: who must approve or decide, told once.

Budget: one digest per person per pipeline run, only for cases that newly need *them*;
one escalation email per case. Everything is logged on the case timeline.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from aurora.config import Tenant
from aurora.store import Store


def _send(to: str, subject: str, body: str) -> bool:
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not (user and pw) or os.environ.get("AURORA_SEND") == "0":   # local testing: never send
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)
    from aurora.comms import smtp_send
    try:
        smtp_send(msg)
    except (OSError, smtplib.SMTPException):   # a notification must never stop the plan from updating
        return False
    return True


def _people(tenant: Tenant) -> dict[str, str]:
    return tenant.cfg.get("people", {}) or {}


def _link(tenant: Tenant, cid: str) -> str:
    base = os.environ.get("AURORA_APP_URL") or tenant.cfg.get("notifications", {}).get("app_url", "")
    return f"{base.rstrip('/')}/cases/{cid}"


def _line(tenant: Tenant, c: dict) -> str:
    d = c["data"]
    rec = next((o for o in d.get("options", []) if o["id"] == d.get("recommended_option")), None)
    parts = [f"• [{c['id']}] {c['title']}"]
    if rec:
        gain = ", ".join(f"{v:+,} {k}" for k, v in rec["copies_gained"].items())
        parts.append(f"  Gain: {gain} · Cost: €{rec['cost_eur']:,} · Ready {rec['arrival_at'][5:16]}"
                     f" · needed by {rec['last_useful_moment'][5:16]}" if rec.get("cost_eur") is not None
                     else f"  Gain: {gain}")
    parts.append(f"  Why: {d['signal']['summary'][:220]}")
    parts.append(f"  Open: {_link(tenant, c['id'])}")
    return "\n".join(parts)


def _recipients(c: dict, tenant: Tenant, policy_holder) -> list[str]:
    d = c["data"]
    if c["status"] == "AWAITING_HUMAN_REVIEW":
        if not d["signal"]["facts"].get("affects_deadline", True):
            return []  # not urgent: goes to the daily one-pager instead
        role = tenant.cfg.get("notifications", {}).get("review_to_role", "Head of Procurement")
        who = policy_holder(role)
        return [who] if who else []
    approvers = (d.get("approver") or {}).get("approvers", [])
    return [a["person"] for a in approvers if a.get("person")]


def notify_new_cases(tenant: Tenant, store: Store, policy_holder) -> dict[str, list[str]]:
    """Send each person one digest of the cases that newly need them."""
    people = _people(tenant)
    sent_already = set(store.get("notified_cases", []))
    digest: dict[str, list[dict]] = {}
    for c in store.cases():
        if c["id"] in sent_already or c["status"] not in ("AWAITING_APPROVAL", "AWAITING_HUMAN_REVIEW"):
            continue
        for person in _recipients(c, tenant, policy_holder):
            digest.setdefault(person, []).append(c)
    sent: dict[str, list[str]] = {}
    for person, cases in digest.items():
        addr = people.get(person)
        if not addr:
            for c in cases:
                store.event(c["id"], "notify", f"{person} has no address on file; shown in Launch Control only")
            continue
        n = len(cases)
        subject = (f"[Aurora] {n} decision{'s' if n > 1 else ''} for you before "
                   f"{tenant.cfg['deadline']['name']}")
        body = (f"Hello {person.split()[-1] if person.startswith('Dr.') else person.split()[0]},\n\n"
                f"Aurora needs your decision on {n} case{'s' if n > 1 else ''}. "
                f"Each is ranked by customers protected per euro and checked against the deadline "
                f"({tenant.cfg['deadline']['at'][:16].replace('T', ' ')}).\n\n"
                + "\n\n".join(_line(tenant, c) for c in cases)
                + "\n\nApprove or decide in Launch Control. You will not get another email for these cases "
                  "unless a supplier goes silent.\n\n— Aurora")
        ok = _send(addr, subject, body)
        for c in cases:
            store.event(c["id"], "notify", f"{'Approval request emailed' if ok else 'Approval request queued (email off)'}"
                                           f" to {person}")
        sent[person] = [c["id"] for c in cases]
        sent_already.update(c["id"] for c in cases)
    store.put("notified_cases", sorted(sent_already))
    return sent


def notify_escalation(tenant: Tenant, store: Store, case: dict) -> None:
    approvers = (case["data"].get("approver") or {}).get("approvers", [])
    for a in approvers:
        addr = _people(tenant).get(a.get("person") or "")
        if not addr:
            continue
        ok = _send(addr, f"[Aurora] Escalation: {case['id']} — supplier has not replied",
                   f"Hello,\n\nThe supplier did not answer our request or the reminder for:\n\n"
                   f"{_line(tenant, case)}\n\nPlease call them or choose another option in Launch Control.\n\n— Aurora")
        store.event(case["id"], "notify", f"Escalation {'emailed' if ok else 'queued'} to {a['person']}")
