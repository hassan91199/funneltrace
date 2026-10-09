import json

import httpx
import pytest

from funneltrace.crm import LIFECYCLE_STAGE, HubSpotCrm
from funneltrace.interfaces import CrmError

CONTACT = {
    "name": "Sarah Mitchell",
    "email": "sarah@x.co",
    "phone": "14155550142",
    "lifecycle_stage": "salesqualifiedlead",
}


def make(responses):
    """HubSpotCrm over a mock transport: `responses` is a queue of httpx.Response."""
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return responses.pop(0)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HubSpotCrm("tok", client=client), seen


def found(contact_id):
    return httpx.Response(200, json={"total": 1, "results": [{"id": contact_id}]})


def stage(current):
    """The GET that reads a contact's current lifecycle stage before an update."""
    return httpx.Response(200, json={"id": "x", "properties": {"lifecyclestage": current}})


NOT_FOUND = httpx.Response(200, json={"total": 0, "results": []})


def test_lifecycle_mapping_matches_the_locked_eval_expectations():
    assert LIFECYCLE_STAGE == {
        "hot": "salesqualifiedlead",
        "warm": "marketingqualifiedlead",
        "cold": "lead",
    }


def test_creates_a_contact_when_none_matches():
    crm, seen = make([NOT_FOUND, NOT_FOUND, httpx.Response(201, json={"id": "501"})])
    result = crm.upsert_contact(CONTACT)
    assert (result.external_id, result.action) == ("501", "create")
    create = seen[-1]
    assert create.method == "POST" and create.url.path == "/crm/v3/objects/contacts"
    assert create.headers["authorization"] == "Bearer tok"
    assert json.loads(create.content)["properties"] == {
        "email": "sarah@x.co",
        "phone": "+14155550142",
        "firstname": "Sarah",
        "lastname": "Mitchell",
        "lifecyclestage": "salesqualifiedlead",
    }


def test_finds_an_existing_contact_by_email_and_updates_it():
    crm, seen = make([found("77"), stage("lead"), httpx.Response(200, json={"id": "77"})])
    result = crm.upsert_contact(CONTACT)
    assert (result.external_id, result.action) == ("77", "update")
    search = json.loads(seen[0].content)
    assert search["filterGroups"][0]["filters"][0] == {
        "propertyName": "email",
        "operator": "EQ",
        "value": "sarah@x.co",
    }
    assert seen[-1].method == "PATCH" and seen[-1].url.path == "/crm/v3/objects/contacts/77"


def test_falls_back_to_phone_when_email_finds_nothing():
    crm, seen = make(
        [NOT_FOUND, found("78"), stage("lead"), httpx.Response(200, json={"id": "78"})]
    )
    assert crm.upsert_contact(CONTACT).external_id == "78"
    phone_filter = json.loads(seen[1].content)["filterGroups"][0]["filters"][0]
    # CONTAINS_TOKEN on the digits: found immediately, while EQ lags behind HubSpot's indexing.
    assert phone_filter == {
        "propertyName": "phone",
        "operator": "CONTAINS_TOKEN",
        "value": "14155550142",
    }


def test_a_known_external_id_skips_the_search():
    crm, seen = make([stage("lead"), httpx.Response(200, json={"id": "9"})])
    result = crm.upsert_contact({**CONTACT, "external_id": "9"})
    assert (result.external_id, result.action) == ("9", "update")
    assert [r.method for r in seen] == ["GET", "PATCH"]


def test_phone_only_contacts_skip_the_email_search_and_blank_fields_are_not_sent():
    crm, seen = make([NOT_FOUND, httpx.Response(201, json={"id": "5"})])
    crm.upsert_contact(
        {
            "name": "+14155550142",  # WhatsApp fallback name: not a real name
            "email": None,
            "phone": "14155550142",
            "lifecycle_stage": "lead",
        }
    )
    assert json.loads(seen[0].content)["filterGroups"][0]["filters"][0]["propertyName"] == "phone"
    assert json.loads(seen[1].content)["properties"] == {
        "phone": "+14155550142",
        "lifecyclestage": "lead",
    }


def test_single_word_names_become_a_first_name_only():
    crm, seen = make([NOT_FOUND, NOT_FOUND, httpx.Response(201, json={"id": "5"})])
    crm.upsert_contact({**CONTACT, "name": "Priya"})
    props = json.loads(seen[-1].content)["properties"]
    assert props["firstname"] == "Priya" and "lastname" not in props


def lifecycle_patches(seen):
    return [
        json.loads(r.content)["properties"].get("lifecyclestage")
        for r in seen
        if r.method == "PATCH"
    ]


def test_moving_to_an_earlier_stage_clears_it_first_because_hubspot_ignores_a_direct_downgrade():
    crm, seen = make(
        [stage("salesqualifiedlead"), httpx.Response(200, json={}), httpx.Response(200, json={})]
    )
    crm.upsert_contact({**CONTACT, "external_id": "9", "lifecycle_stage": "marketingqualifiedlead"})
    assert lifecycle_patches(seen) == ["", "marketingqualifiedlead"]


def test_moving_forward_or_staying_put_is_a_single_update():
    crm, seen = make([stage("lead"), httpx.Response(200, json={})])
    crm.upsert_contact({**CONTACT, "external_id": "9"})
    assert lifecycle_patches(seen) == ["salesqualifiedlead"]


def test_a_stage_outside_our_three_is_never_overwritten():
    crm, seen = make([stage("customer"), httpx.Response(200, json={})])
    crm.upsert_contact({**CONTACT, "external_id": "9", "lifecycle_stage": "lead"})
    assert lifecycle_patches(seen) == [None]  # the PATCH carries no lifecyclestage at all


@pytest.mark.parametrize("status", [401, 409, 429, 500])
def test_http_errors_become_crm_errors_with_the_status(status):
    crm, _ = make([httpx.Response(status, json={"message": "nope"})])
    with pytest.raises(CrmError, match=str(status)):
        crm.upsert_contact(CONTACT)


def test_network_failures_become_crm_errors():
    def boom(request):
        raise httpx.ConnectError("no route")

    crm = HubSpotCrm("tok", client=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(CrmError, match="no route"):
        crm.upsert_contact(CONTACT)


def test_a_token_is_required():
    with pytest.raises(CrmError, match="HUBSPOT_ACCESS_TOKEN"):
        HubSpotCrm("")


def test_eval_helpers_read_find_and_delete_contacts():
    crm, seen = make(
        [
            httpx.Response(200, json={"id": "7", "properties": {"lifecyclestage": "lead"}}),
            found("7"),
            httpx.Response(204),
        ]
    )
    assert crm.get_contact("7") == {"lifecyclestage": "lead"}
    assert crm.find_contact(CONTACT) == "7"
    crm.delete_contact("7")
    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/crm/v3/objects/contacts/7"),
        ("POST", "/crm/v3/objects/contacts/search"),
        ("DELETE", "/crm/v3/objects/contacts/7"),
    ]
    assert seen[0].url.params["properties"] == "lifecyclestage,email,phone"
