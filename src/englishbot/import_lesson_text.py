from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient, StubLessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader, JsonDraftWriter
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Extract editable lesson drafts from text and finalize reviewed drafts.",
)


def _build_pipeline(
    *,
    extractor: str,
    ollama_model: str,
    ollama_base_url: str,
) -> LessonImportPipeline:
    extraction_client = StubLessonExtractionClient()
    if extractor == "ollama":
        extraction_client = OllamaLessonExtractionClient(
            model=ollama_model,
            base_url=ollama_base_url,
        )
    return LessonImportPipeline(
        extraction_client=extraction_client,
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        draft_writer=JsonDraftWriter(),
        draft_reader=JsonDraftReader(),
        image_prompt_enricher=(
            OllamaImagePromptEnricher(
                model=ollama_model,
                base_url=ollama_base_url,
            )
            if extractor == "ollama"
            else None
        ),
    )


def _print_validation_errors(errors: list[object]) -> None:
    typer.echo(
        json.dumps(
            [asdict(error) for error in errors],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("extract-draft")
def extract_draft(
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            help="Path to the raw lesson text file.",
            exists=True,
            dir_okay=False,
        ),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", help="Path to the editable draft JSON file.", dir_okay=False),
    ],
    extractor: Annotated[
        str,
        typer.Option("--extractor", help="Extraction backend to use."),
    ] = "ollama",
    ollama_model: Annotated[
        str,
        typer.Option("--ollama-model", help="Ollama model name for extraction."),
    ] = os.getenv("OLLAMA_PULL_MODEL", "llama3.2:3b"),
    ollama_base_url: Annotated[
        str,
        typer.Option("--ollama-base-url", help="Base URL for the local Ollama server."),
    ] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    include_image_prompts: Annotated[
        bool,
        typer.Option(
            "--include-image-prompts",
            help="Generate image prompts for each extracted vocabulary pair.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    if extractor not in {"ollama", "stub"}:
        raise typer.BadParameter(
            "Extractor must be one of: ollama, stub.",
            param_hint="--extractor",
        )

    configure_logging(log_level.upper())
    raw_text = input_path.read_text(encoding="utf-8")
    pipeline = _build_pipeline(
        extractor=extractor,
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
    )
    result = pipeline.extract_draft(
        raw_text=raw_text,
        output_path=output_path,
        enrich_image_prompts=include_image_prompts,
    )
    if not result.validation.is_valid:
        _print_validation_errors(result.validation.errors)
        raise typer.Exit(code=1)
    logging.getLogger(__name__).info(
        "Draft extraction completed item_count=%s output_path=%s",
        len(result.draft.vocabulary_items),
        output_path,
    )


@app.command("finalize-draft")
def finalize_draft(
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            help="Path to the reviewed draft JSON file.",
            exists=True,
            dir_okay=False,
        ),
    ],
    output_path: Annotated[
        Path,
        typer.Option(
            "--output",
            help="Path to the final canonical content pack JSON.",
            dir_okay=False,
        ),
    ],
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    pipeline = LessonImportPipeline(
        extraction_client=StubLessonExtractionClient(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        draft_writer=JsonDraftWriter(),
        draft_reader=JsonDraftReader(),
    )
    result = pipeline.finalize_draft_from_file(
        input_path=input_path,
        output_path=output_path,
    )
    if not result.validation.is_valid:
        _print_validation_errors(result.validation.errors)
        raise typer.Exit(code=1)
    warning_count = (
        len(result.canonicalization.warnings) if result.canonicalization is not None else 0
    )
    logging.getLogger(__name__).info(
        "Draft finalization completed warnings=%s output_path=%s",
        warning_count,
        output_path,
    )


if __name__ == "__main__":
    app()
