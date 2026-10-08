from pathlib import Path

from .common import error_context, log_progress, read_json, write_json


def build_glossary(entities_dir: Path, glossary_path: Path) -> Path:
    if glossary_path.exists():
        log_progress("glossary", 1, 1, glossary_path, "skipped (exists)")
        return glossary_path
    with error_context(f"glossary: {entities_dir} -> {glossary_path}"):
        best = {}
        entities_paths = sorted(entities_dir.glob("*.json"))
        for current, path in enumerate(entities_paths, start=1):
            with error_context(f"Entity shard: {path}"):
                for entity in read_json(path):
                    source = entity["source"]
                    score = (
                        entity["entity_confidence"]
                        + entity["type_confidence"]
                        + entity["translation_confidence"]
                    ) / 3
                    if source not in best or score > best[source][0]:
                        best[source] = (score, entity["translation"])
                log_progress("glossary", current, len(entities_paths), path, "read")
        glossary = {source: best[source][1] for source in sorted(best)}
        write_json(glossary_path, glossary)
    return glossary_path
