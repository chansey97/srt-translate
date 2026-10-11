from pathlib import Path

from .common import error_context, log_progress, read_json, write_json


def _normalize_for_matching(text: str) -> str:
    return " ".join(text.casefold().split())


def generate_glossary_subsets(
    entries_dir: Path, glossary_path: Path, glossary_subsets_dir: Path,
) -> list[Path]:
    paths = []
    glossary = None
    normalized_sources = []
    entries_paths = sorted(entries_dir.glob("*.json"))
    total = len(entries_paths)
    for current, entries_path in enumerate(entries_paths, start=1):
        output_path = glossary_subsets_dir / entries_path.name
        paths.append(output_path)
        if output_path.exists():
            log_progress("subsets", current, total, output_path, "skipped (exists)")
            continue
        with error_context(f"subsets: {entries_path}, {glossary_path} -> {output_path}"):
            if glossary is None:
                glossary = read_json(glossary_path)
                normalized_sources = [
                    (source, _normalize_for_matching(source)) for source in sorted(glossary)
                ]
            text = _normalize_for_matching(
                "\n".join(entry["text"] for entry in read_json(entries_path))
            )
            subset = {
                source: glossary[source]
                for source, normalized_source in normalized_sources
                if normalized_source and normalized_source in text
            }
            write_json(output_path, subset)
            log_progress("subsets", current, total, output_path, "done")
    return paths
