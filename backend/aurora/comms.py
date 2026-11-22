"""Supplier Comms agent: drafts in the supplier's language, sends only after approval,
reads replies and turns them into facts on the case.

Sending is only reachable through `send_for_case`, which requires an approved action.
Without Gmail credentials, approved emails stay in the outbox as "ready to send".
"""
from __future__ import annotations

import email
import email.utils
import imaplib

import pandas as pd
import os
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import make_msgid

from aurora.agents import llm
from aurora.store import Store
from aurora.world import World

DRAFT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["subject", "body", "body_en", "language"],
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"},
                   "body_en": {"type": "string"}, "language": {"type": "string"}},
}

DRAFT_SYSTEM = """You write short, polite supplier emails for a procurement team.
Write in the supplier's preferred language, then give an English version in body_en.
Reference the supplier's own document (their offer, notice or order confirmation) and our PO number if
one exists. Never mention internal receipt, batch or case-analysis numbers, internal values or budgets.
Ask only what is needed to close the case.
Never promise payment, prices beyond what was offered, or contract changes.
Sign as the sender name given. No placeholders."""

REPLY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary_en", "confirmed", "confirmed_qty", "confirmed_time", "commitments", "new_risks", "needs_human"],
    "properties": {"summary_en": {"type": "string"}, "confirmed": {"type": "boolean"},
                   "confirmed_qty": {"type": ["number", "null"]}, "confirmed_time": {"type": ["string", "null"]},
                   "commitments": {"type": "array", "items": {"type": "string"}},
                   "new_risks": {"type": "array", "items": {"type": "string"}},
                   "needs_human": {"type": "boolean"}},
}


def supplier_contact(world: World, name_hint: str) -> dict | None:
    sup = world.t("suppliers")
    for s in sup.to_dict("records"):
        first = str(s.get("name", "")).split()[0].lower()
        if first and first in (name_hint or "").lower():
            return {"supplier_id": s["supplier_id"], "name": s.get("name"),
                    "email": s.get("contact_email") or s.get("contact_email_1") or s.get("email"),
                    "contact": s.get("contact_name"),
                    "language": s.get("preferred_language") or s.get("contact_language") or "en"}
    return None


def draft(world: World, case: dict, option: dict | None) -> dict:
    d = case["data"]
    hint = (option or {}).get("title", "") + " " + " ".join(d["signal"]["evidence"]) + " " + d["signal"]["summary"]
    contact = supplier_contact(world, hint)
    if not contact or not contact.get("email"):
        raise ValueError("No supplier contact found for this case")
    sender = world.tenant.cfg.get("comms", {}).get("sender_name", "Procurement")
    brief = (f"Supplier: {contact['name']} (contact {contact['contact']}, language {contact['language']}).\n"
             f"Customer: {world.tenant.cfg['display_name']}. Sender name: {sender}.\n"
             f"Case {case['id']}: {d['signal']['summary']}\n"
             f"Decision approved: {(option or {}).get('title', d.get('supplier_intent'))}\n"
             f"Goal: {d.get('supplier_intent') or 'Confirm the approved action and the timing.'}\n"
             f"Quantity: {(option or {}).get('qty')}. Needed before: {(option or {}).get('last_useful_moment', '')[:16]}.\n"
             f"Supplier's document to reference: {((option or {}).get('evidence') or d['signal']['evidence'] or [''])[0].split('/')[-1]}")
    out = llm.structured(system=DRAFT_SYSTEM, content=brief, schema=DRAFT_SCHEMA, role="exec", effort="low")
    out["subject"] = f"[{case['id']}] {out['subject']}"
    out["to"] = contact["email"]
    out["supplier"] = contact["name"]
    return out


def _configured() -> bool:
    if os.environ.get("AURORA_SEND") == "0":   # local testing: emails stay in the outbox
        return False
    return bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"))


def smtp_send(msg: EmailMessage) -> None:
    """Send through Gmail: STARTTLS on 587, then SSL on 465 (some hosts block one of them)."""
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
    except OSError:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(user, pw)
            s.send_message(msg)


def send_for_case(store: Store, case_id: str, message: dict, approved_by: str,
                  in_reply_to: str | None = None, parsed: dict | None = None) -> dict:
    """The only path that sends email. Requires a human approval recorded on the case."""
    if not approved_by:
        raise PermissionError("Supplier emails need an approval")
    if not _configured():
        store.add_message(case_id, "outbox", message["to"], message["subject"], message["body"], message["body_en"],
                          parsed=parsed)
        store.event(case_id, "comms", f"Email to {message['supplier']} ready to send (Gmail not configured)")
        return {"sent": False, "reason": "gmail_not_configured"}
    override = os.environ.get("AURORA_SUPPLIER_EMAIL_OVERRIDE")  # test mode: never reach the real supplier
    msg = EmailMessage()
    msg["From"] = os.environ["GMAIL_USER"]
    msg["To"] = override or message["to"]
    msg["Subject"] = message["subject"]
    msg["Message-ID"] = make_msgid(domain="aurora.local")
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(message["body"] + "\n\n---\n" + message["body_en"])
    try:
        smtp_send(msg)
    except (OSError, smtplib.SMTPException) as e:   # host blocks SMTP or Gmail refuses: keep it in the outbox
        store.add_message(case_id, "outbox", message["to"], message["subject"], message["body"], message["body_en"],
                          parsed=parsed)
        store.event(case_id, "comms", f"Email to {message['supplier']} ready but not sent (mail server unreachable: {e})")
        return {"sent": False, "reason": "smtp_unreachable"}
    store.add_message(case_id, "out", message["to"], message["subject"], message["body"], message["body_en"],
                      msg["Message-ID"], parsed)
    store.event(case_id, "comms", f"Email sent to {message['supplier']} ({msg['To']}"
                                  + (f", test mode instead of {message['to']}" if override else "") + f"), approved by {approved_by}")
    return {"sent": True, "message_id": msg["Message-ID"]}


def follow_up(store: Store, case: dict, text: str | None = None) -> dict | None:
    """One polite reminder on the same thread (covered by the original approval)."""
    sent = [m for m in store.messages(case["id"]) if m["direction"] == "out"]
    if not sent:
        return None
    first = sent[-1]
    approved_by = next((e["text"].split(":")[0].replace("Approved by ", "") for e in store.events(case["id"])
                        if e["actor"] == "human"), "")
    reminder = {"to": first["counterpart"], "supplier": first["counterpart"],
                "subject": "Re: " + first["subject"].removeprefix("Re: "),
                "body": (text or "Friendly reminder, we need your confirmation urgently.") + "\n\n> "
                        + first["body"].replace("\n", "\n> "),
                "body_en": text or "Reminder of the request below."}
    store.event(case["id"], "comms", "No reply yet: sending one reminder on the same thread")
    return send_for_case(store, case["id"], reminder, approved_by)


def poll_replies(store: Store) -> list[dict]:
    """Read new mail. Replies on a case go to the negotiation agent; any other mail from outside
    is saved as a document so the normal pipeline (reader + risk triage) picks it up."""
    if not _configured():
        return []
    from aurora.config import get_tenant
    tenant = get_tenant()
    me = os.environ["GMAIL_USER"].lower()
    seen = set(store.get("imap_seen", []))
    last_uid = int(store.get("imap_last_uid", 0))
    # Message-IDs we sent → case, so replies without the [C-xxxx] tag still find their case
    thread_map = {m["message_id"]: c["id"] for c in store.cases() for m in store.messages(c["id"])
                  if m["direction"] == "out" and m["message_id"]}
    found = []
    with imaplib.IMAP4_SSL("imap.gmail.com") as m:
        m.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
        m.select("INBOX")
        _, data = m.uid("search", None, f"UID {last_uid + 1}:*")   # only mail we have not seen
        for uid in data[0].split():
            if int(uid) <= last_uid:
                continue
            last_uid = max(last_uid, int(uid))
            if uid.decode() in seen:
                continue
            _, raw = m.uid("fetch", uid, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", ""))))  # decode =?UTF-8?Q?...?=
            del msg["Subject"]
            msg["Subject"] = subject
            seen.add(uid.decode())
            sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            if sender.split("+")[0] == me.split("@")[0] or sender == me:
                continue  # our own notifications (plus-addressed) and sent copies
            body = _text_of(msg)
            tag = re.search(r"\[(C-\d{4})\]", msg.get("Subject", ""))
            refs = (msg.get("In-Reply-To", "") + " " + msg.get("References", "")).split()
            cid = tag.group(1) if tag and store.case(tag.group(1)) else next((thread_map[r] for r in refs if r in thread_map), None)
            if cid:
                found.append(handle_case_reply(tenant, store, cid, msg, body))
            else:
                inbox = tenant.state_dir / "inbox"
                inbox.mkdir(exist_ok=True)
                name = f"{datetime.now():%Y%m%d-%H%M%S}_{uid.decode()}.txt"
                (inbox / name).write_text(f"From: {msg.get('From')}\nDate: {msg.get('Date')}\n"
                                          f"Subject: {msg.get('Subject')}\n\n{body}")
                found.append({"inbox": name, "from": sender})
    store.put("imap_seen", sorted(seen))
    store.put("imap_last_uid", last_uid)
    return found


def handle_case_reply(tenant, store: Store, cid: str, msg, body: str) -> dict:
    from aurora import negotiation as neg
    case = store.case(cid)
    d = case["data"]
    mandate = d.get("mandate")
    option = next((o for o in d.get("options", []) if o["id"] == d.get("recommended_option")), None)
    world = World.load(tenant, read_documents=False)
    from aurora.planner import LaunchPlanner
    planner = LaunchPlanner(world)
    # read "today/tonight" on the plan's clock, so supplier times and deadlines compare like for like
    terms = neg.read_terms(body, msg.get("Subject", ""), planner.as_of.isoformat(timespec="minutes"))
    store.add_message(cid, "in", msg.get("From", ""), msg.get("Subject", ""), body, terms["summary_en"],
                      msg.get("Message-ID", ""), terms)
    if case["status"] in ("AGREED", "IN_TRANSIT"):
        return track_reply(tenant, store, case, terms)
    ev = None
    if mandate and option:
        pid = max(option["copies_gained"], key=lambda k: option["copies_gained"][k])
        rate = next(p["rate_per_hour"] for p in tenant.cfg["products"] if p["id"] == pid)
        qty_per = world.bom(pid).get(d["impact"].get("part"), 1)
        buf = float(tenant.cfg.get("receiving_buffer_hours", 2))
        ev = neg.evaluate(terms, mandate, rate, qty_per, lambda t: planner.hours_left(t + timedelta(hours=buf)))
    move, reason = neg.decide_move(terms, ev, neg.agent_rounds(store, cid))
    store.event(cid, "negotiator", f"Supplier: {terms['summary_en']} → {move.replace('_', ' ')}: {reason}",
                {"terms": terms, "evaluation": ev})
    if move in ("accept", "counter", "answer", "walk_away"):
        context = {"our_terms": neg.safe_terms(mandate), "supplier_terms": terms,
                   "copies_we_can_still_use": (ev or {}).get("copies_saved"),
                   "approved_option": (option or {}).get("title"),
                   "supplier_document": ((option or {}).get("evidence") or [""])[0].split("/")[-1],
                   "sender": tenant.cfg.get("comms", {}).get("sender_name"),
                   }
        draft_ = neg.draft_move(move, context)
        reply = {"to": email.utils.parseaddr(msg.get("From", ""))[1], "supplier": msg.get("From", ""),
                 "subject": "Re: " + msg.get("Subject", "").removeprefix("Re: "), **draft_}
        send_for_case(store, cid, reply, (mandate or {}).get("approved_by", "mandate"),
                      in_reply_to=msg.get("Message-ID"), parsed={"negotiation": move})
    if move == "accept":
        expected = (ev or {}).get("arrival_at") or (option or {}).get("arrival_at")
        store.update_data(cid, tracking={"agreed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                         "expected_arrival": expected, "qty": (ev or {}).get("qty"),
                                         "supplier_id": _supplier_id(tenant, option),
                                         "supplier_name": (option or {}).get("title", "").replace("Accept ", "").split(" offer")[0],
                                         "part": d["impact"].get("part"),
                                         "shipment_reference": terms.get("shipment_reference")})
        store.set_status(cid, "AGREED", "negotiator", f"Agreed: {reason}. Tracking until the goods are received.")
        if not terms.get("shipment_reference"):
            minutes = tenant.cfg.get("comms", {}).get("demo_reply_timeout_minutes", 20)
            store.add_timer(cid, "await_waybill", (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat())
    elif move in ("counter", "answer"):
        store.set_status(cid, "AWAITING_SUPPLIER", "negotiator", reason)
        minutes = tenant.cfg.get("comms", {}).get("demo_reply_timeout_minutes", 20)
        store.add_timer(cid, "await_reply", (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat())
    else:  # escalate or walk away: the decision goes back to a human with fresh numbers
        store.put("committed_actions", [a for a in store.get("committed_actions", []) if a != d.get("recommended_option")])
        store.update_data(cid, negotiation={"terms": terms, "evaluation": ev, "reason": reason, "move": move})
        store.set_status(cid, "AWAITING_APPROVAL" if move == "escalate" else "AWAITING_HUMAN_REVIEW",
                         "negotiator", reason)
        from aurora.notify import notify_escalation
        notify_escalation(tenant, store, store.case(cid))
    return {"case": cid, "move": move, "reason": reason}


def _supplier_id(tenant, option: dict | None) -> str | None:
    world = World.load(tenant, read_documents=False)
    c = supplier_contact(world, " ".join([(option or {}).get("title", "")] + ((option or {}).get("evidence") or [])))
    return (c or {}).get("supplier_id")


def track_reply(tenant, store: Store, case: dict, terms: dict) -> dict:
    """After agreement the conversation is about shipping: record references and news."""
    cid = case["id"]
    tracking = dict(case["data"].get("tracking") or {})
    if terms.get("shipment_reference") and not tracking.get("shipment_reference"):
        tracking["shipment_reference"] = terms["shipment_reference"]
        if terms.get("arrival_at"):
            tracking["expected_arrival"] = terms["arrival_at"]
        store.update_data(cid, tracking=tracking)
        store.set_status(cid, "IN_TRANSIT", "tracker", f"Shipment reference {terms['shipment_reference']} received; "
                                                      f"watching receipts for the delivery")
        # if it has not arrived by the expected time (+ buffer), escalate
        if tracking.get("expected_arrival"):
            due = datetime.fromisoformat(tracking["expected_arrival"]) + timedelta(hours=2)
            store.add_timer(cid, "await_delivery", due.isoformat())
        return {"case": cid, "move": "track", "reason": "Shipment reference recorded"}
    store.event(cid, "tracker", f"Supplier update: {terms['summary_en']}")
    if terms["intent"] in ("refusal", "counter_offer") or terms.get("new_risks"):
        store.set_status(cid, "AWAITING_HUMAN_REVIEW", "tracker", "Supplier changed something after agreement")
        from aurora.notify import notify_escalation
        notify_escalation(tenant, store, store.case(cid))
    return {"case": cid, "move": "note", "reason": terms["summary_en"][:120]}


def check_deliveries(tenant, store: Store, world: World) -> list[str]:
    """Close agreed cases only when the goods are booked in (new goods receipt after agreement)."""
    done = []
    r = world.t("receipts")
    for c in store.cases():
        if c["status"] not in ("AGREED", "IN_TRANSIT"):
            continue
        t = c["data"].get("tracking") or {}
        if not t.get("part"):
            continue
        hits = r[(r["part_id"] == t["part"]) & (r["gr_date"] >= pd.Timestamp(t["agreed_at"][:10]))]
        if t.get("supplier_id"):
            hits = hits[hits["supplier_id"] == t["supplier_id"]]
        if len(hits):
            gr = hits.iloc[-1]
            store.update_data(c["id"], tracking={**t, "received": {"gr_number": str(gr["gr_number"]),
                                                                   "qty": float(gr["qty_received"]),
                                                                   "delivery_note": gr.get("delivery_note")}})
            store.set_status(c["id"], "DELIVERED", "tracker",
                             f"Goods received: receipt {gr['gr_number']}, {int(gr['qty_received']):,} units")
            opt = c["data"].get("recommended_option")
            store.put("committed_actions", [a for a in store.get("committed_actions", []) if a != opt])
            done.append(c["id"])
    return done


def _text_of(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="replace")
        return ""
    return msg.get_payload(decode=True).decode(errors="replace")
