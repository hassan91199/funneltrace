import pytest

from funneltrace.interfaces import LLMRefusal
from funneltrace.scoring import SCORE_SCHEMA, ScoreResult, ScoringError, parse_score, score_lead
from tests.fakes import FakeLLM

GOOD = {"category": "hot", "confidence": 0.92, "reasoning": "Furnace out, budget approved."}


def test_parses_a_valid_response():
    assert parse_score(GOOD) == ScoreResult("hot", 0.92, "Furnace out, budget approved.")


def test_category_is_case_and_whitespace_insensitive():
    assert parse_score({**GOOD, "category": " Warm "}).category == "warm"


def test_reasoning_is_collapsed_to_one_line():
    result = parse_score({**GOOD, "reasoning": "Urgent.\n  Has budget.\n"})
    assert result.reasoning == "Urgent. Has budget."


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {**GOOD, "category": "lukewarm"},
        {**GOOD, "category": None},
        {**GOOD, "confidence": 1.5},
        {**GOOD, "confidence": -0.1},
        {**GOOD, "confidence": "high"},
        {**GOOD, "confidence": True},
        {**GOOD, "reasoning": ""},
        {**GOOD, "reasoning": "   "},
        {**GOOD, "reasoning": 42},
        {"category": "hot", "confidence": 0.9},
        "not a dict",
    ],
)
def test_malformed_output_is_rejected(bad):
    with pytest.raises(ScoringError):
        parse_score(bad)


def test_schema_demands_exactly_the_three_fields():
    assert SCORE_SCHEMA["required"] == ["category", "confidence", "reasoning"]
    assert SCORE_SCHEMA["properties"]["category"]["enum"] == ["hot", "warm", "cold"]
    assert SCORE_SCHEMA["additionalProperties"] is False


def test_score_lead_sends_the_definitions_the_name_and_every_message_in_order():
    llm = FakeLLM(json_responses=[GOOD])
    result = score_lead(
        llm,
        "Daniel Okafor",
        [("web_form", "Planning a kitchen remodel."), ("whatsapp", "Can you come Thursday?")],
    )
    assert result.category == "hot"
    (system, user, schema) = llm.json_calls[0]
    assert schema == SCORE_SCHEMA
    for word in ("hot", "warm", "cold"):
        assert word in system
    assert "Daniel Okafor" in user
    assert user.index("Planning a kitchen remodel.") < user.index("Can you come Thursday?")
    assert "web_form" in user and "whatsapp" in user


def test_score_lead_wraps_a_refusal():
    llm = FakeLLM(json_responses=[LLMRefusal("I can't help with that")])
    with pytest.raises(ScoringError, match="refused"):
        score_lead(llm, "X", [("web_form", "hi")])


def test_score_lead_wraps_malformed_output():
    llm = FakeLLM(json_responses=[{"category": "maybe"}])
    with pytest.raises(ScoringError):
        score_lead(llm, "X", [("web_form", "hi")])
