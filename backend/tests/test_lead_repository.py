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


def test_same_person_on_the_other_channel_merges_into_one_lead(repo):
    import psycopg

    first = repo.add_lead(
        normalize_web_form(
            {"name": "Priya Sharma", "email": "p@x.co", "phone": "+92 300 5550188", "message": "a"}
        )
    )
    second = repo.add_lead(
        normalize_whatsapp({"from": "923005550188", "profile_name": "Priya", "text": "b"})
    )
    other = repo.add_lead(
        normalize_whatsapp({"from": "923005550999", "profile_name": "Priya", "text": "c"})
    )
    assert first.is_new and not second.is_new and other.is_new
    assert second.lead_id == first.lead_id != other.lead_id
    assert "phone" in second.match_reason

    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM leads").fetchone()[0] == 2
        rows = conn.execute(
            "SELECT channel, match_reason FROM lead_messages WHERE lead_id = %s "
            "ORDER BY received_at",
            (first.lead_id,),
        ).fetchall()
    assert [r[0] for r in rows] == ["web_form", "whatsapp"]
    assert rows[0][1] is None and "phone" in rows[1][1]


def test_messages_and_scoring_history_are_kept_per_lead(repo):
    from funneltrace.scoring import ScoreResult

    a = repo.add_lead(
        normalize_web_form({"name": "Dan", "email": "d@x.co", "phone": "", "message": "first"})
    )
    repo.add_lead(
        normalize_web_form({"name": "Dan", "email": "d@x.co", "phone": "", "message": "second"})
    )
    context = repo.get_context(a.lead_id)
    assert context.name == "Dan"
    assert context.messages == [("web_form", "first"), ("web_form", "second")]

    repo.add_score(a.lead_id, ScoreResult("warm", 0.6, "Early."), model="m1")
    repo.add_score(a.lead_id, ScoreResult("hot", 0.9, "Deadline."), model="m1")
    history = repo.scores_for(a.lead_id)
    assert [(s.category, s.confidence, s.reasoning, s.model) for s in history] == [
        ("warm", pytest.approx(0.6), "Early.", "m1"),
        ("hot", pytest.approx(0.9), "Deadline.", "m1"),
    ]
