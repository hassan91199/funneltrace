import os

import pytest

from funneltrace.db import apply_migrations
from funneltrace.intake import normalize_web_form, normalize_whatsapp
from funneltrace.repository import PgLeadRepository
from funneltrace.scoring import ScoreResult

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


def test_draft_lifecycle_and_events_persist(repo):
    lead = repo.add_lead(
        normalize_web_form({"name": "Dan", "email": "d@x.co", "phone": "", "message": "hi"})
    )
    scoring_id = repo.add_score(lead.lead_id, ScoreResult("hot", 0.9, "Urgent."), model="m")
    first = repo.add_draft(lead.lead_id, scoring_id, "S1", "B1")
    assert first.status == "pending" and first.lead_name == "Dan" and first.category == "hot"

    second = repo.add_draft(lead.lead_id, scoring_id, "S2", "B2")
    assert repo.get_draft(first.draft_id).status == "superseded"
    assert [d.draft_id for d in repo.list_drafts("pending")] == [second.draft_id]

    decided = repo.decide_draft(second.draft_id, "approved")
    assert decided.status == "approved" and decided.decided_at is not None
    assert repo.decide_draft(second.draft_id, "rejected") is None  # already decided

    repo.log_event(lead.lead_id, "would_send", {"to": "d@x.co"})
    (event,) = repo.events_for(lead.lead_id)
    assert event.type == "would_send" and event.payload == {"to": "d@x.co"}


def test_crm_syncs_persist_per_lead(repo):
    lead = repo.add_lead(
        normalize_web_form({"name": "Dan", "email": "d@x.co", "phone": "", "message": "hi"})
    )
    scoring_id = repo.add_score(lead.lead_id, ScoreResult("hot", 0.9, "Urgent."), model="m")
    draft = repo.add_draft(lead.lead_id, scoring_id, "S", "B")

    repo.add_crm_sync(lead.lead_id, draft.draft_id, "hubspot", "failed", error="HubSpot 401")
    repo.add_crm_sync(
        lead.lead_id, draft.draft_id, "hubspot", "synced", external_id="501", action="create"
    )
    failed, synced = repo.crm_syncs_for(lead.lead_id)
    assert (failed.status, failed.error, failed.external_id) == ("failed", "HubSpot 401", None)
    assert (synced.status, synced.external_id, synced.action) == ("synced", "501", "create")
    assert synced.draft_id == draft.draft_id and synced.crm == "hubspot"


def test_events_can_be_read_after_a_cursor_for_one_lead_or_all(repo):
    a = repo.add_lead(
        normalize_web_form({"name": "Dan", "email": "d@x.co", "phone": "", "message": "hi"})
    )
    b = repo.add_lead(
        normalize_web_form({"name": "Eve", "email": "e@x.co", "phone": "", "message": "hi"})
    )
    repo.log_event(a.lead_id, "lead_received", {"n": 1})
    repo.log_event(b.lead_id, "lead_received", {"n": 2})
    repo.log_event(a.lead_id, "scored", {"n": 3})

    everything = repo.events_after(0)
    assert [e.payload["n"] for e in everything] == [1, 2, 3]
    assert everything[0].lead_id == a.lead_id and everything[0].created_at is not None
    assert [e.payload["n"] for e in repo.events_after(0, a.lead_id)] == [1, 3]
    assert [e.payload["n"] for e in repo.events_after(everything[0].id)] == [2, 3]
    assert repo.events_after(everything[-1].id) == []
