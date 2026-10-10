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

## CI parity

GitHub Actions (`.github/workflows/ci.yml`) runs exactly these commands, so a green local run means a
green CI run:

```bash
docker build -t funneltrace-backend backend && docker run --rm funneltrace-backend     # lint + default suite
docker build -t funneltrace-frontend frontend && docker run --rm funneltrace-frontend  # typecheck, lint, tests, build

# DB-backed tests too (CI does this against a Postgres service; locally use the compose db):
docker run --rm --network host \
  -e FUNNELTRACE_TEST_DATABASE_URL=postgresql://funneltrace:funneltrace@localhost:5433/funneltrace_test \
  funneltrace-backend
```

The backend image can also serve the API (`docker run ... funneltrace-backend serve`, with the env from
`backend/.env.example`).

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

Three runs so far, all kept in `backend/eval/results/` (JSON has every draft, verdict and quote).
The scorer and drafter were `gpt-4o-mini` throughout; each row says what changed before it.

| Run | What changed | Category | Dedup | Draft | CRM | All four |
|---|---|---|---|---|---|---|
| 1 (`20261009T222245Z`) | First run. Judge was the same model as the drafter. | 10/10 | 10/10 | 9/10 | 9/10 | 8/10 |
| 2 (`20261010T144210Z`) | Fixture email fixed; drafting prompt made follow-up aware; judge now `gpt-4.1` and must quote the draft | 10/10 | 10/10 | 6/10 | 10/10 | 6/10 |
| 3 (`20261010T144427Z`, latest) | Judge fixed: "does not" points need no quote, quotes must be contiguous | 10/10 | 10/10 | 5/10 | 10/10 | 5/10 |

Latency per event in the latest run, in process, including the real OpenAI and HubSpot calls: intake
to scored and drafted averaged 2.5 s (median 2.5, max 2.8); approval including the HubSpot write
averaged 1.8 s (median 1.7, max 2.3). Across the three runs the intake averages were 3.4, 2.9 and 2.5 s.

Then a controlled experiment on the weak spot, the drafts: only the drafting model changed (scorer
`gpt-4o-mini` and judge `gpt-4.1` held fixed), three runs each, `python -m eval.run --runs 3
[--draft-model ...]`. Summaries: `eval-20261010T150101Z-x3.md` (baseline) and
`eval-20261010T150548Z-x3.md` (`gpt-5.4-mini`); every run's JSON is alongside.

| Drafter | Draft relevant, per run | Mean | Range | Mean s per event (intake to approval) |
|---|---|---|---|---|
| `gpt-4o-mini` (baseline) | 6, 6, 4 of 10 | 5.3 | 4–6 | 5.2, 5.7, 5.0 |
| `gpt-5.4-mini` | 5, 7, 9 of 10 | 7.0 | 5–9 | 5.4, 5.3, 5.4 |

Category, dedup and the CRM write were 10/10 in all six runs. The stronger drafter looks better on
average at about the same latency, but the ranges overlap (4–6 vs 5–9) and three runs of ten events
is a small sample: treat it as a likely improvement, not a proven one. Because the latency was the
same, `gpt-5.4-mini` is now the app's default drafting model (`OPENAI_DRAFT_MODEL` overrides it);
the runs above that predate this used `gpt-4o-mini` as drafter. Scoring stays on `OPENAI_MODEL`.

How to read this:

- **Category and dedup are solid** (10/10 in every run). The CRM write is 10/10 since the fixture
  email was fixed. Run 1's miss was HubSpot rejecting the made-up `jason@rankboost-seo.example`;
  the adapter still does not retry without a rejected email, so a real lead with a mistyped email
  would lose their CRM contact. That remains a known limitation.
- **Draft quality is the weak spot, and it is noisy.** The same event can pass in one run and fail
  in the next (#2 and #8 passed in run 2 and failed in run 3), because drafts are sampled each
  time. With ten events and one run each, the follow-up-aware prompt cannot be shown to have helped
  or hurt. Run 1's 9/10 came from a lenient judge and should not be quoted.
- **Fixes to the judge were made after seeing results** (runs 2 and 3), so they are not a clean
  first-try measurement. Run 3's fix was for two mistakes found by reading the drafts: a "does not
  quote a price" point cannot be backed by a quote, and one verdict stitched two sentences together.
- **The judge is still an LLM.** In run 2 it accepted "Thanks for following up!" as referencing an
  earlier message for one lead and rejected it for another.
- **Some failures are the rules, not the model.** #7 failed in all six experiment runs: the drafts
  say a plumber will be sent "as quickly as we can", and the judge wants a firm "someone will be
  dispatched now". The drafter is told never to promise availability it cannot know, so that
  checklist point and the safety rule pull in opposite directions; a human adds the commitment at
  approval. #3 fails the same way: the drafter offers to "walk you through our process" but will
  not invent what the process is. #10 is mostly the judge insisting on an explicit WhatsApp mention
  and a stated link between the visit and "before summer".
- **Drafts that fell short in run 3 (before the experiment):** #3 never answers the process question (the drafter has
  no knowledge of the company's process and does not invent one), #8 does not ask about house size,
  #10 thanks her for following up but never mentions WhatsApp or proposes a time, #7 gives vague
  safety advice and waits for an address before dispatching, and #2 offers a call today without
  committing to one.
