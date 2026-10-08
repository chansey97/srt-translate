import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
import srt


@pytest.fixture
def user_config_file(tmp_path, monkeypatch):
    directory = tmp_path / "user-config"
    (directory / "srt-translate").mkdir(parents=True)
    monkeypatch.setattr("srt_translate.config.user_config_path", lambda appname, **kwargs: directory / appname)
    return directory / "srt-translate" / "config.toml"


@pytest.fixture
def make_srt(tmp_path):
    def make(entries, *, filename="input.srt", encoding="utf-8", eol="\r\n"):
        path = tmp_path / filename
        subtitles = [
            srt.Subtitle(
                index=n, start=timedelta(seconds=position * 2),
                end=timedelta(seconds=position * 2 + 1), content=text,
            )
            for position, (n, text) in enumerate(entries)
        ]
        path.write_bytes(srt.compose(subtitles, reindex=False, eol=eol).encode(encoding))
        return path
    return make


@pytest.fixture
def make_entity():
    def make(source, translation, *, scores=(0.9, 0.9, 0.9), **overrides):
        return {
            "source": source,
            "context": f"Hello, {source}.",
            "reasoning": "The name identifies a character in the dialogue.",
            "type": "character",
            "subtype": "person",
            "translation": translation,
            "entity_confidence": scores[0],
            "type_confidence": scores[1],
            "translation_confidence": scores[2],
            **overrides,
        }
    return make


@pytest.fixture
def api_response():
    def make(data=None, *, content=None, finish_reason="stop", refusal=None):
        if data is not None:
            content = json.dumps(data, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(content=content, refusal=refusal),
        )])
    return make


@pytest.fixture
def fake_client(api_response):
    class FakeClient:
        def __init__(self, responses=(), *, handler=None):
            self.responses = iter(responses)
            self.handler = handler
            self.calls = []
            self.closed = False
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            self.calls.append(kwargs)
            result = self.handler(kwargs) if self.handler is not None else next(self.responses)
            if isinstance(result, Exception):
                raise result
            return api_response(result) if isinstance(result, dict) else result

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

    return FakeClient
