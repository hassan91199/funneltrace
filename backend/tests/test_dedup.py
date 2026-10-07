import pytest

from eval.test_set import TEST_SET
from funneltrace.dedup import Candidate, find_match, names_compatible
from funneltrace.intake import normalize_web_form, normalize_whatsapp
from funneltrace.repository import InMemoryLeadRepository


def _inbound(event):
    if event["channel"] == "web_form":
        return normalize_web_form(event["payload"])
    return normalize_whatsapp(event["payload"])


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Sarah Mitchell", "Sarah M"),
        ("Daniel Okafor", "Dan Okafor"),
        ("Priya Sharma", "Priya"),
        ("sarah  mitchell", "SARAH MITCHELL"),
        ("Jon Smith", "John Smith"),
        ("Sarah Mitchell", "+14155550142"),  # WhatsApp fallback name: no real name known
    ],
)
def test_names_that_can_be_the_same_person(a, b):
    assert names_compatible(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Sarah Mitchell", "Daniel Okafor"),
        ("Sarah Mitchell", "Sarah Okafor"),
        ("Dan Okafor", "Don Brown"),
    ],
)
def test_names_that_cannot_be_the_same_person(a, b):
    assert not names_compatible(a, b)


def _candidate(**kw):
    base = {"lead_id": "L1", "name": "Sarah Mitchell", "normalized_email": None}
    return Candidate(**{"normalized_phone": None, **base, **kw})


def test_matches_on_phone_and_records_why():
    inbound = normalize_whatsapp({"from": "14155550142", "profile_name": "Sarah M", "text": "hi"})
    match = find_match(inbound, [_candidate(normalized_phone="14155550142")])
    assert match.lead_id == "L1"
    assert "phone" in match.reason and "Sarah M" in match.reason


def test_matches_on_email():
    inbound = normalize_web_form(
        {"name": "Sarah Mitchell", "email": " S@X.co ", "phone": "", "message": "hi"}
    )
    match = find_match(inbound, [_candidate(normalized_email="s@x.co")])
    assert match.lead_id == "L1" and "email" in match.reason


def test_name_alone_never_merges():
    inbound = normalize_web_form(
        {"name": "Sarah Mitchell", "email": "other@x.co", "phone": "", "message": "hi"}
    )
    assert find_match(inbound, [_candidate(normalized_email="s@x.co")]) is None


def test_shared_phone_with_a_clearly_different_name_does_not_merge():
    inbound = normalize_whatsapp({"from": "14155550142", "profile_name": "Bob Jones", "text": "hi"})
    assert find_match(inbound, [_candidate(normalized_phone="14155550142")]) is None


def test_whatsapp_without_a_profile_name_merges_on_phone_alone():
    inbound = normalize_whatsapp({"from": "14155550142", "text": "hi"})
    assert find_match(inbound, [_candidate(normalized_phone="14155550142")]) is not None


def test_empty_identifiers_never_match_each_other():
    inbound = normalize_web_form({"name": "Mike Torres", "email": "m@y.com", "message": "hi"})
    assert find_match(inbound, [_candidate(name="Mike Torres")]) is None


def test_eval_set_stream_dedups_exactly_as_locked():
    repo = InMemoryLeadRepository()
    lead_ids = {}
    for event in TEST_SET:
        stored = repo.add_lead(_inbound(event))
        assert stored.is_new is event["expect_new_lead"], f"event {event['id']}"
        if not stored.is_new:
            assert stored.match_reason, f"event {event['id']}"
        lead_ids[event["id"]] = stored.lead_id

    for event in TEST_SET:
        same_person = [e["id"] for e in TEST_SET if e["person"] == event["person"]]
        assert len({lead_ids[i] for i in same_person}) == 1, f"person {event['person']}"
    assert len(set(lead_ids.values())) == 7
    assert lead_ids[8] != lead_ids[1]  # the near-miss stays separate


def test_merge_fills_missing_contact_details():
    repo = InMemoryLeadRepository()
    repo.add_lead(_inbound(TEST_SET[3]))  # Priya on WhatsApp: phone only
    repo.add_lead(_inbound(TEST_SET[9]))  # Priya Sharma via form: adds email
    (record,) = repo.records
    assert record.normalized_email == "priya.sharma@example.com"
    assert record.name == "Priya Sharma"
