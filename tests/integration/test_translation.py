import json

import pytest

from srt_translate.common import read_json, write_json
from srt_translate.phase_discover_entities import discover_entities
from srt_translate.phase_translate import translate


def test_discovery_languages_background_schema_and_empty_entities(tmp_path, fake_client, make_entity, monkeypatch):
    name = "000001_000002.json"
    entries = [{"n": 251, "text": "[Elias] Alexia's right."}]
    entities = [make_entity("Elias", "イライアス", type="unrestricted_type", subtype="arbitrary_subtype")]
    write_json(tmp_path / "entries" / name, entries)
    write_json(tmp_path / "entries" / "000003_000003.json", [{"n": 7, "text": "Yes."}])
    background = tmp_path / "background.txt"
    background.write_bytes("故事背景".encode("utf-8-sig"))
    waits = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", waits.append)
    client = fake_client([{"entities": entities}, {"entities": []}])
    paths = discover_entities(
        tmp_path / "entries", tmp_path / "entities", source_lang="en", target_lang="ja",
        client=client, model="chosen-model", background_path=background, delay_between_requests=0.25,
    )
    assert [path.name for path in paths] == [name, "000003_000003.json"]
    assert read_json(paths[0]) == entities
    assert read_json(paths[1]) == []
    assert waits == [0.25, 0.25]
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert payload == {"source_lang": "en", "target_lang": "ja", "background": "故事背景", "entries": entries}
    assert client.calls[0]["response_format"]["json_schema"]["name"] == "EntitiesResponse"
    assert client.calls[0]["model"] == "chosen-model"


def test_discovery_skip_never_reads_target_or_inputs_or_sleeps(tmp_path, fake_client, monkeypatch):
    name = "000001_000001.json"
    write_json(tmp_path / "entries" / name, [])
    (tmp_path / "entries" / name).write_text("invalid", encoding="utf-8")
    output = tmp_path / "entities" / name
    write_json(output, [])
    output.write_text("edited, invalid JSON", encoding="utf-8")
    waits = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", waits.append)
    client = fake_client()
    assert discover_entities(
        tmp_path / "entries", tmp_path / "entities", source_lang="en", target_lang="ja",
        client=client, model="test", background_path=tmp_path / "missing.txt", delay_between_requests=2,
    ) == [output]
    assert output.read_text(encoding="utf-8") == "edited, invalid JSON"
    assert client.calls == waits == []


@pytest.mark.parametrize("no_translate,glossary", [
    (False, {"Zed": "Zed", "Alexia": "アレクシア", "manual": "覆盖"}),
    (True, {"Zed": "Zed", "Alexia": "アレクシア", "manual": "覆盖"}),
    (False, {}), (True, {}),
])
def test_translation_uses_subset_verbatim_and_mutually_exclusive_modes(tmp_path, fake_client, no_translate, glossary):
    name = "000001_000001.json"
    write_json(tmp_path / "entries" / name, [{"n": 10, "text": "Alexia and Zed."}])
    write_json(tmp_path / "subsets" / name, glossary)
    background = tmp_path / "background.txt"
    background.write_text("Background", encoding="utf-8")
    client = fake_client([{"entries": [{"n": 10, "text": "translated"}]}])
    translate(
        tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations",
        source_lang="en", target_lang="fr", client=client, model="test",
        no_translate_glossary=no_translate, background_path=background,
    )
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert payload["source_lang"] == "en" and payload["target_lang"] == "fr"
    assert payload["background"] == "Background"
    assert payload["history"] == []
    assert client.calls[0]["response_format"]["json_schema"]["name"] == "TranslationResponse"
    if no_translate:
        assert "glossary" not in payload
        assert payload["do_not_translate_terms"] == list(glossary)
    else:
        assert "do_not_translate_terms" not in payload
        assert payload["glossary"] == glossary


@pytest.mark.parametrize("history_size", [0, 1, 3, 5, 20])
def test_history_crosses_shards_and_joins_existing_translations_by_number(tmp_path, fake_client, history_size):
    chunks = [[31, 7], [99], [20, 15], [8]]
    previous = []
    for i, numbers in enumerate(chunks):
        name = f"{i + 1:06d}_{i + 1:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": n, "text": f"source {n}"} for n in numbers])
        if i < 3:
            # Existing files are trusted; lookup for history uses n, not array position.
            write_json(tmp_path / "translations" / name, [{"n": n, "text": f"译文 {n}"} for n in reversed(numbers)])
            previous.extend({"n": n, "source": f"source {n}", "translation": f"译文 {n}"} for n in numbers)
        else:
            write_json(tmp_path / "subsets" / name, {})
    client = fake_client([{"entries": [{"n": 8, "text": "eight"}]}])
    translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="zh-Hans", client=client, model="test", history_size=history_size)
    assert len(client.calls) == 1
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert payload["history"] == (previous[-history_size:] if history_size else [])


@pytest.mark.parametrize("history_size", [0, 1])
def test_unneeded_broken_history_is_not_read(tmp_path, fake_client, history_size):
    for i in range(1, 4):
        name = f"{i:06d}_{i:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": i, "text": f"source {i}"}])
        if i < 3:
            write_json(tmp_path / "translations" / name, [{"n": i, "text": f"translation {i}"}])
        else:
            write_json(tmp_path / "subsets" / name, {})
    (tmp_path / "entries" / "000001_000001.json").write_text("broken", encoding="utf-8")
    (tmp_path / "translations" / "000001_000001.json").write_text("broken", encoding="utf-8")
    if history_size == 0:
        (tmp_path / "translations" / "000002_000002.json").write_text("broken", encoding="utf-8")
    client = fake_client([{"entries": [{"n": 3, "text": "third"}]}])
    translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="zh-Hans", client=client, model="test", history_size=history_size)
    assert len(client.calls) == 1


@pytest.mark.parametrize("broken", ["json", "number"])
def test_required_bad_history_fails_before_call(tmp_path, fake_client, broken):
    for i in [1, 2]:
        name = f"{i:06d}_{i:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": i, "text": "source"}])
        write_json(tmp_path / "subsets" / name, {})
    previous = tmp_path / "translations" / "000001_000001.json"
    write_json(previous, [{"n": 999, "text": "wrong number"}])
    if broken == "json":
        previous.write_text("broken", encoding="utf-8")
    client = fake_client()
    with pytest.raises((ValueError, KeyError)) as caught:
        translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="ja", client=client, model="test")
    assert str(previous) in " ".join(caught.value.__notes__)
    assert client.calls == []
    assert not (tmp_path / "translations" / "000002_000002.json").exists()


def test_new_translations_and_edited_subset_feed_later_history(tmp_path, fake_client, monkeypatch):
    for i in range(1, 4):
        name = f"{i:06d}_{i:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": i, "text": "Elias"}])
        write_json(tmp_path / "subsets" / name, {"Elias": "本片人工译名"} if i == 2 else {})
    write_json(tmp_path / "translations" / "000001_000001.json", [{"n": 1, "text": "此前人工译文"}])
    payloads = []
    events = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", lambda value: events.append(("sleep", value)))
    def respond(request):
        payload = json.loads(request["messages"][1]["content"])
        payloads.append(payload)
        events.append(("call", payload["entries"][0]["n"]))
        text = payload["glossary"].get("Elias", "下一片译文")
        return {"entries": [{"n": payload["entries"][0]["n"], "text": text}]}
    client = fake_client(handler=respond)
    translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="zh-Hans", client=client, model="test", delay_between_requests=0.5)
    assert payloads[0]["history"] == [{"n": 1, "source": "Elias", "translation": "此前人工译文"}]
    assert payloads[1]["history"][-1] == {"n": 2, "source": "Elias", "translation": "本片人工译名"}
    assert events == [("sleep", 0.5), ("call", 2), ("sleep", 0.5), ("call", 3)]


@pytest.mark.parametrize("bad_entries,reason", [
    ([{"n": 251, "text": "one"}], "Expected 2 translations, got 1"),
    ([{"n": 251, "text": "one"}, {"n": 252, "text": "two"}, {"n": 253, "text": "extra"}], "Expected 2 translations, got 3"),
    ([{"n": 251, "text": "one"}, {"n": 999, "text": "two"}], "mismatch at position 2"),
    ([{"n": 252, "text": "two"}, {"n": 251, "text": "one"}], "mismatch at position 1"),
])
def test_bad_new_translation_stops_without_saving_or_followup(tmp_path, fake_client, bad_entries, reason):
    for i in [1, 2]:
        name = f"{i:06d}_{i:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": 251, "text": "one"}, {"n": 252, "text": "two"}])
        write_json(tmp_path / "subsets" / name, {})
    client = fake_client([{"entries": bad_entries}])
    with pytest.raises(ValueError, match=reason) as caught:
        translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="ja", client=client, model="test")
    assert "000001_000001.json" in " ".join(caught.value.__notes__)
    assert len(client.calls) == 1
    assert not list((tmp_path / "translations").glob("*.json"))


def test_missing_subset_fails_but_empty_subset_can_call(tmp_path, fake_client):
    name = "000001_000001.json"
    write_json(tmp_path / "entries" / name, [{"n": 1, "text": "one"}])
    client = fake_client([{"entries": [{"n": 1, "text": "一"}]}])
    with pytest.raises(FileNotFoundError) as caught:
        translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="zh-Hans", client=client, model="test")
    assert str(tmp_path / "subsets" / name) in " ".join(caught.value.__notes__)
    assert client.calls == []
    write_json(tmp_path / "subsets" / name, {})
    translate(tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations", source_lang="en", target_lang="zh-Hans", client=client, model="test")
    assert len(client.calls) == 1


def test_translation_skip_does_not_read_any_files_or_sleep(tmp_path, fake_client, monkeypatch):
    name = "000001_000001.json"
    write_json(tmp_path / "entries" / name, [])
    (tmp_path / "entries" / name).write_text("broken", encoding="utf-8")
    path = tmp_path / "translations" / name
    write_json(path, [])
    path.write_text("manual edit", encoding="utf-8")
    waits = []
    monkeypatch.setattr("srt_translate.llm.time.sleep", waits.append)
    client = fake_client()
    assert translate(
        tmp_path / "entries", tmp_path / "subsets", tmp_path / "translations",
        source_lang="en", target_lang="fr", client=client, model="test",
        background_path=tmp_path / "missing.txt", delay_between_requests=2,
    ) == [path]
    assert client.calls == waits == []
    assert path.read_text(encoding="utf-8") == "manual edit"


@pytest.mark.parametrize("phase", ["discover", "translate"])
def test_response_unpack_errors_preserve_previous_files(tmp_path, fake_client, phase):
    for i in [1, 2, 3]:
        name = f"{i:06d}_{i:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": i, "text": "source"}])
        write_json(tmp_path / "subsets" / name, {})
    valid = {"entities": []} if phase == "discover" else {"entries": [{"n": 1, "text": "translated"}]}
    client = fake_client([valid, {"missing": []}])
    output_dir = tmp_path / phase
    with pytest.raises(KeyError) as caught:
        if phase == "discover":
            discover_entities(tmp_path / "entries", output_dir, source_lang="en", target_lang="ja", client=client, model="test")
        else:
            translate(tmp_path / "entries", tmp_path / "subsets", output_dir, source_lang="en", target_lang="ja", client=client, model="test")
    assert f"{phase}:" in " ".join(caught.value.__notes__)
    assert "000002_000002.json" in " ".join(caught.value.__notes__)
    assert [path.name for path in output_dir.glob("*.json")] == ["000001_000001.json"]
    assert len(client.calls) == 2
