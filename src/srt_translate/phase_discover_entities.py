from pathlib import Path

from .common import error_context, log_progress, read_background, read_json, write_json
from .llm import request_json
from .prompts import DISCOVER_ENTITIES_PROMPT
from .schemas import EntitiesResponse


def discover_entities(
    entries_dir: Path, entities_dir: Path, *, source_lang: str, target_lang: str,
    client, model: str, background_path: Path | None = None,
    delay_between_requests: float = 0.0,
) -> list[Path]:
    paths = []
    background = None
    entries_paths = sorted(entries_dir.glob("*.json"))
    total = len(entries_paths)
    for current, entries_path in enumerate(entries_paths, start=1):
        output_path = entities_dir / entries_path.name
        paths.append(output_path)
        if output_path.exists():
            log_progress("discover", current, total, output_path, "skipped (exists)")
            continue
        with error_context(f"discover: {entries_path} -> {output_path}"):
            log_progress("discover", current, total, output_path, "processing")
            if background is None:
                background = read_background(background_path)
            payload = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "background": background,
                "entries": read_json(entries_path),
            }
            response = request_json(
                client=client, model=model, system_prompt=DISCOVER_ENTITIES_PROMPT,
                payload=payload, response_model=EntitiesResponse,
                delay_between_requests=delay_between_requests,
            )
            write_json(output_path, response["entities"])
            log_progress("discover", current, total, output_path, "done")
    return paths
