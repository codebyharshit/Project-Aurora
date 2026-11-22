# Aurora — Architecture

> **Your ERP says you're fine. Your paperwork says you're not.** Aurora's agents find the gap, price it against your next deadline, and close it within your own rules and with your approval.

Aurora is a team of specialised AI agents for companies with a **hard date** (a launch, a start of production, a season) that depends on outside suppliers. Soony's Grand Heist 6 launch (trucks leave Sunday 20:00) is the first customer and the live demo. **Nothing in the code is specific to Soony**: everything about a customer lives in `tenants/<customer>/tenant.yaml` and in the customer's own documents.

## 1. Goal → process → agents → people

```
GOAL      Ship Grand Heist 6 by Sun 20:00 · Collector's 0% shortfall · Standard ≤ 2% · rank by € at risk per hour
            (proposed by the Onboarding agent from Soony's memo + notes, confirmed by a human, stored as config)
PROCESS   ① Order ─ ② Confirm ─ ③ Ship ─ ④ Track ─ ⑤ Receive ─ ⑥ Pack ─ ⑦ Sell
          SAP       email/PDF    4 carriers  spreadsheet  paper scans  pack-out log  deadline   (only ① and ⑥ had a system)
AGENTS    one specialised agent per business task on every step (Lio's model: matching · chasing · exception handling)
PEOPLE    each decision goes to the one person the customer's policy names; everyone sees only their own work
```

- **The goal is a first-class object** (`backend/aurora/goal.py`, `GET /api/goal`). It drives the verdict ("on time within tolerance?"), the ranking of decisions, and the `why` on every case: *which goal it serves, what it protects vs costs, which rule applies, how much evidence*.
- **Ranking:** euros at risk per hour until each fix's *last useful moment*; the priority product's copies weigh more (customer weights from config); items that don't touch the deadline rank 10× lower.

## 2. The loop

```
 files / mailbox ─▶ Data Intake ─▶ Document Reader ─▶ World (ERP tables + facts from paper, each with source + confidence)
                                                          │
          Launch Planner: ERP view vs reality, worked backwards from the deadline, what-ifs, last useful moment
                                                          │
   detectors (matching): Stock Truth · Order Confirmation · Release Gate · Tracking   +   Risk Triage (AI, anything new)
                                                          ▼
          Case Manager ── known type → playbook (AOP) ── Sourcing (options) ── Approvals (who decides) ── Decision Copilot (why)
                       └─ new type  → Investigator (tool-using agent) → human decides → saved as a new playbook
                                                          ▼
          one notification to the named approver ── Approve ── Supplier Chaser (email, any language)
                                                          ▼
          Negotiation agent (accept · counter · answer · escalate within the mandate) ── Tracking (waybill → in transit → delivered)
```

Agents share state through the **case store** (SQLite): status, evidence, options, mandate, negotiation, tracking, timeline, emails. No single long prompt; each AI call gets only what it needs. Numbers, approvals and money decisions are deterministic code; language, reading and judgement are AI.

## 3. Agents (business-use-case vocabulary)

| Agent | Step | Task | Kind |
|---|---|---|---|
| Data Intake Agent | all | Watches sources every minute; understands unknown files (Schema Mapper) | AI + code |
| Document Reader Agent | ②⑤ | Scans, handwriting, PDFs in any language → facts with confidence | AI |
| Order Confirmation Agent | ①② | Supplier confirmation vs PO: quantity, date, price, revision; orders nobody confirmed | code |
| Stock Truth Agent | ⑤ | Paper vs ERP: wrong receipts, warehouse remarks (AI), goods without an order | code + AI |
| Release Gate Agent | ⑤⑥ | Rejected lots, banned revisions, expired supplier releases | code |
| Tracking Agent | ④ | Short shipments, cargo at port, silent carriers, tracker vs ERP, deliveries | code + AI |
| Launch Planner Agent | ⑥⑦ | Backwards plan, ERP view vs reality, what-ifs | code |
| Sourcing Agent | ①③ | Options priced and ranked by customers protected per euro, partial gains if late | code |
| Approvals Agent | ① | Parses policy + org chart; routes to the right available person (stand-ins for vacancies); notifies once | AI + code |
| Supplier Chaser Agent | ②③ | Emails in the supplier's language, reminds once, escalates, reads every reply | AI |
| Negotiation Agent | ③ | Reads terms → evaluates against plan + mandate → accept/counter/answer/escalate/walk away | AI + rules |
| Investigator | ⑦ | Tool-using agent for unknown problems: plan, parts, suppliers, documents, what-ifs, approvers → options + draft playbook | AI agent |
| Decision Copilot | ⑦ | One-sentence headline + goal line per case (template from verified numbers; AI only for new problem types) | AI + code |
| Onboarding Agent | setup | Proposes goal, rules, autonomy from the customer's files; a human confirms each section | AI |

Live registry with activity: `GET /api/agents`.

## 4. Product vs customer configuration

| Product (code, same for everyone) | Per customer (data) |
|---|---|
| Reading any document/format/language; canonical data model; Schema Mapper | Sources, column synonyms, learned mappings |
| Generic detectors and the AI catch-all | Thresholds |
| Backwards planner, what-ifs, partial gains | Deadline, products, priorities, tolerances, value per unit, shifts |
| Policy engine (limits, roles, vacancies, exceptions) | The customer's own policy documents and org chart |
| Playbook library (Agent Operating Procedures) | Enabled playbooks, autonomy per playbook, learned playbooks |
| Chaser, negotiation, tracking, notifications | Sender identity, people directory, mandate tolerance, timeouts |

**Onboarding a new company:** connect sources → Schema Mapper and Document Reader understand the data → Onboarding agent proposes the goal → policy parsed into rules → autonomy defaults → a human confirms each step (`/setup`).

## 5. Interfaces

- **Launch room (`/`)** — Soony-branded, *View as* a team member: *Everyone* sees the verdict, three numbers, the process strip, who must act and what the agents are doing; a *person* sees only their inbox (approve · decide · agents handle alone) with one-click actions.
- **AI team (`/team`)** — goal → process → agents with live activity, autonomy ladder, playbooks.
- **Setup (`/setup`)** — goal first, then rules, autonomy, data, sources; each proposed by an agent and confirmed by a person.
- **Email** — supplier conversations (with negotiation) and one approval notice per person.

## 6. Tech

Python · FastAPI · SQLite · pandas · OpenAI (default; provider-neutral layer, Claude supported) · Gmail SMTP/IMAP · Next.js + Tailwind. Deployed: backend on Railway (Docker, persistent volume, access key), frontend on Vercel. Eval: `backend/scripts/eval.py` → `docs/EVAL.md`.
