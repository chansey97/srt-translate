from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

import pytest

from srt_translate.common import read_json, read_srt


def test_archive_contains_complete_application(portable_app):
    root = Path(__file__).resolve().parents[2]
    assert (portable_app / "srt-translate.exe").is_file()
    assert (portable_app / "_internal").is_dir()
    default = (root / "src" / "srt_translate" / "config.default.toml").read_bytes()
    assert (portable_app / "config.toml").read_bytes() == default
    assert (portable_app / "_internal" / "srt_translate" / "config.default.toml").read_bytes() == default
    assert (portable_app / "README.md").read_bytes() == (root / "README.md").read_bytes()
    assert not list(portable_app.rglob("PLAN.md"))


def test_help_does_not_require_valid_configuration(run_portable, portable_config_file):
    portable_config_file.write_text("invalid portable config", encoding="utf-8")
    result = run_portable("--help")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert "--config-file PATH" in result.stdout.decode("utf-8")


@pytest.mark.parametrize("redirect", [False, True])
def test_extract_with_packaged_defaults_and_utf8_output(
    run_portable, portable_config_file, tmp_path, make_srt, redirect,
):
    portable_config_file.unlink()
    source = make_srt([(7, "Hello 🎬")], filename="字幕 🎬.srt")
    result = run_portable(source, "--source-lang", "en", "--to-stage", "extract", redirect=redirect)
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert source.stem in result.stdout.decode("utf-8")
    assert result.stderr == b""
    entries = tmp_path / "字幕 🎬__en_to_zh-Hans" / "entries" / "000001_000001.json"
    assert read_json(entries) == [{"n": 7, "text": "Hello 🎬"}]


@pytest.mark.parametrize("redirect", [False, True])
@pytest.mark.parametrize("failure", ["stage", "config", "argument"])
def test_errors_preserve_exit_codes_and_utf8_paths(run_portable, tmp_path, redirect, failure):
    source = tmp_path / "缺失字幕 🎬.srt"
    args = [source, "--source-lang", "en", "--to-stage", "extract"]
    expected_text = str(source)
    if failure == "config":
        config_file = tmp_path / "缺失配置 🎬.toml"
        args += ["--config-file", config_file]
        expected_text = str(config_file)
    elif failure == "argument":
        args += ["--未知参数🎬"]
        expected_text = "--未知参数🎬"
    result = run_portable(*args, redirect=redirect)
    assert result.returncode == (1 if failure == "stage" else 2)
    assert expected_text in result.stderr.decode("utf-8")
    if failure == "stage":
        assert source.stem in result.stdout.decode("utf-8")
    else:
        assert result.stdout == b""
    assert not (tmp_path / "缺失字幕 🎬__en_to_zh-Hans").exists()


@pytest.fixture
def local_api():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, self.headers.get("Authorization"), request))
            schema_name = request["response_format"]["json_schema"]["name"]
            content = (
                {"entities": []} if schema_name == "EntitiesResponse"
                else {"entries": [{"n": 7, "text": "你好 🎬"}]}
            )
            response = json.dumps({
                "id": "chatcmpl-portable-test", "object": "chat.completion", "created": 0,
                "model": request["model"],
                "choices": [{
                    "index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
                }],
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("explicit", [False, True])
def test_frozen_pipeline_and_configuration_layers(
    run_portable, portable_config_file, tmp_path, make_srt, local_api, explicit,
):
    base_url, calls = local_api
    portable_config_file.write_text(
        f'[openai]\nbase_url = "{base_url}"\napi_key = "portable-key"\n'
        'model = "portable-model"\nmax_retries = 0\n', encoding="utf-8",
    )
    source = make_srt([(7, "Hello 🎬")], filename="字幕 🎬.srt")
    original = source.read_bytes()
    args = [source, "--source-lang", "en"]
    if explicit:
        config_file = tmp_path / "覆盖配置 🎬.toml"
        config_file.write_text('[openai]\nmodel = "explicit-model"\n', encoding="utf-8")
        args += ["--config-file", config_file]
    result = run_portable(*args)
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert len(calls) == 2
    assert all(path == "/v1/chat/completions" and auth == "Bearer portable-key" for path, auth, _ in calls)
    requests = [request for _, _, request in calls]
    assert all(request["model"] == ("explicit-model" if explicit else "portable-model") for request in requests)
    assert [request["response_format"]["json_schema"]["name"] for request in requests] == [
        "EntitiesResponse", "TranslationResponse",
    ]
    final = tmp_path / "字幕 🎬__en_to_zh-Hans" / "backfill" / source.name
    assert [(s.index, s.content) for s in read_srt(final)] == [(7, "你好 🎬")]
    assert str(final) in result.stdout.decode("utf-8")
    assert source.read_bytes() == original
