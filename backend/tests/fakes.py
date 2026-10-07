class FakeLLM:
    """Scripted LLM for the default suite: no network, records every call."""

    model = "fake-model"

    def __init__(self, json_responses=None, text_responses=None):
        self._json = list(json_responses or [])
        self._text = list(text_responses or [])
        self.json_calls: list[tuple[str, str, dict]] = []
        self.text_calls: list[tuple[str, str]] = []

    def complete_json(self, system, user, schema):
        self.json_calls.append((system, user, schema))
        response = self._json.pop(0) if len(self._json) > 1 else self._json[0]
        if isinstance(response, Exception):
            raise response
        return response

    def complete_text(self, system, user):
        self.text_calls.append((system, user))
        return self._text.pop(0) if len(self._text) > 1 else self._text[0]
