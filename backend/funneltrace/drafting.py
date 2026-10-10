import re
from dataclasses import dataclass

from funneltrace.interfaces import LeadLLM, LLMRefusal
from funneltrace.scoring import ScoreResult

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You write the next reply to an inbound lead for a small home-services company (HVAC, \
plumbing, remodels). A human will read and approve it before anything is sent.

Rules:
- Write as the company team, in a warm, plain, brief voice. Address the person by first \
name. Reply to their latest message.
- If they have written before, they are following up: say so naturally ("thanks for \
following up"), refer to what they said earlier, and build on it. Do not ask for anything \
they have already told you, and do not answer again what was already answered or asked.
- Use the specifics in the latest message: any timeline, deadline, budget or new detail \
they give, and the channel change if they moved from one channel to another.
- Never invent a price, discount, availability slot or guarantee. Do not quote a price; \
offer to give an accurate quote after a short call or visit.
- Match the tone to the category:
  hot - act fast: acknowledge the urgency and offer a concrete next step (a call today, \
a visit this week); for an emergency, add one line of basic safety advice.
  warm - be helpful and unpressured: answer what you can at a high level, ask one or two \
details needed to help, and offer a consultation.
  cold - keep it short and low-pressure and leave the door open; if the sender is a \
vendor soliciting us, politely decline without engaging with the pitch.

Answer with JSON: "subject" (one short line) and "body" (the message, plain text).
"""


class DraftingError(Exception):
    """The model refused, or returned something that is not a usable draft."""


@dataclass(frozen=True)
class DraftContent:
    subject: str
    body: str


def parse_draft(raw: object) -> DraftContent:
    if not isinstance(raw, dict):
        raise DraftingError(f"expected a JSON object, got {type(raw).__name__}")
    subject, body = raw.get("subject"), raw.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise DraftingError("missing subject")
    if not isinstance(body, str) or not body.strip():
        raise DraftingError("missing body")
    return DraftContent(re.sub(r"\s+", " ", subject).strip(), body.strip())


def draft_followup(
    llm: LeadLLM, name: str, score: ScoreResult, messages: list[tuple[str, str]]
) -> DraftContent:
    def line(channel: str, body: str) -> str:
        return f"[{channel}] {body}"

    *earlier, latest = messages
    if earlier:
        history = "\n".join(line(c, b) for c, b in earlier)
        thread = (
            f"This person is following up: they have written {len(messages)} times, first on "
            f"{earlier[0][0]}, most recently on {latest[0]}.\n"
            f"Earlier messages, oldest first:\n{history}\n"
            f"Latest message (reply to this one):\n{line(*latest)}"
        )
    else:
        thread = f"Message:\n{line(*latest)}"
    user = (
        f"Lead name: {name}\n"
        f"Category: {score.category} (confidence {score.confidence:.2f})\n"
        f"Why: {score.reasoning}\n"
        f"{thread}"
    )
    try:
        raw = llm.complete_json(SYSTEM_PROMPT, user, DRAFT_SCHEMA)
    except LLMRefusal as exc:
        raise DraftingError(f"model refused to draft: {exc}") from exc
    except ValueError as exc:
        raise DraftingError(f"model returned invalid JSON: {exc}") from exc
    return parse_draft(raw)
