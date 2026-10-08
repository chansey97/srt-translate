from pathlib import Path

import pytest

from srt_translate.common import read_background, read_json, read_srt, write_json
from srt_translate.phase_backfill import backfill
from srt_translate.phase_extract_entries import extract_entries


@pytest.mark.parametrize("total", [1, 20, 21, 103])
def test_extract_chunk_positions_and_numbers(tmp_path, make_srt, total):
    numbers = [1000 - i * 3 for i in range(total)]
    source = make_srt([(n, f"line {i}") for i, n in enumerate(numbers)])
    paths = extract_entries(source, tmp_path / "entries")
    expected_names = [
        f"{start + 1:06d}_{min(start + 20, total):06d}.json"
        for start in range(0, total, 20)
    ]
    assert [path.name for path in paths] == expected_names
    assert paths == sorted(paths)
    assert [entry["n"] for path in paths for entry in read_json(path)] == numbers
    assert len(read_json(paths[-1])) == (total % 20 or 20)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030"])
def test_input_encodings_and_original_preserved(tmp_path, make_srt, encoding):
    source = make_srt([(10, "你好\n第二行"), (35, "再见")], encoding=encoding)
    original = source.read_bytes()
    kwargs = {"input_encoding": encoding} if encoding == "gb18030" else {}
    paths = extract_entries(source, tmp_path / "entries", **kwargs)
    assert read_json(paths[0]) == [{"n": 10, "text": "你好\n第二行"}, {"n": 35, "text": "再见"}]
    assert source.read_bytes() == original
    raw = paths[0].read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert "你好" in raw.decode("utf-8")
    assert b'\n  {\n    "n": 10,' in raw
    assert b"\\n" in raw


def test_extract_skips_existing_content_without_reading_it(tmp_path, make_srt):
    source = make_srt([(10, "first"), (20, "second"), (35, "third")])
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    edited = entries_dir / "000001_000002.json"
    edited.write_bytes(b"intentionally invalid edited JSON")
    paths = extract_entries(source, entries_dir, chunk_size=2)
    assert edited.read_bytes() == b"intentionally invalid edited JSON"
    assert read_json(paths[1]) == [{"n": 35, "text": "third"}]


@pytest.mark.parametrize("filename,total,chunks,last,bom,multiline", [
    ("Blood.of.Zeus.S01E01.srt", 284, 15, "000281_000284.json", True, 59),
    ("1997 スペシャルおまけビデオ.srt", 63, 4, "000061_000063.json", False, None),
])
def test_repository_samples(tmp_path, filename, total, chunks, last, bom, multiline):
    source = Path(__file__).resolve().parents[2] / "examples" / filename
    original = source.read_bytes()
    assert original.startswith(b"\xef\xbb\xbf") is bom
    paths = extract_entries(source, tmp_path / "entries")
    entries = [entry for path in paths for entry in read_json(path)]
    assert len(entries) == total
    assert len(paths) == chunks
    assert paths[-1].name == last
    if multiline is not None:
        assert sum("\n" in entry["text"] for entry in entries) == multiline
    assert source.read_bytes() == original


def test_background_bom_and_missing_file(tmp_path):
    assert read_background(None) == ""
    path = tmp_path / "background.txt"
    path.write_bytes("故事背景\r\n下一行".encode("utf-8-sig"))
    assert read_background(path) == "故事背景\n下一行"
    with pytest.raises(FileNotFoundError):
        read_background(tmp_path / "missing.txt")


def test_bad_json_error_includes_path(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        read_json(path)
    assert str(path) in " ".join(caught.value.__notes__)


@pytest.mark.parametrize("encoding", ["utf-8-sig", "gb18030"])
def test_backfill_preserves_order_timing_and_output_bytes(tmp_path, make_srt, encoding):
    source = make_srt([(35, "原文一"), (10, "原文二"), (20, "原文三")], encoding=encoding)
    original = source.read_bytes()
    translated = [
        {"n": 35, "text": '<font color="#FF0000">译文</font>\r\n第二行'},
        {"n": 10, "text": r"{\an8}♪ 音乐 ♪ https://example.com"},
        {"n": 20, "text": "第三行\n\n清理空白"},
    ]
    translations_dir = tmp_path / "translations"
    write_json(translations_dir / "000003_000003.json", translated[2:])
    write_json(translations_dir / "000001_000002.json", translated[:2])
    output = tmp_path / "backfill" / source.name
    assert backfill(source, translations_dir, output, input_encoding=encoding) == output
    result = read_srt(output)
    expected = read_srt(source, encoding)
    assert [(s.index, s.start, s.end) for s in result] == [(s.index, s.start, s.end) for s in expected]
    assert result[0].content == translated[0]["text"].replace("\r\n", "\n")
    assert result[1].content == translated[1]["text"]
    assert result[2].content == "第三行\n清理空白"
    raw = output.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\r\n" not in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert source.read_bytes() == original


def test_backfill_uses_positions_without_rechecking_numbers_or_extra_entries(tmp_path, make_srt):
    source = make_srt([(10, "one"), (20, "two")])
    write_json(tmp_path / "translations" / "000001_000002.json", [
        {"n": 999, "text": "一"}, {"text": "二"}, {"n": 7, "text": "extra"},
    ])
    output = backfill(source, tmp_path / "translations", tmp_path / "backfill" / source.name)
    assert [(s.index, s.content) for s in read_srt(output)] == [(10, "一"), (20, "二")]


def test_backfill_missing_position_fails_without_output(tmp_path, make_srt):
    source = make_srt([(10, "one"), (20, "two")])
    write_json(tmp_path / "translations" / "000001_000001.json", [{"n": 10, "text": "一"}])
    output = tmp_path / "backfill" / source.name
    with pytest.raises(IndexError) as caught:
        backfill(source, tmp_path / "translations", output)
    assert "backfill:" in " ".join(caught.value.__notes__)
    assert not output.exists()


def test_existing_backfill_skips_all_inputs(tmp_path):
    output = tmp_path / "edited.srt"
    output.write_bytes(b"edited SRT")
    assert backfill(tmp_path / "missing.srt", tmp_path / "missing", output) == output
    assert output.read_bytes() == b"edited SRT"

