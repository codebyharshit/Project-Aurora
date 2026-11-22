# Aurora — Operating Rules

When the agents act alone, when they ask a person, and who that person is. Describes what the code does (`backend/aurora/`). Customer specifics come from the customer's documents and `tenants/<customer>/tenant.yaml`.

## 1. Triggers

| Trigger | What happens | Person needed? |
|---|---|---|
| Every 60 s: new/changed file at the customer | Downloaded, read once (cached by SHA-256), whole pipeline re-runs | No |
| Supplier reply in the inbox (case tag `[C-xxxx]` or same email thread) | Negotiation / tracking agent handles it | Only outside the mandate |
| Unsolicited email from outside | Saved as a document → read → triaged like any file | If it becomes a case |
| Timer expires (supplier silent) | One reminder on the same thread, then escalation | Escalation goes to the approver |
| A person approves or decides | Agents carry it out; the plan updates | That is the human step |

Re-running without new data changes nothing; human decisions, mandates, negotiations, tracking and investigations survive every refresh. A problem that disappears retires its case; if it comes back, the case reopens.

## 2. Autonomy tiers (Agent Operating Procedures)

| Tier | Agents alone | The person | Examples |
|---|---|---|---|
| **Observe** | Read, reconcile, plan, rank, correct the *planning view* (never the ERP) | — | Reading scans, the 80,000 vs 8,000 art-book receipt |
| **Ask** | Prepare a question that commits the company to nothing | One click "let the agent ask" | Ask Hwaseong about the card balance; ask Karton to confirm an order |
| **Commit** | Options, prices, timing, draft, approver named | **The policy's approver approves** | Accept Karton's art books (Paul), sort the statue lot (Maren + Daniel), collect the container (Katrin) |
| **Never** | Flag and explain | Verifies through a known contact | Payments, bank-detail changes, contract changes |
| **Review** (new kind of problem) | Investigator investigates with tools, proposes options and a playbook | **Decides**; can save the decision as a playbook | Rare-earth export licence, Boise Incoterms hold, Karton shutdown |

Asking is free, committing needs the right person, money and bank details are never automatic.

**Earned autonomy:** each approval is counted per playbook; after 3 approvals without edits the approver is offered "do this automatically next time" (only the approver can switch it; *never* stays never).

## 3. Who decides (from the customer's own policy)

| Action | Rule | Soony |
|---|---|---|
| Purchase / accept an offer | Lowest role whose limit is above the value | Buyer < €50k (Paul Winter, P&P) · Category Lead < €500k · Head of Procurement < €2M · CPO < €5M · CPO+CFO above |
| Dock slot | Site lead (deputy) | Katrin Jansen (Raj Patel) |
| Concession / release | Roles named in the inspection report or release policy | Supplier Quality Lead + Category Lead |
| Supplier release extension | Category Lead + Supplier Quality, once, ≤ 90 days | — |
| **Role vacant** | Exception role, recorded as stand-in | Category Lead Collector's vacant until 23 Nov → Dr. Maren Vogt |
| Last word on what ships | Role named in the memo | Quality & Compliance |
| Ask/tracking work | The PO's buyer, the category buyer, or the Logistics Planner | Felix (game cards), Mei Lin (collector's items), Paul (packaging), Raj (tracking) |

## 4. Goal, ranking and "why"

- **Goal:** every pre-ordered customer served; Collector's 0% shortfall, Standard ≤ 2% of launch (Felix: "1–2% delay is OK if pre-orders are served"); value per missed unit configured (€149 Collector's, €12 Standard — to confirm with the Head of Procurement).
- **Verdict:** "on time" = every product within its tolerance.
- **Options** come from the data (offers in supplier documents, cargo at port, sortable rejected lots, priority reallocation); each is checked against its **last useful moment**; a late option shows its **partial** gain.
- **Ranking:** euros at risk per hour to the last useful moment; trade-offs shown ("+3,750 Collector's / −3,750 Standard because shared parts go to Collector's first").
- **Every case carries a `why`:** goal served · protects € vs costs € · the policy rule and approver (with stand-in) · evidence count · whether it touches the deadline.

## 5. Supplier conversations: chasing and negotiation

**Mandate:** when the approver approves, they authorise: quantity, needed-by time, budget up to the approved cost + 10% (never above their own limit), minimum worthwhile benefit (half the approved gain).

**Every reply:** AI reads it (any language: confirm / counter / split deliveries / price / question / refusal / waybill) → code evaluates (customers still served per delivery tranche, on time, within budget) → rules decide → AI writes in the supplier's language on the same thread.

| Move | When |
|---|---|
| Accept | Within budget and worth it (incl. late-but-useful) |
| Counter | Saves too little → split delivery / earlier loading |
| Answer | A question, from case data |
| Escalate | Price above the mandate, or no deal after 3 agent rounds |
| Walk away | Supplier refuses → option leaves the plan, a person picks the next one |

Never reveals the budget ceiling, internal values or internal receipt numbers; never promises payment beyond the offer or contract changes.

**After agreement:** *Agreed* → waits for the waybill (one reminder) → *In transit* → *Delivered* only when the goods receipt appears in the data; not received by expected time + 2 h → escalation. A supplier who changes the deal after agreement sends the case back to a person.

**Test mode:** `AURORA_SUPPLIER_EMAIL_OVERRIDE` redirects every supplier email to one address. Local development uses `AURORA_SEND=0` (nothing sent) and `AURORA_BACKGROUND=0` (only one instance reads the inbox).

## 6. Notifications ("not a lot of notifications")

One ranked inbox per person; one digest per person per run, only for decisions *they* must take; never twice for the same case; one escalation per case; problems that don't touch the deadline go to the daily overview, not to anyone's inbox.

## 7. Unknown problems and learning

Generic detectors + the AI Risk Triage flag anything that contradicts, blocks or changes supply (documents, news, emails) → no playbook matches → **Investigator** (tool-using: plan, parts, suppliers, documents, what-ifs, approvers, open cases) → impact, root cause, options with approvers, recommendation, questions → the person decides → **save as playbook** (`tenants/<customer>/playbooks_learned.yaml`) → the next similar problem follows those steps.

## 8. Data safety

The ERP is never changed (corrections live in the planning view with evidence, offered as proposed corrections). A document-vs-ERP difference that looks like a number-format misread, or low reading confidence, is flagged for review, not applied. Every number shows its source (ERP, document, supplier email, configured assumption). The deployed API requires an access key; customer data never goes to git.
