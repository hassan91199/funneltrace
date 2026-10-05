from fastapi.testclient import TestClient

from funneltrace.api import create_app
from funneltrace.repository import InMemoryLeadRepository

FORM = {
    "name": "Sarah Mitchell",
    "email": "sarah.mitchell@gmail.com",
    "phone": "+1 (415) 555-0142",
    "message": "Furnace died.",
}
WHATSAPP = {"from": "14155550142", "profile_name": "Sarah M", "text": "call me today"}


def make_client():
    repo = InMemoryLeadRepository()
    return TestClient(create_app(repo=repo)), repo


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
