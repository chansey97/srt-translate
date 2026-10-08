import json
from contextlib import contextmanager
from pathlib import Path

import srt


def log_progress(stage: str, current: int, total: int, path: Path, status: str) -> None:
    print(f"[{stage}] {current}/{total} {status}: {path.name}", flush=True)


@contextmanager
def error_context(message: str):
    """Keep the original exception, adding the relevant stage or file."""
    try:
        yield
    except Exception as exc:
        exc.add_note(message)
        raise


def read_json(path: Path):
    with error_context(f"Read JSON: {path}"):
        with path.open(encoding="utf-8") as file:
            return json.load(file)


def write_json(path: Path, data) -> None:
    with error_context(f"Write JSON: {path}"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")


def read_background(path: Path | None) -> str:
    if path is None:
        return ""
    with error_context(f"Read background: {path}"):
        return path.read_text(encoding="utf-8-sig")


def read_srt(path: Path, input_encoding: str = "utf-8-sig") -> list[srt.Subtitle]:
    with error_context(f"Read SRT: {path}"):
        return list(srt.parse(path.read_text(encoding=input_encoding), ignore_errors=False))


def write_srt(path: Path, subtitles: list[srt.Subtitle]) -> None:
    with error_context(f"Write SRT: {path}"):
        output_text = srt.compose(subtitles, reindex=False, strict=True, eol="\r\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            file.write(output_text)
