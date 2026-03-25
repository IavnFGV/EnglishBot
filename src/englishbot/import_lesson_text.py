from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from englishbot.__main__ import configure_logging
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import StubLessonExtractionClient
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import free-form lesson text into a JSON content pack."
    )
    parser.add_argument("--input", required=True, help="Path to the raw lesson text file.")
    parser.add_argument("--output", required=True, help="Path to the output JSON content pack.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level, for example INFO or DEBUG.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level.upper())

    raw_text = Path(args.input).read_text(encoding="utf-8")
    pipeline = LessonImportPipeline(
        extraction_client=StubLessonExtractionClient(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )
    result = pipeline.run(raw_text=raw_text, output_path=Path(args.output))
    if not result.validation.is_valid:
        print(
            json.dumps(
                [asdict(error) for error in result.validation.errors],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    warning_count = (
        len(result.canonicalization.warnings) if result.canonicalization is not None else 0
    )
    logging.getLogger(__name__).info("Import completed with warnings=%s", warning_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
