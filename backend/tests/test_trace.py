import itertools
import json

from fastapi.testclient import TestClient

from funneltrace.api import create_app
from funneltrace.interfaces import CrmError, LLMRefusal
from funneltrace.repository import InMemoryLeadRepository
from funneltrace.trace import format_sse, stream_events
from tests.fakes import FakeCrm, FakeLLM

FORM = {
    "name": "Sarah Mitchell",
    "email": "sarah@x.co",
    "phone": "+1 (415) 555-0142",
    "message": "Furnace died.",
}
WHATSAPP = {"from": "14155550142", "profile_name": "Sarah M", "text": "call me today"}
SCORE = {"category": "hot", "confidence": 0.9, "reasoning": "Urgent."}
DRAFT = {"subject": "Re: furnace", "body": "We can visit this week."}


def make(llm=None, crm=None):
    repo = InMemoryLeadRepository()
    llm = llm or FakeLLM(score=SCORE, draft=DRAFT)
    return TestClient(create_app(repo=repo, llm=llm, crm=crm or FakeCrm())), repo


def types(repo, lead_id):
    return [e.type for e in repo.events_for(lead_id)]


def test_a_lead_journey_is_traced_step_by_step_through_approval_and_crm():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    assert types(repo, body["lead_id"]) == ["lead_received", "dedup_decision", "scored", "drafted"]
    client.post(f"/drafts/{body['draft']['id']}/approve")
    assert types(repo, body["lead_id"]) == [
        "lead_received",
        "dedup_decision",
        "scored",
        "drafted",
        "draft_approved",
        "would_send",
        "crm_synced",
    ]


def test_each_event_carries_what_a_reader_needs_to_follow_the_decision():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    received, dedup, scored, drafted = (e.payload for e in repo.events_for(body["lead_id"]))
    assert received["channel"] == "web_form" and received["name"] == "Sarah Mitchell"
    assert received["message_id"] == body["message_id"]
    assert dedup == {"is_new": True, "match_reason": None}
    assert scored == {
        "category": "hot",
        "confidence": 0.9,
        "reasoning": "Urgent.",
        "model": "fake-model",
    }
    assert drafted["draft_id"] == body["draft"]["id"] and drafted["subject"] == "Re: furnace"


def test_a_merge_is_traced_with_the_reason_and_the_journey_continues_on_the_same_lead():
    client, repo = make()
    first = client.post("/webhooks/web-form", json=FORM).json()
    second = client.post("/webhooks/whatsapp", json=WHATSAPP).json()
    assert second["lead_id"] == first["lead_id"]
    events = repo.events_for(first["lead_id"])
    assert [e.type for e in events].count("lead_received") == 2
    merge = [e.payload for e in events if e.type == "dedup_decision"][1]
    assert merge["is_new"] is False and "phone" in merge["match_reason"]


def test_a_rejection_is_traced_and_nothing_is_sent_or_synced():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    client.post(f"/drafts/{body['draft']['id']}/reject")
    assert types(repo, body["lead_id"])[-1] == "draft_rejected"
    assert "would_send" not in types(repo, body["lead_id"])


def test_failures_are_traced_instead_of_vanishing():
    client, repo = make(FakeLLM(score=LLMRefusal("no"), draft=DRAFT))
    body = client.post("/webhooks/web-form", json=FORM).json()
    assert types(repo, body["lead_id"]) == ["lead_received", "dedup_decision", "score_failed"]

    client, repo = make(FakeLLM(score=SCORE, draft={"subject": "", "body": ""}))
    body = client.post("/webhooks/web-form", json=FORM).json()
    assert types(repo, body["lead_id"])[-2:] == ["scored", "draft_failed"]

    client, repo = make(crm=FakeCrm(error=CrmError("HubSpot 401")))
    body = client.post("/webhooks/web-form", json=FORM).json()
    client.post(f"/drafts/{body['draft']['id']}/approve")
    assert types(repo, body["lead_id"])[-3:] == ["draft_approved", "would_send", "crm_failed"]


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "data" in fields:
            events.append({**fields, "data": json.loads(fields["data"])})
    return events


def test_the_stream_replays_a_leads_events_in_order_with_ids():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    other = client.post("/webhooks/web-form", json={**FORM, "email": "o@x.co", "phone": ""}).json()
    resp = client.get("/events", params={"lead_id": body["lead_id"], "follow": "false"})
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    assert [e["event"] for e in events] == [
        "lead_received",
        "dedup_decision",
        "scored",
        "drafted",
    ]
    ids = [int(e["id"]) for e in events]
    assert ids == sorted(ids) and len(set(ids)) == 4
    assert {e["data"]["lead_id"] for e in events} == {body["lead_id"]}
    assert other["lead_id"] != body["lead_id"]
    scored = events[2]["data"]
    assert scored["payload"]["reasoning"] == "Urgent." and scored["created_at"]


def test_without_a_lead_filter_the_stream_carries_every_leads_events():
    client, _ = make()
    client.post("/webhooks/web-form", json=FORM)
    client.post("/webhooks/web-form", json={**FORM, "email": "o@x.co", "phone": ""})
    events = parse_sse(client.get("/events", params={"follow": "false"}).text)
    assert len(events) == 8 and len({e["data"]["lead_id"] for e in events}) == 2


def test_resuming_after_an_event_id_skips_what_the_client_already_has():
    client, _ = make()
    client.post("/webhooks/web-form", json=FORM)
    everything = parse_sse(client.get("/events", params={"follow": "false"}).text)
    cut = everything[1]["id"]
    by_param = parse_sse(client.get("/events", params={"after": cut, "follow": "false"}).text)
    by_header = parse_sse(
        client.get("/events", params={"follow": "false"}, headers={"Last-Event-ID": cut}).text
    )
    assert [e["id"] for e in by_param] == [e["id"] for e in everything[2:]]
    assert by_header == by_param


def test_bad_lead_ids_and_cursors_are_rejected():
    client, _ = make()
    assert client.get("/events", params={"lead_id": "nope", "follow": "false"}).status_code == 404
    assert client.get("/events", params={"after": "x", "follow": "false"}).status_code == 422


def test_the_live_stream_delivers_events_that_arrive_after_the_replay():
    repo = InMemoryLeadRepository()
    repo.log_event(None, "early", {})

    def sleep(_):  # stands in for the wait between polls: a new event lands meanwhile
        repo.log_event(None, "late", {})

    stream = stream_events(repo, follow=True, sleep=sleep)
    lines = "".join(itertools.islice(stream, 2))
    assert [e["event"] for e in parse_sse(lines)] == ["early", "late"]


def test_the_live_stream_sends_keepalive_comments_while_idle():
    repo = InMemoryLeadRepository()
    stream = stream_events(repo, follow=True, sleep=lambda _: None, keepalive_every=2)
    chunks = list(itertools.islice(stream, 1))
    assert chunks == [": keepalive\n\n"]


def test_format_sse_shape():
    assert format_sse(7, "scored", {"a": 1}) == 'id: 7\nevent: scored\ndata: {"a": 1}\n\n'
