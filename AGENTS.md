# FunnelTrace

AI lead-triage workflow: multi-channel intake, LLM scoring with reasoning, dedup,
human-approved follow-up drafts, HubSpot sync, and a live decision trace.

# Git

- Remote: `origin` = `https://github.com/hassan91199/funneltrace.git` (default branch `main`).
- Work on branches; `main` only changes by merging. Never force-push.

# Repo conventions

- `.docs/` is git-ignored (local-only notes); do not commit it.
- Build test-first (red/green/refactor). The default test suite fakes the LLM and
  CRM, with no network calls. The real eval run is opt-in.
- Never report eval numbers before the eval has actually run.
