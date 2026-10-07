import json

from funneltrace.interfaces import LLMRefusal


class OpenAILLM:
    """LeadLLM backed by OpenAI chat completions with strict structured output."""

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini", client=None) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
        self._client = client
        self.model = model

    def _complete(self, system: str, user: str, **extra):
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **extra,
        )
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMRefusal(message.refusal)
        return message.content or ""

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        content = self._complete(
            system,
            user,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            },
        )
        return json.loads(content)

    def complete_text(self, system: str, user: str) -> str:
        return self._complete(system, user)
