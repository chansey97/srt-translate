from pathlib import Path

from .common import error_context, log_progress, read_background, read_json, write_json
from .llm import request_json
from .prompts import translation_prompt
from .schemas import TranslationResponse


def _read_history(
    previous_paths: list[Path], translations_dir: Path, history_size: int,
) -> list[dict]:
    history = []
    for entries_path in reversed(previous_paths):
        remaining = history_size - len(history)
        if remaining <= 0:
            break
        translation_path = translations_dir / entries_path.name
        with error_context(f"History: {entries_path}, {translation_path}"):
            entries = read_json(entries_path)[-remaining:]
            translations = {entry["n"]: entry for entry in read_json(translation_path)}
            history = [
                {
                    "n": entry["n"],
                    "source": entry["text"],
                    "translation": translations[entry["n"]]["text"],
                }
                for entry in entries
            ] + history
    return history


def translate(
    entries_dir: Path, glossary_subsets_dir: Path, translations_dir: Path, *,
    source_lang: str, target_lang: str, client, model: str,
    background_path: Path | None = None, history_size: int = 5,
    no_translate_glossary: bool = False, delay_between_requests: float = 0.0,
) -> list[Path]:
    entries_paths = sorted(entries_dir.glob("*.json"))
    total = len(entries_paths)
    paths = []
    background = None
    for index, entries_path in enumerate(entries_paths):
        output_path = translations_dir / entries_path.name
        paths.append(output_path)
        if output_path.exists():
            log_progress("translate", index + 1, total, output_path, "skipped (exists)")
            continue
        subset_path = glossary_subsets_dir / entries_path.name
        with error_context(f"translate: {entries_path}, {subset_path} -> {output_path}"):
            log_progress("translate", index + 1, total, output_path, "processing")
            entries = read_json(entries_path)
            glossary = read_json(subset_path)
            if background is None:
                background = read_background(background_path)
            payload = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "background": background,
                "history": _read_history(entries_paths[:index], translations_dir, history_size),
                "entries": entries,
            }
            if no_translate_glossary:
                payload["do_not_translate_terms"] = list(glossary)
            else:
                payload["glossary"] = glossary
            response = request_json(
                client=client, model=model,
                system_prompt=translation_prompt(no_translate_glossary),
                payload=payload, response_model=TranslationResponse,
                delay_between_requests=delay_between_requests,
            )
            translated_entries = response["entries"]
            if len(translated_entries) != len(entries):
                raise ValueError(
                    f"Expected {len(entries)} translations, got {len(translated_entries)}"
                )
            for position, (entry, translated) in enumerate(
                zip(entries, translated_entries), start=1
            ):
                if translated["n"] != entry["n"]:
                    raise ValueError(f"Subtitle number mismatch at position {position}")
            write_json(output_path, translated_entries)
            log_progress("translate", index + 1, total, output_path, "done")
    return paths
