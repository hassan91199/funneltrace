# FunnelTrace

AI lead-triage workflow: multi-channel intake, LLM scoring with reasoning, dedup, human-approved follow-up drafts, HubSpot sync, and a live decision trace.

Status: backend and UI built; architecture diagram and demo assets still to come.

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

## Eval

Ten locked leads (`backend/eval/test_set.py`, written before any scoring code) run in order through
the real app against real OpenAI, the HubSpot sandbox and Postgres, and each is graded on four
things: category, dedup, draft relevance and the CRM write. The default test suite never does this;
the harness itself is covered offline with fakes (`tests/test_eval_runner.py`).

```bash
cd backend
FUNNELTRACE_TEST_DATABASE_URL=postgresql://... .venv/bin/python -m eval.run   # wipes that scratch DB
```

Latest run (2026-10-09, `gpt-4o-mini` for scoring, drafting and judging; one run, n=10;
full per-event detail in `backend/eval/results/eval-20261009T222245Z.json`):

| Check | Result |
|---|---|
| Category correct | 10/10 |
| Dedup correct (7 distinct leads) | 10/10 |
| Draft relevant (LLM-judged, every checklist point met) | 9/10 |
| CRM write correct (action, lifecycle stage, verified in HubSpot) | 9/10 |
| Events passing all four | 8/10 |

Latency per event, in process, including the real OpenAI and HubSpot calls: intake to scored and
drafted averaged 3.4 s (median 3.2, max 5.5); approval including the HubSpot write averaged 2.0 s
(median 1.8, max 2.7).

What the two misses were, and what the numbers do not say:

- **#6 CRM write failed**: HubSpot rejected the fixture's `jason@rankboost-seo.example` as an
  invalid email, so no contact was written. The sync was recorded and traced as failed and the
  approval stood, as designed, but the adapter does not retry without the email.
- **#10 draft failed**: the draft did not propose scheduling the tune-up before summer.
- **The draft check is lenient.** The judge is the same model that wrote the drafts, and it passed
  #10's "references her earlier WhatsApp message" on little more than "Thanks for reaching out".
  Read 9/10 as an upper bound for merged-lead drafts.
- One run at default sampling: a rerun can differ. Ten events is a smoke-level sample, not a benchmark.
