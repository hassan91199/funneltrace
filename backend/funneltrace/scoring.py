import re
from dataclasses import dataclass

from funneltrace.interfaces import LeadLLM, LLMRefusal

CATEGORIES = ("hot", "warm", "cold")

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["category", "confidence", "reasoning"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You triage inbound sales leads for a small home-services company (HVAC, plumbing, \
remodels). Classify the lead from what the person actually wrote, not from keywords.

Categories:
- hot: clear intent to buy now (urgent need, near-term timeline, budget or a decision \
date). Ready for same-day human contact.
- warm: real interest but no urgency: a genuine need with a longer timeline, or still \
gathering information.
- cold: not a buyer: browsing with no intent, or a vendor soliciting us.

Answer with JSON: "category" (hot, warm or cold), "confidence" (0 to 1: how sure you \
are of the category) and "reasoning" (one short sentence a salesperson can read to see \
why). If the lead has written several times, score the lead as they stand now, using \
the whole conversation.
"""


class ScoringError(Exception):
    """The model refused, or returned something that is not a valid score."""


@dataclass(frozen=True)
class ScoreResult:
    category: str
    confidence: float
    reasoning: str


def parse_score(raw: object) -> ScoreResult:
    if not isinstance(raw, dict):
        raise ScoringError(f"expected a JSON object, got {type(raw).__name__}")

    category = raw.get("category")
    category = category.strip().lower() if isinstance(category, str) else category
    if category not in CATEGORIES:
        raise ScoringError(f"invalid category: {raw.get('category')!r}")

    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        raise ScoringError(f"invalid confidence: {confidence!r}")
    if not 0 <= confidence <= 1:
        raise ScoringError(f"confidence out of range: {confidence!r}")

    reasoning = raw.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ScoringError("missing reasoning")
    return ScoreResult(category, float(confidence), re.sub(r"\s+", " ", reasoning).strip())


def score_lead(llm: LeadLLM, name: str, messages: list[tuple[str, str]]) -> ScoreResult:
    conversation = "\n".join(f"[{channel}] {body}" for channel, body in messages)
    user = f"Lead name: {name}\nMessages, oldest first:\n{conversation}"
    try:
        raw = llm.complete_json(SYSTEM_PROMPT, user, SCORE_SCHEMA)
    except LLMRefusal as exc:
        raise ScoringError(f"model refused to score: {exc}") from exc
    except ValueError as exc:
        raise ScoringError(f"model returned invalid JSON: {exc}") from exc
    return parse_score(raw)
