# Aurora · Keep the Line Running

**Your ERP says you're fine. Your paperwork says you're not.** Aurora is a team of specialised AI agents that finds the gap, prices it against your next deadline, and closes it within your own rules and with your approval: it reads every document (scans, handwriting, Korean/Polish/Chinese PDFs), plans backwards from the deadline, routes each decision to the one person your policy names, emails and **negotiates** with suppliers, and tracks the goods until they arrive.

Built at START Hack Munich 2026. First customer: **Soony** — Grand Heist 6 launch, trucks leave Sunday 20:00.

## What it does for Soony (live, on the real data)

| | ERP says | Reality (paperwork) | With 3 approvals (€18,840) |
|---|---|---|---|
| Collector's (11,700 to pack) | 100% | 91.8% of launch | **100%** |
| Standard (38,000 to pack) | 100% | 95.0% of launch | **98.9%** (6,800 follow later, within the 2% tolerance) |

Found from the raw files, nothing hardcoded (see [`docs/EVAL.md`](docs/EVAL.md), 21/21): an art-book receipt booked as 80,000 that the delivery note corrects by hand to 8,000; a statue lot that failed inspection but counts as usable; 28,000 of 48,000 game cards flown (Korean notice); a container waiting at the port while the tracker says "in transit"; a banned sleeve revision in stock and on a supplier's confirmation; a wrong-part pallet in a warehouse remark; an expired supplier release; an order nobody confirmed from a supplier with a shutdown; new problems like a rare-earth export licence and an Incoterms hold, investigated by a tool-using agent.

Proven end to end with real email: approve → Polish email to the supplier → counter-offer read (split delivery) → agent counters within the mandate → supplier accepts → waybill → in transit.

## How it works

Goal → process → agents → people. One specialised agent per business task on Soony's seven process steps (Order · Confirm · Ship · Track · Receive · Pack · Sell). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the rules for autonomy and human-in-the-loop in [`docs/OPERATING_RULES.md`](docs/OPERATING_RULES.md).

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env            # LIO_TOKEN (data portal), OPENAI_API_KEY, GMAIL_USER, GMAIL_APP_PASSWORD, …
cd backend
../.venv/bin/python -m aurora.cli pull          # download the customer's files
../.venv/bin/python -m aurora.cli extract-all   # read every document once (cached)
AURORA_SEND=0 ../.venv/bin/uvicorn aurora.api:app --port 8000   # AURORA_SEND=0: nothing is emailed
cd ../frontend && npm install && npm run dev    # http://localhost:3000
../.venv/bin/python ../backend/scripts/eval.py  # eval scorecard → docs/EVAL.md
```

## Onboard another company

Create `tenants/<company>/tenant.yaml` (sources, deadline, products and priorities, tolerances, people), point it at their files and policy documents, run the pipeline, and confirm the Onboarding agent's proposal on `/setup`. No code changes.

## Deploy

Backend: `Dockerfile` (always-on host with a volume at `/app/data/state`, e.g. Railway; set the variables from `.env.example`, incl. `AURORA_ACCESS_KEY`). Frontend: Vercel with `NEXT_PUBLIC_API_URL`; open it once with `?key=<access key>`.

## Repo

`backend/aurora/` agents, planner, policy, API · `tenants/soony/` customer configuration · `frontend/` launch room UI · `docs/` architecture, operating rules, eval. Customer data and secrets are not in git.

Team LUMI: Harshit Agarwal, Zorawar Singh, Mikail Ugur, Jakub Walentek, Antonina Begacheva.
