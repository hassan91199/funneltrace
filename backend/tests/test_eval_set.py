from collections import Counter, defaultdict

from eval.test_set import CATEGORIES, TEST_SET


def test_ten_leads_with_sequential_ids():
    assert [e["id"] for e in TEST_SET] == list(range(1, 11))


def test_every_event_has_the_graded_fields():
    for e in TEST_SET:
        assert e["channel"] in {"web_form", "whatsapp"}
        assert e["expected_category"] in CATEGORIES
        assert e["person"]
        assert e["draft_must_address"], e["id"]
        assert e["expected_crm"]["action"] in {"create", "update"}
        assert e["expected_crm"]["lifecycle_stage"]
        assert e["notes"]


def test_payload_shape_matches_channel():
    for e in TEST_SET:
        keys = set(e["payload"])
        if e["channel"] == "web_form":
            assert keys == {"name", "email", "phone", "message"}, e["id"]
        else:
            assert keys == {"from", "profile_name", "text"}, e["id"]


def test_spread_of_hot_warm_cold():
    counts = Counter(e["expected_category"] for e in TEST_SET)
    assert all(counts[c] >= 2 for c in CATEGORIES)


def test_same_person_on_both_channels_exists():
    channels = defaultdict(set)
    for e in TEST_SET:
        channels[e["person"]].add(e["channel"])
    assert any(len(c) == 2 for c in channels.values())


def test_dedup_expectations_are_consistent():
    seen = set()
    for e in TEST_SET:
        is_new = e["person"] not in seen
        assert e["expect_new_lead"] is is_new, e["id"]
        # A repeat contact must update the existing CRM contact, never create a second one.
        assert e["expected_crm"]["action"] == ("create" if is_new else "update"), e["id"]
        seen.add(e["person"])


def test_has_a_near_miss_that_must_not_merge():
    near_miss = [e for e in TEST_SET if e.get("near_miss_of")]
    assert near_miss
    by_id = {e["id"]: e for e in TEST_SET}
    for e in near_miss:
        assert e["expect_new_lead"] is True
        assert e["person"] != by_id[e["near_miss_of"]]["person"]
