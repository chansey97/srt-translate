from pathlib import Path

from .common import error_context, log_progress, read_srt, write_json


def extract_entries(
    input_srt: Path, entries_dir: Path, *, chunk_size: int = 20,
    input_encoding: str = "utf-8-sig",
) -> list[Path]:
    with error_context(f"extract: {input_srt} -> {entries_dir}"):
        subtitles = read_srt(input_srt, input_encoding)
        total = len(subtitles)
        width = max(6, len(str(total)))
        starts = range(0, total, chunk_size)
        paths = []
        for current, start in enumerate(starts, start=1):
            end = min(start + chunk_size, total)
            path = entries_dir / f"{start + 1:0{width}d}_{end:0{width}d}.json"
            paths.append(path)
            if path.exists():
                log_progress("extract", current, len(starts), path, "skipped (exists)")
                continue
            entries = [
                {"n": subtitle.index, "text": subtitle.content}
                for subtitle in subtitles[start:end]
            ]
            write_json(path, entries)
            log_progress("extract", current, len(starts), path, "done")
        return paths
