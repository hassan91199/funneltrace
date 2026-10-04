# FunnelTrace

AI lead-triage workflow: multi-channel intake, LLM scoring with reasoning, dedup,
human-approved follow-up drafts, HubSpot sync, and a live decision trace.
Scope and decisions: the build brief at
`/home/hassan/dev/projs/github-hassan91199/personal-docs/.docs/funneltrace_build_brief.md`.
Tasks are tracked in ClickUp list `proj-funneltrace` (list_id `1100390000093499`,
folder "Projects"); task names are prefixed `FT-N`.

# Git / GitHub

- Remote: `origin` = `https://github.com/hassan91199/funneltrace.git` (default branch `main`).
- This machine has multiple GitHub accounts. Prefix every `git push` / `gh` write
  operation with the `as-hassan-personal` wrapper, e.g.
  `as-hassan-personal git push origin main`. A plain `git push` can fail with a
  misleading "Repository not found".
- The remote URL stays plain (no token in it); this repo has a local credential
  helper for `https://github.com/hassan91199` delegating to `gh auth git-credential`.
- The full workflow is documented in
  `/home/hassan/dev/projs/github-hassan91199/personal-docs/docs/git-github-auth.md`.
  This applies regardless of which coding agent is driving the command.

# Repo conventions

- `.docs/` is git-ignored (local-only notes); do not commit it.
- Build test-first (red/green/refactor). The default test suite fakes the LLM and
  CRM, with no network calls. The real eval run is opt-in.
- Never report eval numbers before the eval has actually run.
