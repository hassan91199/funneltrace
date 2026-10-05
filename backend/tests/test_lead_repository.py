import os

import pytest

from funneltrace.db import apply_migrations
from funneltrace.intake import normalize_web_form, normalize_whatsapp
from funneltrace.repository import PgLeadRepository

TEST_DB = os.environ.get("FUNNELTRACE_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not TEST_DB, reason="FUNNELTRACE_TEST_DATABASE_URL not set"),
]


@pytest.fixture
def repo():
    import psycopg

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    apply_migrations(TEST_DB)
    return PgLeadRepository(TEST_DB)


def test_both_channels_land_in_the_same_tables_with_the_same_shape(repo):
    import psycopg

    form = normalize_web_form(
        {"name": "Sarah", "email": "S@x.co", "phone": "+1 415 555 0142", "message": "hi"}
    )
    chat = normalize_whatsapp({"from": "14155550999", "profile_name": "Bob", "text": "yo"})
    for inbound in (form, chat):
        stored = repo.add_lead(inbound)
        assert stored.lead_id and stored.message_id

    with psycopg.connect(TEST_DB) as conn:
        leads = conn.execute(
            "SELECT name, email, phone, normalized_email, normalized_phone "
            "FROM leads ORDER BY created_at"
        ).fetchall()
        msgs = conn.execute(
            "SELECT channel, body, raw_payload FROM lead_messages ORDER BY received_at"
        ).fetchall()
    assert leads[0] == ("Sarah", "S@x.co", "+1 415 555 0142", "s@x.co", "14155550142")
    assert leads[1][3] is None and leads[1][4] == "14155550999"
    assert [m[0] for m in msgs] == ["web_form", "whatsapp"]
    assert msgs[1][2] == {"from": "14155550999", "profile_name": "Bob", "text": "yo"}
