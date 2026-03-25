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
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Import free-form lesson text into a JSON content pack.",
)


@app.command()
def main(
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
        typer.Option("--output", help="Path to the output JSON content pack.", dir_okay=False),
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
            help="Generate image prompts in a separate per-item enrichment step.",
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
    extraction_client = StubLessonExtractionClient()
    if extractor == "ollama":
        extraction_client = OllamaLessonExtractionClient(
            model=ollama_model,
            base_url=ollama_base_url,
        )
    pipeline = LessonImportPipeline(
        extraction_client=extraction_client,
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=(
            OllamaImagePromptEnricher(
                model=ollama_model,
                base_url=ollama_base_url,
            )
            if extractor == "ollama"
            else None
        ),
    )
    result = pipeline.run(
        raw_text=raw_text,
        output_path=output_path,
        enrich_image_prompts=include_image_prompts,
    )
    if not result.validation.is_valid:
        typer.echo(
            json.dumps(
                [asdict(error) for error in result.validation.errors],
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)
    warning_count = (
        len(result.canonicalization.warnings) if result.canonicalization is not None else 0
    )
    logging.getLogger(__name__).info("Import completed with warnings=%s", warning_count)


if __name__ == "__main__":
    app()
