# FunnelTrace

AI lead-triage workflow: multi-channel intake, LLM scoring with reasoning, dedup, human-approved follow-up drafts, HubSpot sync, and a live decision trace.

Status: scaffolding. Architecture, run instructions and eval numbers will be added as they exist.

## Backend quick start

```bash
docker compose up -d db                      # Postgres on localhost:5433
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                         # fill in keys as needed
DATABASE_URL=postgresql://funneltrace:funneltrace@localhost:5433/funneltrace .venv/bin/python -m funneltrace.db   # apply migrations
.venv/bin/pytest                             # default suite, no network
```

DB-backed tests are opt-in: set `FUNNELTRACE_TEST_DATABASE_URL` to a scratch database (it drops and recreates the `public` schema).
