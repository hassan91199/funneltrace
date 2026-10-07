from types import SimpleNamespace

import pytest

from funneltrace.interfaces import LeadLLM, LLMRefusal
from funneltrace.openai_llm import OpenAILLM

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def completion(content=None, refusal=None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, result):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._result = result

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


def test_satisfies_the_llm_protocol():
    assert isinstance(OpenAILLM(client=FakeClient(completion("{}")), model="m"), LeadLLM)


def test_complete_json_requests_strict_structured_output_and_parses_it():
    client = FakeClient(completion('{"a": "x"}'))
    llm = OpenAILLM(client=client, model="gpt-test")
    assert llm.complete_json("sys", "usr", SCHEMA) == {"a": "x"}
    call = client.calls[0]
    assert call["model"] == "gpt-test"
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    fmt = call["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == SCHEMA


def test_refusal_is_raised_not_returned():
    llm = OpenAILLM(client=FakeClient(completion(refusal="no")), model="m")
    with pytest.raises(LLMRefusal):
        llm.complete_json("s", "u", SCHEMA)


def test_non_json_content_raises_a_value_error():
    llm = OpenAILLM(client=FakeClient(completion("not json")), model="m")
    with pytest.raises(ValueError):
        llm.complete_json("s", "u", SCHEMA)


def test_complete_text_returns_the_message_content():
    llm = OpenAILLM(client=FakeClient(completion("hello")), model="m")
    assert llm.complete_text("s", "u") == "hello"
