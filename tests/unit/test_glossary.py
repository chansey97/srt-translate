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


def test_subsets_deduplicate_sort_and_take_values_from_global_glossary(tmp_path, make_entity):
    entities = [make_entity(source, "old") for source in ["B", "A", "B", "a", " A ", "A B"]]
    write_json(tmp_path / "entities" / "000001_000002.json", entities)
    write_json(tmp_path / "entities" / "000003_000003.json", [])
    glossary = {key: f"edited {key}" for key in ["A", "B", "a", " A ", "A B", "unused"]}
    write_json(tmp_path / "glossary.json", glossary)
    paths = generate_glossary_subsets(tmp_path / "entities", tmp_path / "glossary.json", tmp_path / "subsets")
    assert [p.name for p in paths] == ["000001_000002.json", "000003_000003.json"]
    assert read_json(paths[0]) == {key: glossary[key] for key in [" A ", "A", "A B", "B", "a"]}
    assert list(read_json(paths[0])) == [" A ", "A", "A B", "B", "a"]
    assert read_json(paths[1]) == {}


def test_missing_glossary_key_is_normal_key_error(tmp_path, make_entity):
    write_json(tmp_path / "entities" / "000001_000001.json", [make_entity("A", "old")])
    write_json(tmp_path / "glossary.json", {})
    with pytest.raises(KeyError, match="A"):
        generate_glossary_subsets(tmp_path / "entities", tmp_path / "glossary.json", tmp_path / "subsets")
    assert not (tmp_path / "subsets" / "000001_000001.json").exists()


def test_existing_subsets_skip_unreadable_inputs(tmp_path):
    name = "000001_000001.json"
    write_json(tmp_path / "entities" / name, [{}])
    subset = tmp_path / "subsets" / name
    write_json(subset, {"manual": "override"})
    assert generate_glossary_subsets(tmp_path / "entities", tmp_path / "missing.json", tmp_path / "subsets") == [subset]
    assert read_json(subset) == {"manual": "override"}

