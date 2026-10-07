from fastapi.testclient import TestClient

from funneltrace.api import create_app
from funneltrace.interfaces import LLMRefusal
from funneltrace.repository import InMemoryLeadRepository
from tests.fakes import FakeLLM

FORM = {
    "name": "Sarah Mitchell",
    "email": "sarah.mitchell@gmail.com",
    "phone": "+1 (415) 555-0142",
    "message": "Furnace died.",
}
WHATSAPP = {"from": "14155550142", "profile_name": "Sarah M", "text": "call me today"}


HOT = {"category": "hot", "confidence": 0.9, "reasoning": "Urgent, has budget."}


def make_client(llm=None):
    repo = InMemoryLeadRepository()
    llm = llm or FakeLLM(score=HOT, draft={"subject": "s", "body": "b"})
    return TestClient(create_app(repo=repo, llm=llm)), repo


def test_web_form_webhook_stores_a_lead():
    client, repo = make_client()
    resp = client.post("/webhooks/web-form", json=FORM)
    assert resp.status_code == 201
    assert resp.json()["lead_id"]
    assert repo.leads[0].normalized_phone == "14155550142"
    assert repo.leads[0].channel == "web_form"


def test_whatsapp_webhook_uses_the_from_field_and_stores_the_same_shape():
    client, repo = make_client()
    resp = client.post("/webhooks/whatsapp", json=WHATSAPP)
    assert resp.status_code == 201
    form_fields = set(vars(repo.leads[0]))
    client.post("/webhooks/web-form", json=FORM)
    assert set(vars(repo.leads[1])) == form_fields


def test_invalid_payload_is_a_422_and_stores_nothing():
    client, repo = make_client()
    bad_email = client.post("/webhooks/web-form", json={**FORM, "email": "nope"})
    no_contact = client.post("/webhooks/web-form", json={**FORM, "email": "", "phone": ""})
    missing_field = client.post("/webhooks/whatsapp", json={"from": "14155550142"})
    assert bad_email.status_code == no_contact.status_code == missing_field.status_code == 422
    assert repo.leads == []


def test_webhook_scores_the_lead_and_returns_the_result():
    client, repo = make_client()
    body = client.post("/webhooks/web-form", json=FORM).json()
    assert body["score"] == {
        "category": "hot",
        "confidence": 0.9,
        "reasoning": "Urgent, has budget.",
    }
    (stored,) = repo.scores_for(body["lead_id"])
    assert stored.category == "hot" and stored.model == "fake-model"


def test_a_returning_contact_is_rescored_with_the_whole_conversation():
    llm = FakeLLM(score=HOT, draft={"subject": "s", "body": "b"})
    client, repo = make_client(llm)
    first = client.post("/webhooks/web-form", json=FORM).json()
    second = client.post("/webhooks/whatsapp", json=WHATSAPP).json()
    assert second["lead_id"] == first["lead_id"]
    assert len(repo.scores_for(first["lead_id"])) == 2
    user_prompt = llm.json_calls[2][1]
    assert "Furnace died." in user_prompt and "call me today" in user_prompt


def test_scoring_failure_keeps_the_lead_and_reports_the_error():
    client, repo = make_client(FakeLLM(json_responses=[LLMRefusal("nope")]))
    resp = client.post("/webhooks/web-form", json=FORM)
    assert resp.status_code == 201
    body = resp.json()
    assert body["score"] is None and "refused" in body["score_error"]
    assert repo.scores_for(body["lead_id"]) == []
    assert len(repo.leads) == 1
