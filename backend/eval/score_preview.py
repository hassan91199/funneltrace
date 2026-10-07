"""Manual smoke run: score the 10 eval events with the real model and print the result
next to the locked expectation. Not the formal eval (that is FT-10); no database needed.

    OPENAI_API_KEY=... python -m eval.score_preview
"""

from eval.test_set import TEST_SET
from funneltrace.config import Settings
from funneltrace.intake import normalize_web_form, normalize_whatsapp
from funneltrace.openai_llm import OpenAILLM
from funneltrace.repository import InMemoryLeadRepository
from funneltrace.scoring import ScoringError, score_lead


def main() -> None:
    settings = Settings(database_url="unused", **_openai_settings())
    llm = OpenAILLM(settings.openai_api_key, settings.openai_model)
    repo = InMemoryLeadRepository()
    print(f"model: {llm.model}")
    for event in TEST_SET:
        normalize = normalize_web_form if event["channel"] == "web_form" else normalize_whatsapp
        stored = repo.add_lead(normalize(event["payload"]))
        context = repo.get_context(stored.lead_id)
        try:
            result = score_lead(llm, context.name, context.messages)
            got = f"{result.category} ({result.confidence:.2f}) {result.reasoning}"
        except ScoringError as exc:
            got = f"ERROR {exc}"
        print(f"#{event['id']:<2} expected {event['expected_category']:<5} got {got}")


def _openai_settings() -> dict:
    import os

    return {
        "openai_api_key": os.environ["OPENAI_API_KEY"],
        "openai_model": os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
    }


if __name__ == "__main__":
    main()
