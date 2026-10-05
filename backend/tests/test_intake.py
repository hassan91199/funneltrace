import pytest

from eval.test_set import TEST_SET
from funneltrace.intake import (
    normalize_email,
    normalize_phone,
    normalize_web_form,
    normalize_whatsapp,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Sarah.Mitchell@Gmail.com", "sarah.mitchell@gmail.com"),
        ("  d.okafor@fastmail.com  ", "d.okafor@fastmail.com"),
        ("", None),
        (None, None),
        ("   ", None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["not-an-email", "a@b", "@x.com", "a b@x.com"])
def test_normalize_email_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalize_email(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+1 (415) 555-0142", "14155550142"),
        ("14155550142", "14155550142"),
        ("+92 300 5550188", "923005550188"),
        ("00 44 7700 900123", "447700900123"),
        ("", None),
        (None, None),
        ("n/a", None),
        ("12345", None),  # too short to be a usable phone number
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_web_form_becomes_a_lead_record():
    lead = normalize_web_form(
        {
            "name": "  Sarah Mitchell ",
            "email": "Sarah.Mitchell@gmail.com",
            "phone": "+1 (415) 555-0142",
            "message": "Furnace died.",
        }
    )
    assert lead.channel == "web_form"
    assert lead.name == "Sarah Mitchell"
    assert lead.normalized_email == "sarah.mitchell@gmail.com"
    assert lead.normalized_phone == "14155550142"
    assert lead.message == "Furnace died."
    assert lead.raw_payload["email"] == "Sarah.Mitchell@gmail.com"


def test_whatsapp_becomes_the_same_record_shape():
    lead = normalize_whatsapp({"from": "14155550142", "profile_name": "Sarah M", "text": "hi"})
    assert lead.channel == "whatsapp"
    assert lead.name == "Sarah M"
    assert lead.email is None and lead.normalized_email is None
    assert lead.normalized_phone == "14155550142"
    assert lead.message == "hi"


def test_whatsapp_without_profile_name_falls_back_to_the_number():
    lead = normalize_whatsapp({"from": "14155550142", "profile_name": "", "text": "hi"})
    assert lead.name == "+14155550142"


def test_web_form_needs_a_way_to_reach_the_person():
    with pytest.raises(ValueError, match="email or phone"):
        normalize_web_form({"name": "A", "email": "", "phone": "", "message": "hi"})


@pytest.mark.parametrize("missing", ["name", "message"])
def test_web_form_requires_name_and_message(missing):
    payload = {"name": "A", "email": "a@b.co", "phone": "", "message": "hi"}
    payload[missing] = "  "
    with pytest.raises(ValueError, match=missing):
        normalize_web_form(payload)


def test_whatsapp_requires_a_usable_number_and_text():
    with pytest.raises(ValueError, match="from"):
        normalize_whatsapp({"from": "abc", "profile_name": "x", "text": "hi"})
    with pytest.raises(ValueError, match="text"):
        normalize_whatsapp({"from": "14155550142", "profile_name": "x", "text": ""})


def test_every_locked_eval_payload_normalizes():
    for e in TEST_SET:
        fn = normalize_web_form if e["channel"] == "web_form" else normalize_whatsapp
        lead = fn(e["payload"])
        assert lead.channel == e["channel"], e["id"]


def test_same_person_events_share_a_normalized_phone_across_channels():
    leads = {}
    for e in TEST_SET:
        fn = normalize_web_form if e["channel"] == "web_form" else normalize_whatsapp
        leads[e["id"]] = fn(e["payload"])
    for a, b in [(1, 2), (3, 9), (4, 10)]:
        assert leads[a].normalized_phone == leads[b].normalized_phone is not None
    # the near-miss shares neither phone nor email with the person it resembles
    assert leads[8].normalized_phone != leads[1].normalized_phone
    assert leads[8].normalized_email != leads[1].normalized_email
