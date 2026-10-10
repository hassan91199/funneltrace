import pytest

from funneltrace.drafting import (
    DRAFT_SCHEMA,
    DraftContent,
    DraftingError,
    draft_followup,
    parse_draft,
)
from funneltrace.interfaces import LLMRefusal
from funneltrace.scoring import ScoreResult
from tests.fakes import FakeLLM

GOOD = {"subject": "Re: your furnace", "body": "Hi Sarah,\n\nWe can visit this week.\n\nThanks"}
HOT = ScoreResult("hot", 0.9, "Urgent, has budget.")


def test_parses_a_valid_draft():
    assert parse_draft(GOOD) == DraftContent(GOOD["subject"], GOOD["body"])


def test_subject_is_one_line_but_body_keeps_its_paragraphs():
    draft = parse_draft({"subject": " Re:\n furnace ", "body": " Hi\n\nBye \n"})
    assert draft.subject == "Re: furnace"
    assert draft.body == "Hi\n\nBye"


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"subject": "s"},
        {"body": "b"},
        {"subject": "", "body": "b"},
        {"subject": "s", "body": " "},
        {"subject": 1, "body": "b"},
        {"subject": "s", "body": None},
        "nope",
    ],
)
def test_malformed_draft_is_rejected(bad):
    with pytest.raises(DraftingError):
        parse_draft(bad)


def test_schema_requires_subject_and_body():
    assert DRAFT_SCHEMA["required"] == ["subject", "body"]
    assert DRAFT_SCHEMA["additionalProperties"] is False


def test_prompt_carries_category_reasoning_and_the_whole_conversation():
    llm = FakeLLM(draft=GOOD)
    draft_followup(
        llm, "Sarah Mitchell", HOT, [("web_form", "Furnace died."), ("whatsapp", "Call me today")]
    )
    system, user, schema = llm.json_calls[0]
    assert schema == DRAFT_SCHEMA
    assert "price" in system.lower()  # never invent a quote
    assert "hot" in user and "Urgent, has budget." in user and "Sarah Mitchell" in user
    assert user.index("Furnace died.") < user.index("Call me today")


def test_refusal_and_bad_json_become_drafting_errors():
    with pytest.raises(DraftingError, match="refused"):
        draft_followup(FakeLLM(draft=LLMRefusal("no")), "X", HOT, [("web_form", "hi")])
    with pytest.raises(DraftingError):
        draft_followup(FakeLLM(draft=ValueError("bad json")), "X", HOT, [("web_form", "hi")])


def test_a_follow_up_is_marked_so_the_reply_answers_the_latest_message():
    llm = FakeLLM(draft=GOOD)
    draft_followup(
        llm,
        "Priya",
        ScoreResult("warm", 0.7, "Wants a tune-up."),
        [("whatsapp", "how much for a tune up?"), ("web_form", "before summer, no rush")],
    )
    _, user, _ = llm.json_calls[0]
    assert "following up" in user.lower()
    assert "whatsapp" in user and "web_form" in user
    earlier, latest = user.split("Latest message")
    assert "how much for a tune up?" in earlier and "before summer" not in earlier
    assert "before summer, no rush" in latest and "how much" not in latest


def test_a_first_message_is_not_framed_as_a_follow_up():
    llm = FakeLLM(draft=GOOD)
    draft_followup(llm, "Sarah", HOT, [("web_form", "Furnace died.")])
    _, user, _ = llm.json_calls[0]
    assert "following up" not in user.lower() and "Earlier" not in user
    assert "Furnace died." in user


def test_the_rules_say_to_use_the_latest_messages_specifics_without_naming_any_lead():
    from funneltrace.drafting import SYSTEM_PROMPT

    lowered = SYSTEM_PROMPT.lower()
    assert "latest message" in lowered and "timeline" in lowered
    assert "already" in lowered  # do not re-ask what was already answered or asked
    for name in ("priya", "sarah", "daniel", "tune-up", "summer"):
        assert name not in lowered
