class FakeLLM:
    """Scripted LLM for the default suite: no network, records every call.

    `json_responses` answers every complete_json call in order (last one repeats).
    `score` / `draft` answer by request kind instead, for flows that make both calls."""

    model = "fake-model"

    def __init__(self, json_responses=None, text_responses=None, score=None, draft=None):
        self._json = list(json_responses or [])
        self._text = list(text_responses or [])
        self._by_kind = {"score": _as_list(score), "draft": _as_list(draft)}
        self.json_calls: list[tuple[str, str, dict]] = []
        self.text_calls: list[tuple[str, str]] = []

    def complete_json(self, system, user, schema):
        self.json_calls.append((system, user, schema))
        kind = "score" if "category" in schema["properties"] else "draft"
        queue = self._by_kind[kind] or self._json
        response = _next(queue)
        if isinstance(response, Exception):
            raise response
        return response

    def complete_text(self, system, user):
        self.text_calls.append((system, user))
        return _next(self._text)


def _as_list(value):
    return [] if value is None else value if isinstance(value, list) else [value]


def _next(queue):
    return queue.pop(0) if len(queue) > 1 else queue[0]
