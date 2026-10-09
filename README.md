# FunnelTrace

AI lead-triage workflow: multi-channel intake, LLM scoring with reasoning, dedup, human-approved follow-up drafts, HubSpot sync, and a live decision trace.

Status: scaffolding. Architecture, run instructions and eval numbers will be added as they exist.

## Backend quick start

```bash
docker compose up -d db                      # Postgres on localhost:5433
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                         # fill in keys as needed
.venv/bin/python -m funneltrace.db              # apply migrations (reads .env)
.venv/bin/pytest                             # default suite, no network
```

## Frontend quick start

```bash
cd backend && .venv/bin/uvicorn funneltrace.api:app --port 8000   # API
cd frontend && npm install && npm run dev                           # UI on http://localhost:3000
```

Open the UI, fire a demo lead, watch the trace, then approve the draft in the inbox.

DB-backed tests are opt-in: set `FUNNELTRACE_TEST_DATABASE_URL` to a scratch database (it drops and recreates the `public` schema).
