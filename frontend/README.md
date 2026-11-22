# Soony · Grand Heist 6 launch room (Aurora frontend)

Next.js (App Router) + TypeScript + Tailwind. Soony-branded (Soony blue primary, "powered by Aurora"), with a
**View as** switch in the header so every team member sees only their own items.

- **Home · Everyone**: one verdict card (sentence + Collector's / Standard now → with approvals + decisions waiting),
  the seven-step process strip (① Order … ⑦ Sell: system today, had a system / now an agent, open cases), and two
  columns: *Who must act* (click a name → their view) and *Agents at work*.
- **Home · a person**: a headline sentence ("Paul, 1 decision needs you. Approving it protects …"), then groups:
  Approve (compact decision rows with a goal line and one "Approve as …" button), Decide (Investigator summary +
  decision form), Agents handle alone ("Let the agent ask"), Agents working for you, Done & watching.
- **AI team** (`/team`): the goal every agent serves, the process strip, one card per specialised agent grouped by
  process step (Lio equivalent, trigger, what it does alone, activity, its cases), and the autonomy ladder.
- **Setup** (`/setup`): goal first, then rules, autonomy, data, sources; "n of 5 confirmed".

Case details open in a drawer, or as a page at `/cases/<id>`; dense data sits behind "Details".

## Run

```bash
npm install
npm run dev          # http://localhost:3000
```

The backend must be running (default `http://localhost:8000`). To point elsewhere:

```bash
NEXT_PUBLIC_API_URL=https://aurora-api.example.com npm run dev
```

Production: `npm run build && npm run start`.

Data refreshes every 5 s (SWR). Demo viewport is 1280×800.

## What calls what

| UI | Endpoint |
| --- | --- |
| Header, verdict card, goal, rules, corrections | `GET /api/overview` |
| Queue, who-must-act, person view (fallback) | `GET /api/cases` |
| View-as list, who-must-act | `GET /api/people` |
| Person view (preferred; falls back to `/api/cases` + `owners`) | `GET /api/people/{name}/inbox` |
| Process strip, AI team page | `GET /api/agents` |
| Setup page | `GET /api/setup` |
| Case drawer / page | `GET /api/cases/{id}` |
| Evidence (scans inline, PDFs preview/open) | `GET /api/files/{path}` |
| Approve → confirm popover | `POST /api/cases/{id}/approve` (may send a real supplier email) |
| "Let Aurora do this automatically next time?" | `POST /api/playbooks/{id}/auto?on=true` |
| Needs your judgement → Record decision | `POST /api/cases/{id}/decide` |
| Check for updates | `POST /api/poll` |


## Layout

- `src/lib/types.ts`: response types, taken from the live API
- `src/lib/api.ts`: SWR hooks, POST helpers, `fileUrl`
- `src/lib/format.ts`, `derive.ts`, `evidence.ts`: formatting (Hamburg time), derived lookups, evidence classification
- `src/lib/viewAs.ts`, `useName.ts`: who is looking (localStorage `aurora.viewAs`, also `?as=Name`), prefills forms
- `src/lib/people.ts`, `agents.ts`: owners / inbox derivation and process-step fallbacks when the API is older
- `src/components/`: `LaunchControl` (home), `Header` + `ViewAs` + `Brand`, `VerdictCard` + `DeadlineTimeline`,
  `ProcessStrip`, `WhoMustAct`, `AgentsFeed`, `PersonView` + `DecisionRow`, `GoalLine`, `TeamPage`, `SetupPage`,
  `Story` (facts, benefit, next steps, evidence viewer), `ApproveButton`, `Confirmation`, `Flight`, `CaseDrawer`,
  `CaseDetail`, `Sections` (decide form, rules, corrections), `Investigation`, `Evidence`, `ui`

€ figures are estimates from configured value-per-copy assumptions; the UI says so on hover.
