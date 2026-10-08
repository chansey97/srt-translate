from pathlib import Path

from .common import error_context, log_progress, read_json, write_json


def generate_glossary_subsets(
    entities_dir: Path, glossary_path: Path, glossary_subsets_dir: Path,
) -> list[Path]:
    paths = []
    glossary = None
    entities_paths = sorted(entities_dir.glob("*.json"))
    total = len(entities_paths)
    for current, entities_path in enumerate(entities_paths, start=1):
        output_path = glossary_subsets_dir / entities_path.name
        paths.append(output_path)
        if output_path.exists():
            log_progress("subsets", current, total, output_path, "skipped (exists)")
            continue
        with error_context(f"subsets: {entities_path}, {glossary_path} -> {output_path}"):
            if glossary is None:
                glossary = read_json(glossary_path)
            sources = {entity["source"] for entity in read_json(entities_path)}
            subset = {source: glossary[source] for source in sorted(sources)}
            write_json(output_path, subset)
            log_progress("subsets", current, total, output_path, "done")
    return paths
