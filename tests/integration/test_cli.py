import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from srt_translate import cli
from srt_translate.common import read_json, read_srt, write_json


pytestmark = pytest.mark.usefixtures("user_config_file")


def test_complete_pipeline_and_reuse(tmp_path, make_srt, make_entity, fake_client, monkeypatch):
    source = make_srt([(10, "Elias is here."), (7, "Hello, Alexia."), (35, "Elias, wait!")])
    original = source.read_bytes()
    background = tmp_path / "background.txt"
    background.write_text("A story about Elias and Alexia.", encoding="utf-8-sig")
    output_base = tmp_path / "explicit-parent"
    output = output_base / "input__en_to_zh-Hans"
    client = fake_client([
        {"entities": [make_entity("Elias", "旧名", scores=(0.5, 0.5, 0.5)), make_entity("Alexia", "阿莱克西亚")]},
        {"entities": [make_entity("Elias", "伊莱亚斯")]},
        {"entries": [{"n": 10, "text": "伊莱亚斯来了。"}, {"n": 7, "text": "你好，阿莱克西亚。"}]},
        {"entries": [{"n": 35, "text": "伊莱亚斯，等等！"}]},
    ])
    configurations = []
    def new_client(**kwargs):
        configurations.append(kwargs)
        return client
    monkeypatch.setattr(cli, "OpenAI", new_client)
    waits = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", waits.append)
    args = [str(source), "--source-lang", "en", "--output-dir", str(output_base), "--chunk-size", "2", "--background", str(background), "--delay-between-requests", "0.1"]
    assert cli.main(args) == 0
    assert configurations == [{"base_url": "http://127.0.0.1:8317/v1", "api_key": "123456", "max_retries": 2}]
    assert client.closed
    assert len(client.calls) == 4
    assert all(call["model"] == "gemini-3.8-flash-high" for call in client.calls)
    assert waits == [0.1] * 4
    for directory in ["entries", "entities", "glossary_subsets", "translations"]:
        assert sorted(path.name for path in (output / directory).glob("*.json")) == ["000001_000002.json", "000003_000003.json"]
    assert read_json(output / "glossary.json") == {"Alexia": "阿莱克西亚", "Elias": "伊莱亚斯"}
    payloads = [json.loads(call["messages"][1]["content"]) for call in client.calls]
    assert all(payload["source_lang"] == "en" and payload["target_lang"] == "zh-Hans" for payload in payloads)
    assert all(payload["background"] == "A story about Elias and Alexia." for payload in payloads)
    assert payloads[2]["glossary"] == {"Alexia": "阿莱克西亚", "Elias": "伊莱亚斯"}
    assert payloads[2]["history"] == []
    assert payloads[3]["history"] == [
        {"n": 10, "source": "Elias is here.", "translation": "伊莱亚斯来了。"},
        {"n": 7, "source": "Hello, Alexia.", "translation": "你好，阿莱克西亚。"},
    ]
    final = output / "backfill" / source.name
    assert [(s.index, s.content) for s in read_srt(final)] == [(10, "伊莱亚斯来了。"), (7, "你好，阿莱克西亚。"), (35, "伊莱亚斯，等等！")]
    assert source.read_bytes() == original

    # No downstream readers run when every target exists, even after manual edits.
    (output / "glossary.json").write_text("manual glossary edit", encoding="utf-8")
    (output / "translations" / "000001_000002.json").write_text("manual translation edit", encoding="utf-8")
    final.write_text("manual final SRT edit", encoding="utf-8")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in output.rglob("*") if path.is_file()}
    assert cli.main(args) == 0
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in output.rglob("*") if path.is_file()}
    assert before == after
    assert len(client.calls) == 4
    assert waits == [0.1] * 4


@pytest.mark.parametrize("extra", [
    ["--chunk-size", "0"], ["--chunk-size", "-1"], ["--chunk-size", "1.5"],
    ["--history-size", "-1"], ["--history-size", "x"],
    ["--delay-between-requests=-1"], ["--delay-between-requests=nan"],
    ["--delay-between-requests=inf"], ["--delay-between-requests=-inf"],
    ["--delay-between-requests=1e999"],
    ["--source-lang", ""], ["--source-lang", "中文"],
    ["--source-lang", "en_US"], ["--target-lang", "../../en"],
    ["--target-lang", "en US"],
    ["--from-stage", "translate", "--to-stage", "extract"],
    ["--to-stage", "unknown"],
])
def test_cli_rejects_invalid_parameters(tmp_path, monkeypatch, extra):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as caught:
        cli.main(["missing.srt", "--source-lang", "en", *extra])
    assert caught.value.code == 2
    assert not (tmp_path / "missing__en_to_zh-Hans").exists()


@pytest.mark.parametrize("args", [[], ["input.srt"], ["--source-lang", "en"]])
def test_cli_requires_input_and_source_language(args):
    with pytest.raises(SystemExit) as caught:
        cli.main(args)
    assert caught.value.code == 2


def test_cli_defaults_and_tag_passthrough():
    args = cli.build_parser().parse_args(["input.srt", "--source-lang", "x-MyLang-123"])
    assert args.source_lang == "x-MyLang-123"
    assert args.target_lang == "zh-Hans"
    assert args.output_dir == Path(".")
    assert args.config_file is None
    assert args.history_size == 5 and args.chunk_size == 20
    assert args.no_translate_glossary is False
    assert args.delay_between_requests == 0.0
    args = cli.build_parser().parse_args(["input.srt", "--source-lang", "ja", "--target-lang", "zh-Hans-CN", "--no-translate-glossary", "--history-size", "0"])
    assert args.target_lang == "zh-Hans-CN" and args.no_translate_glossary is True
    assert args.history_size == 0


def test_default_output_directories_resume_and_explicit_path(tmp_path, make_srt, monkeypatch):
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    def unexpected_client(**kwargs):
        pytest.fail("A local stage must not create an API client")
    monkeypatch.setattr(cli, "OpenAI", unexpected_client)
    for filename, source_lang, target_lang in [
        ("one.srt", "en", "zh-Hans"), ("two.srt", "en", "zh-Hans"),
        ("one.srt", "en", "ja"), ("one.srt", "fr", "zh-Hans"),
        ("show.episode.one.srt", "en", "zh-Hans"), ("字幕集.srt", "ja", "en"),
    ]:
        source = make_srt([(1, "line")], filename=filename)
        args = [str(source), "--source-lang", source_lang, "--target-lang", target_lang, "--to-stage", "extract"]
        assert cli.main(args) == 0
        expected = working_dir / f"{source.stem}__{source_lang}_to_{target_lang}" / "entries" / "000001_000001.json"
        assert expected.exists()
        expected.write_text("edited", encoding="utf-8")
        assert cli.main(args) == 0
        assert expected.read_text(encoding="utf-8") == "edited"
        assert cli.main([*args, "--output-dir", "./"]) == 0
        assert expected.read_text(encoding="utf-8") == "edited"
    assert not (working_dir / "entries").exists()
    assert not (working_dir / "outputs").exists()
    assert cli.main([str(tmp_path / "one.srt"), "--source-lang", "en", "--output-dir", "custom", "--to-stage", "extract"]) == 0
    assert (working_dir / "custom" / "one__en_to_zh-Hans" / "entries" / "000001_000001.json").exists()
    assert not (working_dir / "custom" / "entries").exists()


def test_single_subsets_stage_uses_only_its_inputs(tmp_path, monkeypatch):
    def unexpected_client(**kwargs):
        pytest.fail("Subset generation must not create an API client")
    monkeypatch.setattr(cli, "OpenAI", unexpected_client)
    output = tmp_path / "missing__en_to_zh-Hans"
    write_json(output / "entities" / "000001_000001.json", [{"source": "Elias"}])
    write_json(output / "glossary.json", {"Elias": "人工译名"})
    assert cli.main([str(tmp_path / "missing.srt"), "--source-lang", "en", "--output-dir", str(tmp_path), "--from-stage", "subsets", "--to-stage", "subsets"]) == 0
    assert read_json(output / "glossary_subsets" / "000001_000001.json") == {"Elias": "人工译名"}
    assert not (output / "entries").exists()
    assert not (output / "translations").exists()


def test_cli_term_mode_and_delay_reach_translation(tmp_path, fake_client, monkeypatch):
    name = "000001_000001.json"
    output = tmp_path / "missing__en_to_zh-Hant"
    write_json(output / "entries" / name, [{"n": 8, "text": "Elias"}])
    write_json(output / "glossary_subsets" / name, {"Elias": "译名"})
    client = fake_client([{"entries": [{"n": 8, "text": "Elias"}]}])
    monkeypatch.setattr(cli, "OpenAI", lambda **kwargs: client)
    waits = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", waits.append)
    assert cli.main(["missing.srt", "--source-lang", "en", "--target-lang", "zh-Hant", "--output-dir", str(tmp_path), "--from-stage", "translate", "--to-stage", "translate", "--no-translate-glossary", "--history-size", "0", "--delay-between-requests", "1.25"]) == 0
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert payload["do_not_translate_terms"] == ["Elias"] and "glossary" not in payload
    assert payload["target_lang"] == "zh-Hant"
    assert waits == [1.25]


def test_cli_failure_reports_stage_and_path_and_keeps_outputs(tmp_path, make_srt, fake_client, monkeypatch, capsys):
    source = make_srt([(1, "one")])
    client = fake_client([RuntimeError("SDK failed")])
    monkeypatch.setattr(cli, "OpenAI", lambda **kwargs: client)
    output = tmp_path / "input__en_to_zh-Hans"
    assert cli.main([str(source), "--source-lang", "en", "--output-dir", str(tmp_path)]) == 1
    error = capsys.readouterr().err
    assert "Error in discover: SDK failed" in error
    assert str(output / "entries" / "000001_000001.json") in error
    assert len(client.calls) == 1 and client.closed
    assert (output / "entries" / "000001_000001.json").exists()
    assert not (output / "glossary.json").exists()


def test_configuration_layers_reach_both_model_stages(tmp_path, make_srt, fake_client, monkeypatch, user_config_file):
    monkeypatch.chdir(tmp_path)
    source = make_srt([(1, "Hello")])
    user_config_file.write_text(
        '[openai]\nbase_url = "http://proxy.example/v1"\napi_key = "user-key"\nmodel = "user-model"\n',
        encoding="utf-8",
    )
    (tmp_path / "custom.toml").write_text(
        '[openai]\nmodel = "explicit-model"\nmax_retries = 0\n', encoding="utf-8",
    )
    client = fake_client([{"entities": []}, {"entries": [{"n": 1, "text": "你好"}]}])
    configurations = []
    def new_client(**kwargs):
        configurations.append(kwargs)
        return client
    monkeypatch.setattr(cli, "OpenAI", new_client)
    assert cli.main([str(source), "--source-lang", "en", "--config-file", "custom.toml"]) == 0
    assert configurations == [{"base_url": "http://proxy.example/v1", "api_key": "user-key", "max_retries": 0}]
    assert [call["model"] for call in client.calls] == ["explicit-model", "explicit-model"]
    assert client.closed
    assert (tmp_path / "input__en_to_zh-Hans" / "backfill" / "input.srt").exists()


@pytest.mark.parametrize("source_kind", ["missing-explicit", "invalid-explicit", "invalid-user"])
def test_configuration_errors_stop_before_local_stages(tmp_path, make_srt, user_config_file, source_kind, capsys):
    source = make_srt([(1, "Hello")])
    config_path = user_config_file if source_kind == "invalid-user" else tmp_path / "custom.toml"
    if source_kind != "missing-explicit":
        config_path.write_text('[openai]\nmodel = 42\n', encoding="utf-8")
    args = [str(source), "--source-lang", "en", "--output-dir", str(tmp_path), "--to-stage", "extract"]
    if source_kind != "invalid-user":
        args.extend(["--config-file", str(config_path)])
    with pytest.raises(SystemExit) as caught:
        cli.main(args)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "configuration error" in captured.err
    assert str(config_path) in captured.err
    assert captured.out == ""
    assert not (tmp_path / "input__en_to_zh-Hans").exists()


def test_help_does_not_load_configuration(user_config_file, capsys):
    user_config_file.write_text("invalid toml", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        cli.main(["--help"])
    assert caught.value.code == 0
    assert "--config-file PATH" in capsys.readouterr().out


def test_both_installed_entrypoints_have_identical_help():
    console = Path(sys.executable).with_name("srt-translate.exe" if os.name == "nt" else "srt-translate")
    module_result = subprocess.run([sys.executable, "-m", "srt_translate", "--help"], capture_output=True, text=True, check=True)
    console_result = subprocess.run([str(console), "--help"], capture_output=True, text=True, check=True)
    assert module_result.stdout == console_result.stdout
    assert "--no-translate-glossary" in module_result.stdout
    assert "--delay-between-requests" in module_result.stdout
    assert "--config-file PATH" in module_result.stdout
