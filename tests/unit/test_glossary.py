import pytest

from srt_translate.common import read_json, write_json
from srt_translate.phase_build_glossary import build_glossary
from srt_translate.phase_generate_glossary_subsets import generate_glossary_subsets


def test_glossary_mean_scores_ties_and_unmodified_keys(tmp_path, make_entity):
    entities_dir = tmp_path / "entities"
    write_json(entities_dir / "000003_000004.json", [
        make_entity("Heron", "highest mean", scores=(0.8, 0.8, 0.8)),
        make_entity("Elias", "later tie", scores=(0.75, 0.75, 0.75)),
    ])
    write_json(entities_dir / "000001_000002.json", [
        make_entity("Heron", "highest translation only", scores=(0.1, 0.1, 1.0)),
        make_entity("Elias", "first tie", scores=(0.75, 0.75, 0.75)),
        make_entity("Elias", "same shard tie", scores=(0.75, 0.75, 0.75)),
        make_entity("elias", "lowercase"),
        make_entity(" Elias ", "spaces"),
        make_entity("Lord Elias", "full name"),
        make_entity("low", "still included", scores=(0.0, 0.0, 0.0)),
        make_entity("close", "lower", scores=(0.8, 0.8, 0.8)),
        make_entity("close", "higher", scores=(0.8, 0.8, 0.800000001)),
    ])
    path = build_glossary(entities_dir, tmp_path / "glossary.json")
    glossary = read_json(path)
    assert glossary == {
        "Heron": "highest mean", "Elias": "first tie", "elias": "lowercase",
        " Elias ": "spaces", "Lord Elias": "full name", "low": "still included", "close": "higher",
    }
    assert list(glossary) == sorted(glossary)


@pytest.mark.parametrize("empty_shard", [False, True])
def test_empty_entities_produce_empty_glossary(tmp_path, empty_shard):
    if empty_shard:
        write_json(tmp_path / "entities" / "000001_000020.json", [])
    path = build_glossary(tmp_path / "entities", tmp_path / "glossary.json")
    assert read_json(path) == {}


def test_glossary_does_not_infer_missing_entities(tmp_path, make_entity):
    for i in range(15):
        name = f"{i + 1:06d}_{i + 1:06d}.json"
        write_json(tmp_path / "entries" / name, [{"n": i + 1, "text": f"Name{i}"}])
        if i < 14:
            write_json(tmp_path / "entities" / name, [make_entity(f"Name{i}", f"名字{i}")])
    path = build_glossary(tmp_path / "entities", tmp_path / "glossary.json")
    assert len(read_json(path)) == 14
    assert "Name14" not in read_json(path)


def test_existing_glossary_is_not_read_or_overwritten(tmp_path):
    output = tmp_path / "glossary.json"
    output.write_bytes(b"edited content")
    write_json(tmp_path / "entities" / "000001_000001.json", [{}])
    assert build_glossary(tmp_path / "entities", output) == output
    assert output.read_bytes() == b"edited content"


def test_subsets_match_text_and_preserve_sorted_original_keys_and_values(tmp_path):
    write_json(tmp_path / "entries" / "000003_000003.json", [{"n": 3, "text": "Quiet."}])
    write_json(tmp_path / "entries" / "000001_000002.json", [
        {"n": 1, "text": "A B A B"}, {"n": 2, "text": "a"},
    ])
    glossary = {key: f"edited {key}" for key in ["A", "B", "a", " A ", "A B", "unused"]}
    write_json(tmp_path / "glossary.json", glossary)
    paths = generate_glossary_subsets(tmp_path / "entries", tmp_path / "glossary.json", tmp_path / "subsets")
    assert [p.name for p in paths] == ["000001_000002.json", "000003_000003.json"]
    assert read_json(paths[0]) == {key: glossary[key] for key in [" A ", "A", "A B", "B", "a"]}
    assert list(read_json(paths[0])) == [" A ", "A", "A B", "B", "a"]
    assert read_json(paths[1]) == {}


@pytest.mark.parametrize("source,text", [
    ("Ann", "Anna"),
    ("Orc", "force"),
    ("Straße", "STRASSE"),
    ("STRASSE", "Straße"),
    ("New York", "New\nYork"),
    (" New\t York ", "NEW\u00a0YORK"),
    ("New\u2003York", "New \r\n\tYork"),
    ("東京", "東京へ行こう。"),
])
def test_subsets_select_normalized_substring_candidates(tmp_path, source, text):
    write_json(tmp_path / "entries" / "000001_000001.json", [{"n": 1, "text": text}])
    write_json(tmp_path / "glossary.json", {source: "指定译名", "unmatched": "无关"})
    paths = generate_glossary_subsets(tmp_path / "entries", tmp_path / "glossary.json", tmp_path / "subsets")
    assert read_json(paths[0]) == {source: "指定译名"}


def test_subsets_include_overlapping_terms_and_phrases_across_entries(tmp_path):
    write_json(tmp_path / "entries" / "000001_000002.json", [
        {"n": 1, "text": "Moonshadow City is near New"},
        {"n": 2, "text": "York."},
    ])
    glossary = {"New York": "纽约", "Moonshadow City": "月影城", "Moonshadow": "月影"}
    write_json(tmp_path / "glossary.json", glossary)
    paths = generate_glossary_subsets(tmp_path / "entries", tmp_path / "glossary.json", tmp_path / "subsets")
    assert read_json(paths[0]) == glossary
    assert list(read_json(paths[0])) == sorted(glossary)


@pytest.mark.parametrize("entries,glossary", [
    ([{"n": 1, "text": "Elias"}], {}),
    ([], {"Elias": "伊莱亚斯"}),
    ([{"n": 1, "text": "Elias"}], {"": "empty", " \t\n": "whitespace"}),
])
def test_empty_glossary_shards_and_terms_produce_empty_subsets(tmp_path, entries, glossary):
    write_json(tmp_path / "entries" / "000001_000001.json", entries)
    write_json(tmp_path / "glossary.json", glossary)
    paths = generate_glossary_subsets(tmp_path / "entries", tmp_path / "glossary.json", tmp_path / "subsets")
    assert read_json(paths[0]) == {}


def test_existing_subsets_skip_unreadable_inputs(tmp_path):
    name = "000001_000001.json"
    write_json(tmp_path / "entries" / name, [{}])
    subset = tmp_path / "subsets" / name
    write_json(subset, {"manual": "override"})
    assert generate_glossary_subsets(tmp_path / "entries", tmp_path / "missing.json", tmp_path / "subsets") == [subset]
    assert read_json(subset) == {"manual": "override"}

