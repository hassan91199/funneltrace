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
