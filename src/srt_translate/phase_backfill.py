from pathlib import Path

from .common import error_context, log_progress, read_json, read_srt, write_srt


def backfill(
    input_srt: Path, translations_dir: Path, output_srt: Path, *,
    input_encoding: str = "utf-8-sig",
) -> Path:
    if output_srt.exists():
        log_progress("backfill", 1, 1, output_srt, "skipped (exists)")
        return output_srt
    with error_context(f"backfill: {input_srt}, {translations_dir} -> {output_srt}"):
        subtitles = read_srt(input_srt, input_encoding)
        translated_entries = []
        translation_paths = sorted(translations_dir.glob("*.json"))
        for current, path in enumerate(translation_paths, start=1):
            translated_entries.extend(read_json(path))
            log_progress("backfill", current, len(translation_paths), path, "read")
        for position, subtitle in enumerate(subtitles):
            subtitle.content = translated_entries[position]["text"].replace("\r\n", "\n")
        write_srt(output_srt, subtitles)
    return output_srt
