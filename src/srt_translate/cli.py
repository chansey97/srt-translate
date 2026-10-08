import argparse
import math
import re
import sys
from contextlib import ExitStack
from pathlib import Path

from openai import OpenAI

from . import config
from .phase_backfill import backfill
from .phase_build_glossary import build_glossary
from .phase_discover_entities import discover_entities
from .phase_extract_entries import extract_entries
from .phase_generate_glossary_subsets import generate_glossary_subsets
from .phase_translate import translate

STAGES = ("extract", "discover", "glossary", "subsets", "translate", "backfill")


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def nonnegative_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative finite number")
    return seconds


def language_tag(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]+", value):
        raise argparse.ArgumentTypeError(
            "use a nonempty language tag with ASCII letters, digits or hyphens"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="srt-translate",
        description="Translate SRT subtitles through six stages with editable intermediate files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_srt", type=Path, metavar="INPUT_SRT", help="original SRT file"
    )
    parser.add_argument(
        "--source-lang", type=language_tag, required=True, metavar="LANG",
        help="source BCP 47 language tag",
    )
    parser.add_argument(
        "--target-lang", type=language_tag, default="zh-Hans", metavar="LANG",
        help="target BCP 47 language tag",
    )
    parser.add_argument(
        "--background", type=Path, metavar="PATH", help="background text in UTF-8"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("."), metavar="PATH",
        help="output parent directory; creates <stem>__<source>_to_<target> inside it",
    )
    parser.add_argument(
        "--config-file", type=Path, metavar="PATH",
        help="TOML configuration file overriding built-in and user settings by field",
    )
    parser.add_argument(
        "--input-encoding", default="utf-8-sig", metavar="NAME",
        help="original SRT encoding",
    )
    parser.add_argument(
        "--chunk-size", type=positive_int, default=20, metavar="N",
        help="entries per extracted shard",
    )
    parser.add_argument(
        "--history-size", type=nonnegative_int, default=5, metavar="N",
        help="preceding bilingual entries; 0 disables history",
    )
    parser.add_argument(
        "--no-translate-glossary", action="store_true",
        help="keep all subset terms in their original spelling",
    )
    parser.add_argument(
        "--delay-between-requests", type=nonnegative_seconds, default=0.0,
        metavar="SECONDS", help="wait before every model call, including the first",
    )
    parser.add_argument(
        "--from-stage", choices=STAGES, default="extract",
        help="first stage to run (inclusive)",
    )
    parser.add_argument(
        "--to-stage", choices=STAGES, default="backfill",
        help="last stage to run (inclusive)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    start, end = STAGES.index(args.from_stage), STAGES.index(args.to_stage)
    if start > end:
        parser.error("--from-stage must not come after --to-stage")

    try:
        settings = config.load_config(args.config_file)
    except ValueError as exc:
        parser.error(f"configuration error: {exc}")

    input_srt = args.input_srt.resolve()
    task_dir = (
        args.output_dir / f"{input_srt.stem}__{args.source_lang}_to_{args.target_lang}"
    ).resolve()
    entries_dir = task_dir / "entries"
    entities_dir = task_dir / "entities"
    glossary_path = task_dir / "glossary.json"
    subsets_dir = task_dir / "glossary_subsets"
    translations_dir = task_dir / "translations"
    background_path = args.background.resolve() if args.background is not None else None

    client = None
    with ExitStack() as stack:
        for stage in STAGES[start : end + 1]:
            print(f"[{stage}] {task_dir}", flush=True)
            try:
                if stage in ("discover", "translate") and client is None:
                    client = stack.enter_context(
                        OpenAI(
                            base_url=settings.base_url, api_key=settings.api_key,
                            max_retries=settings.max_retries,
                        )
                    )
                if stage == "extract":
                    result = extract_entries(
                        input_srt, entries_dir, chunk_size=args.chunk_size,
                        input_encoding=args.input_encoding,
                    )
                elif stage == "discover":
                    result = discover_entities(
                        entries_dir, entities_dir, source_lang=args.source_lang,
                        target_lang=args.target_lang, client=client, model=settings.model,
                        background_path=background_path,
                        delay_between_requests=args.delay_between_requests,
                    )
                elif stage == "glossary":
                    result = build_glossary(entities_dir, glossary_path)
                elif stage == "subsets":
                    result = generate_glossary_subsets(entities_dir, glossary_path, subsets_dir)
                elif stage == "translate":
                    result = translate(
                        entries_dir, subsets_dir, translations_dir,
                        source_lang=args.source_lang, target_lang=args.target_lang,
                        client=client, model=settings.model, background_path=background_path,
                        history_size=args.history_size,
                        no_translate_glossary=args.no_translate_glossary,
                        delay_between_requests=args.delay_between_requests,
                    )
                else:
                    result = backfill(
                        input_srt, translations_dir, task_dir / "backfill" / input_srt.name,
                        input_encoding=args.input_encoding,
                    )
            except Exception as exc:
                print(f"Error in {stage}: {exc}", file=sys.stderr)
                for note in getattr(exc, "__notes__", ()):
                    print(note, file=sys.stderr)
                return 1
            summary = f"{len(result)} file(s) ready" if isinstance(result, list) else str(result)
            print(f"[{stage}] {summary}", flush=True)
    return 0
