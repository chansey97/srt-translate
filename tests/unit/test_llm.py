import json
from types import SimpleNamespace

import pytest

from srt_translate.llm import request_json
from srt_translate.prompts import DISCOVER_ENTITIES_PROMPT, translation_prompt
from srt_translate.schemas import EntitiesResponse, TranslationResponse


@pytest.mark.parametrize("model,field", [(EntitiesResponse, "entities"), (TranslationResponse, "entries")])
def test_strict_object_schemas(model, field):
    schema = model.model_json_schema()
    for obj in [schema, *schema["$defs"].values()]:
        assert obj["type"] == "object"
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    assert list(schema["properties"]) == [field]
    if model is EntitiesResponse:
        fields = schema["$defs"]["Entity"]["properties"]
        assert len(fields) == 9
        for field_name in ["type", "subtype"]:
            assert fields[field_name]["type"] == "string"
            assert "enum" not in fields[field_name]
        for field_name in ["entity_confidence", "type_confidence", "translation_confidence"]:
            assert fields[field_name]["minimum"] == 0
            assert fields[field_name]["maximum"] == 1
        assert fields["source"]["minLength"] == 1


def test_request_shape_and_no_local_schema_validation(fake_client):
    data = {"entries": [{"n": 7, "text": "你好", "extra": "trusted"}]}
    client = fake_client([data])
    payload = {"source_lang": "en", "target_lang": "zh-Hans", "entries": []}
    assert request_json(client=client, model="test-model", system_prompt="提示", payload=payload, response_model=TranslationResponse) == data
    request = client.calls[0]
    assert set(request) == {"model", "stream", "messages", "response_format"}
    assert request["model"] == "test-model"
    assert request["stream"] is False
    assert request["messages"][0] == {"role": "system", "content": "提示"}
    assert json.loads(request["messages"][1]["content"]) == payload
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "TranslationResponse", "strict": True, "schema": TranslationResponse.model_json_schema()},
    }


@pytest.mark.parametrize("delay,expected", [(0.0, ["call", "call"]), (1.5, [1.5, "call", 1.5, "call"])])
def test_delay_before_every_call(monkeypatch, fake_client, delay, expected):
    events = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", events.append)
    def respond(request):
        events.append("call")
        return {"entities": []}
    client = fake_client(handler=respond)
    for _ in range(2):
        request_json(client=client, model="test", system_prompt="prompt", payload={}, response_model=EntitiesResponse, delay_between_requests=delay)
    assert events == expected


@pytest.mark.parametrize("kwargs,message", [
    ({"finish_reason": "length", "content": "{}"}, "finish_reason"),
    ({"finish_reason": "content_filter", "content": "{}"}, "finish_reason"),
    ({"finish_reason": None, "content": "{}"}, "finish_reason"),
    ({"content": "{}", "refusal": "refused"}, "refused"),
    ({"content": None}, "no text"),
    ({"content": ""}, "no text"),
    ({"content": "not JSON"}, "Expecting value"),
])
def test_failed_responses_are_not_parsed_as_success(fake_client, api_response, kwargs, message):
    client = fake_client([api_response(**kwargs)])
    with pytest.raises(ValueError, match=message):
        request_json(client=client, model="test", system_prompt="prompt", payload={}, response_model=EntitiesResponse)
    assert len(client.calls) == 1


def test_no_choices_and_sdk_errors_propagate(fake_client):
    for response, expected in [(SimpleNamespace(choices=[]), IndexError), (RuntimeError("SDK failed"), RuntimeError)]:
        client = fake_client([response])
        with pytest.raises(expected):
            request_json(client=client, model="test", system_prompt="prompt", payload={}, response_model=EntitiesResponse)
        assert len(client.calls) == 1


def test_prompt_language_and_term_modes():
    for prompt in [DISCOVER_ENTITIES_PROMPT, translation_prompt(), translation_prompt(True)]:
        assert "BCP 47" in prompt
        assert "source_lang" in prompt and "target_lang" in prompt
        assert "zh-Hans" in prompt and "zh-Hant" in prompt
    assert "reasoning 用一句简短的英文" in DISCOVER_ENTITIES_PROMPT
    assert "glossary 是原词到译名的映射" in translation_prompt()
    assert "do_not_translate_terms" not in translation_prompt()
    assert "do_not_translate_terms" in translation_prompt(True)
    assert "glossary 是原词到译名的映射" not in translation_prompt(True)
    assert r"{\c&H00FFFF&}" in translation_prompt()
