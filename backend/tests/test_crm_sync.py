from fastapi.testclient import TestClient

from funneltrace.api import create_app
from funneltrace.interfaces import CrmError
from funneltrace.repository import InMemoryLeadRepository
from tests.fakes import FakeCrm, FakeLLM

FORM = {
    "name": "Sarah Mitchell",
    "email": " Sarah@X.co ",
    "phone": "+1 (415) 555-0142",
    "message": "Furnace died.",
}
WHATSAPP = {"from": "14155550142", "profile_name": "Sarah M", "text": "call me today"}
DRAFT = {"subject": "Re: furnace", "body": "We can visit this week."}


def score(category):
    return {"category": category, "confidence": 0.9, "reasoning": "Because."}


def make(category="hot", crm=None):
    repo = InMemoryLeadRepository()
    crm = crm or FakeCrm()
    llm = FakeLLM(score=score(category), draft=DRAFT)
    return TestClient(create_app(repo=repo, llm=llm, crm=crm)), repo, crm


def webhook(client, payload=FORM, path="web-form"):
    return client.post(f"/webhooks/{path}", json=payload).json()


def events(repo, lead_id, type):
    return [e for e in repo.events_for(lead_id) if e.type == type]


def test_nothing_is_synced_before_approval_or_after_rejection():
    client, repo, crm = make()
    first = webhook(client)
    assert crm.calls == []
    client.post(f"/drafts/{first['draft']['id']}/reject")
    assert crm.calls == []
    assert repo.crm_syncs_for(first["lead_id"]) == []


def test_approving_syncs_the_contact_with_the_mapped_lifecycle_stage():
    client, repo, crm = make("hot")
    body = webhook(client)
    resp = client.post(f"/drafts/{body['draft']['id']}/approve").json()
    assert crm.calls == [
        {
            "name": "Sarah Mitchell",
            "email": "sarah@x.co",
            "phone": "14155550142",
            "lifecycle_stage": "salesqualifiedlead",
        }
    ]
    assert resp["crm"] == {
        "crm": "fake-crm",
        "status": "synced",
        "action": "create",
        "external_id": "crm-1",
    }
    (record,) = repo.crm_syncs_for(body["lead_id"])
    assert (record.status, record.external_id, record.action) == ("synced", "crm-1", "create")
    assert record.draft_id == body["draft"]["id"]
    (event,) = events(repo, body["lead_id"], "crm_synced")
    assert event.payload["external_id"] == "crm-1" and event.payload["action"] == "create"


def test_each_category_maps_to_its_lifecycle_stage():
    for category, stage in [
        ("hot", "salesqualifiedlead"),
        ("warm", "marketingqualifiedlead"),
        ("cold", "lead"),
    ]:
        client, _, crm = make(category)
        body = webhook(client)
        client.post(f"/drafts/{body['draft']['id']}/approve")
        assert crm.calls[0]["lifecycle_stage"] == stage


def test_a_later_approval_updates_the_same_crm_contact_with_the_latest_score():
    repo = InMemoryLeadRepository()
    crm = FakeCrm()
    llm = FakeLLM(score=[score("warm"), score("hot")], draft=DRAFT)
    client = TestClient(create_app(repo=repo, llm=llm, crm=crm))
    first = webhook(client)
    client.post(f"/drafts/{first['draft']['id']}/approve")
    second = webhook(client, WHATSAPP, "whatsapp")
    assert second["lead_id"] == first["lead_id"]
    resp = client.post(f"/drafts/{second['draft']['id']}/approve").json()
    assert crm.calls[1]["external_id"] == "crm-1"
    assert crm.calls[1]["lifecycle_stage"] == "salesqualifiedlead"
    assert resp["crm"]["action"] == "update" and resp["crm"]["external_id"] == "crm-1"


def test_a_phone_only_lead_syncs_without_an_email():
    client, _, crm = make()
    body = webhook(client, WHATSAPP, "whatsapp")
    client.post(f"/drafts/{body['draft']['id']}/approve")
    assert crm.calls[0]["email"] is None and crm.calls[0]["phone"] == "14155550142"


def test_a_crm_failure_does_not_undo_the_approval_and_is_recorded():
    client, repo, crm = make(crm=FakeCrm(error=CrmError("HubSpot 401: bad token")))
    body = webhook(client)
    resp = client.post(f"/drafts/{body['draft']['id']}/approve")
    assert resp.status_code == 200
    assert resp.json()["draft"]["status"] == "approved"
    assert resp.json()["would_send"]["to"] == "sarah@x.co"
    assert resp.json()["crm"]["status"] == "failed"
    assert "401" in resp.json()["crm"]["error"]
    (record,) = repo.crm_syncs_for(body["lead_id"])
    assert record.status == "failed" and "401" in record.error
    (event,) = events(repo, body["lead_id"], "crm_failed")
    assert "401" in event.payload["error"]


def test_an_unconfigured_crm_is_a_recorded_failure_not_a_crash(monkeypatch):
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("funneltrace.api.load_env", lambda: None)
    repo = InMemoryLeadRepository()
    llm = FakeLLM(score=score("hot"), draft=DRAFT)
    client = TestClient(create_app(repo=repo, llm=llm))
    body = webhook(client)
    resp = client.post(f"/drafts/{body['draft']['id']}/approve")
    assert resp.status_code == 200 and resp.json()["crm"]["status"] == "failed"
    assert "HUBSPOT_ACCESS_TOKEN" in resp.json()["crm"]["error"]
