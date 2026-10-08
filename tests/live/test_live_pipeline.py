from datetime import timedelta

import pytest
import srt

from srt_translate.cli import main
from srt_translate.common import read_json, read_srt


@pytest.mark.parametrize("case_name,source_lang,target_lang,texts,background", [
    (
        "en_to_zh_hans", "en", "zh-Hans",
        ["[Elias] Alexia, we must leave before dawn.", "[Alexia] I will meet you at the old bridge.", '<i>♪ We will find our way home. ♪</i>'],
        "Elias and Alexia are travelers in a fictional adventure. Use natural dialogue.",
    ),
    (
        "ja_to_en", "ja", "en",
        ["[ケン] ミカ、明日の朝、駅で会おう。", "[ミカ] わかった。切符はもう買ったよ。", "[ケン] ありがとう。楽しみだね。"],
        "ケンとミカは友人で、一緒に旅行へ出かける。自然な会話にする。",
    ),
])
def test_live_pipeline(live_run_dir, case_name, source_lang, target_lang, texts, background):
    case_dir = live_run_dir / case_name
    case_dir.mkdir()
    source = case_dir / "input.srt"
    subtitles = [
        srt.Subtitle(index=n, start=timedelta(seconds=i * 3), end=timedelta(seconds=i * 3 + 2), content=text)
        for i, (n, text) in enumerate(zip([10, 3, 28], texts))
    ]
    source.write_bytes(srt.compose(subtitles, reindex=False, eol="\r\n").encode("utf-8-sig"))
    background_path = case_dir / "background.txt"
    background_path.write_text(background, encoding="utf-8")
    original = source.read_bytes()
    output_base = case_dir / "outputs"
    task_dir = output_base / f"{source.stem}__{source_lang}_to_{target_lang}"
    assert main([
        str(source), "--source-lang", source_lang, "--target-lang", target_lang,
        "--background", str(background_path), "--output-dir", str(output_base),
    ]) == 0
    output = task_dir / "backfill" / source.name
    result = read_srt(output)
    assert len(result) == len(subtitles)
    assert [(s.index, s.start, s.end) for s in result] == [(s.index, s.start, s.end) for s in subtitles]
    assert all(s.content for s in result)
    assert any(s.content != original_text for s, original_text in zip(result, texts))
    assert [e["n"] for e in read_json(task_dir / "translations" / "000001_000003.json")] == [10, 3, 28]
    assert source.read_bytes() == original
    raw = output.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\r\n" not in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
