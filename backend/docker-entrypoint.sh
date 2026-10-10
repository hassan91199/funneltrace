#!/bin/sh
# test  (default): the CI gate - lint, then the default suite (no network, LLM and CRM faked).
# serve: apply migrations, then run the API (needs DATABASE_URL, OPENAI_API_KEY, ...).
set -eu

case "${1:-test}" in
  test)
    ruff check .
    exec pytest -q
    ;;
  serve)
    python -m funneltrace.db
    exec uvicorn funneltrace.api:app --host 0.0.0.0 --port 8000
    ;;
  *)
    exec "$@"
    ;;
esac
