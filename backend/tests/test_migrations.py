import os

import pytest

from funneltrace.db import apply_migrations, migration_files

TEST_DB = os.environ.get("FUNNELTRACE_TEST_DATABASE_URL")


def test_migrations_are_ordered_and_present():
    files = migration_files()
    assert files, "no migrations found"
    names = [f.name for f in files]
    assert names == sorted(names)
    assert names[0].startswith("001_")


@pytest.mark.db
@pytest.mark.skipif(not TEST_DB, reason="FUNNELTRACE_TEST_DATABASE_URL not set")
def test_migrations_apply_cleanly_and_are_idempotent():
    import psycopg

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    apply_migrations(TEST_DB)
    apply_migrations(TEST_DB)  # second run must be a no-op
    with psycopg.connect(TEST_DB) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
        }
    assert {
        "leads",
        "lead_messages",
        "scoring_history",
        "drafts",
        "crm_syncs",
        "trace_events",
        "schema_migrations",
    } <= tables
