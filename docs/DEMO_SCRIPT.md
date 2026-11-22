# Demo script (3 min pitch + live)

**Story:** goal → process → agents → people → live negotiation. Start the demo early; slides are support.

## Before going on stage (10 min)
- Demo state reset (all decisions open): `POST /api/admin/reset-demo` with the access key.
- Two tabs: Launch room as **Everyone**, and as **Paul Winter**.
- A teammate has the supplier inbox open (test mode: supplier emails go to harshitagrawal048@gmail.com) with the two replies below ready.
- Say once: "The plan is as of Soony's latest status file, Saturday 20:50."

## 0:00 — The problem (30 s)
"Soony launches Grand Heist 6 on Sunday 20:00. Their ERP says 100% of everything ships. Their own paperwork says otherwise. On Saturday, Felix — their senior buyer — told us: *data is a mess, we find out at the dock, and a 1–2% delay is fine as long as pre-orders are served.* So we built a team of agents with one goal: every Collector's copy and at least 98% of Standard on the trucks."
→ Launch room, Everyone: verdict "Not yet", Collector's 91.8% → 100%, Standard 95.0% → 98.9%, "3 approvals, €18,840".

## 0:30 — Process and agents (40 s)
"Soony's process has seven steps; only two had a system. Now every step has a specialised agent: one agent per business task."
→ Process strip → AI team page. Point at: **Document Reader** (299 documents, 5 languages, handwriting), **Stock Truth** (the art book booked as 80,000, delivery note says 8,000 — show the scan), **Order Confirmation** (a supplier confirmed a banned revision; an order nobody confirmed from a supplier with a shutdown), **Tracking** (container at the port, the spreadsheet still says in transit).
"Nothing is hardcoded: 21 of 21 checks re-found from raw files."

## 1:10 — People (35 s)
"Each person sees only what needs them." → View as **Paul Winter**: one card. Read the goal line: *serves Collector's first · protects €513k for €16.8k · within Paul's €50k buyer limit (PP-07) · 3 documents.* → **Approve as Paul Winter**.
"The Chaser emails Karton Nowak in Polish. The Negotiation agent may agree up to +10%, never above Paul's limit."
→ View as **Dr. Maren Vogt**: "stand-in for the vacant Category Lead" — the org chart says Arjun only starts Monday. One new problem: the Investigator used 17 tool calls on the rare-earth export licence and concluded it doesn't touch Sunday → decide → save as playbook.

## 1:45 — Live negotiation (45 s)
Teammate replies as Karton (counter):
> Niestety z powodu przestoju możemy dziś załadować tylko 1 500 szt. Pozostałe 6 500 szt. w poniedziałek 23.11. Cena bez zmian.

→ within a minute: the agent **counters** in Polish ("ship the 1,500 now, the rest before Sunday 11:26, or load earlier") — never revealing the budget.
Teammate replies (accept + waybill):
> OK, wyślemy całe 8 000 szt. dziś o 23:00. CMR WT-2611-88413, przyjazd ok. 08:00.

→ case **Agreed → On the way**, Collector's moves up. Verdict turns green once the other approvals are in: *On time — 6,800 Standard copies follow later (1.1%, within 2%).*
(If mail is slow: open the case — the email thread and mandate are there; press "Check for updates".)

## 2:30 — The business (30 s)
"Setup page: the Onboarding agent proposed Soony's goal from their own memo, parsed their approval policy, and mapped files nobody configured. A new customer is a new config folder, not a project. Every company with a hard date and outside suppliers — game and electronics launches, toys before Christmas, start of production in automotive, pharma launches — has a Soony weekend. Pricing: per active launch or season, plus a platform fee; the playbooks get better with every customer."

## Q&A cheat sheet
- *Hardcoded?* → `tenants/soony/tenant.yaml`, `docs/EVAL.md` (grep check for customer values in code: 0 hits).
- *What if it's wrong?* → every number has evidence; low confidence or format-suspect readings are flagged, not applied; the ERP is never changed; money decisions are deterministic code; commits need the policy's approver.
- *New data drop?* → watcher every minute; Schema Mapper understood new files (CSV → JSON switch, stock updates) with no code change; Risk Triage + Investigator for new problem types.
- *Why would Soony pay?* → 3 approvals protect ~€880k of refunded Collector's pre-orders for €18.8k; no IT project needed.
