from fastapi.testclient import TestClient

from funneltrace.api import create_app
from funneltrace.interfaces import LLMRefusal
from funneltrace.repository import InMemoryLeadRepository
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


def make(llm=None):
    repo = InMemoryLeadRepository()
    llm = llm or FakeLLM(score=SCORE, draft=DRAFT)
    return TestClient(create_app(repo=repo, llm=llm, crm=FakeCrm())), repo


def would_sends(repo, lead_id):
    return [e for e in repo.events_for(lead_id) if e.type == "would_send"]


def test_webhook_creates_a_pending_draft_and_sends_nothing():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    assert body["draft"]["status"] == "pending"
    assert body["draft"]["subject"] == "Re: furnace"
    inbox = client.get("/drafts", params={"status": "pending"}).json()
    assert [d["id"] for d in inbox] == [body["draft"]["id"]]
    assert inbox[0]["lead_name"] == "Sarah Mitchell"
    assert inbox[0]["category"] == "hot" and inbox[0]["reasoning"] == "Urgent."
    assert would_sends(repo, body["lead_id"]) == []  # nothing "sent" yet


def test_approving_marks_it_approved_and_logs_a_would_send_payload():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    resp = client.post(f"/drafts/{body['draft']['id']}/approve")
    assert resp.status_code == 200
    assert resp.json()["draft"]["status"] == "approved"
    (event,) = would_sends(repo, body["lead_id"])
    assert event.type == "would_send"
    assert event.payload == {
        "draft_id": body["draft"]["id"],
        "channel": "web_form",
        "to": "sarah@x.co",
        "subject": "Re: furnace",
        "body": "We can visit this week.",
    }
    assert resp.json()["would_send"] == event.payload


def test_reply_goes_out_on_the_channel_the_lead_last_used():
    client, repo = make()
    client.post("/webhooks/web-form", json=FORM)
    body = client.post("/webhooks/whatsapp", json=WHATSAPP).json()
    client.post(f"/drafts/{body['draft']['id']}/approve")
    (event,) = would_sends(repo, body["lead_id"])
    assert event.payload["channel"] == "whatsapp" and event.payload["to"] == "14155550142"


def test_rejecting_marks_it_rejected_and_sends_nothing():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    resp = client.post(f"/drafts/{body['draft']['id']}/reject")
    assert resp.json()["draft"]["status"] == "rejected"
    assert would_sends(repo, body["lead_id"]) == []
    assert client.get("/drafts", params={"status": "pending"}).json() == []


def test_a_decided_draft_cannot_be_decided_again():
    client, repo = make()
    body = client.post("/webhooks/web-form", json=FORM).json()
    draft_id = body["draft"]["id"]
    client.post(f"/drafts/{draft_id}/approve")
    assert client.post(f"/drafts/{draft_id}/approve").status_code == 409
    assert client.post(f"/drafts/{draft_id}/reject").status_code == 409
    assert len(would_sends(repo, body["lead_id"])) == 1  # sent once, not twice


def test_unknown_draft_is_a_404():
    client, _ = make()
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/drafts/{unknown}").status_code == 404
    assert client.post(f"/drafts/{unknown}/approve").status_code == 404
    assert client.post(f"/drafts/{unknown}/reject").status_code == 404


def test_a_newer_draft_supersedes_the_old_pending_one():
    client, repo = make()
    first = client.post("/webhooks/web-form", json=FORM).json()
    second = client.post("/webhooks/whatsapp", json=WHATSAPP).json()
    assert second["lead_id"] == first["lead_id"]
    assert client.get(f"/drafts/{first['draft']['id']}").json()["status"] == "superseded"
    pending = client.get("/drafts", params={"status": "pending"}).json()
    assert [d["id"] for d in pending] == [second["draft"]["id"]]
    assert client.post(f"/drafts/{first['draft']['id']}/approve").status_code == 409


def test_draft_failure_keeps_the_lead_and_the_score():
    llm = FakeLLM(score=SCORE, draft=LLMRefusal("no"))
    client, repo = make(llm)
    resp = client.post("/webhooks/web-form", json=FORM)
    body = resp.json()
    assert resp.status_code == 201
    assert body["score"]["category"] == "hot"
    assert body["draft"] is None and "refused" in body["draft_error"]
    assert client.get("/drafts").json() == []


def test_no_draft_when_scoring_failed():
    client, _ = make(FakeLLM(score=LLMRefusal("no"), draft=DRAFT))
    body = client.post("/webhooks/web-form", json=FORM).json()
    assert body["score"] is None and body["draft"] is None


def test_status_filter_rejects_unknown_values():
    client, _ = make()
    assert client.get("/drafts", params={"status": "bogus"}).status_code == 422
