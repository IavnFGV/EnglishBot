from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.config import resolve_ollama_model
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient, StubLessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader, JsonDraftWriter
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.models import CanonicalContentPack
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteContentStore

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Extract editable lesson drafts from text and finalize reviewed drafts.",
)

_DEFAULT_EXTRACT_PROMPT_PATH = Path(
    os.getenv("OLLAMA_EXTRACT_LINE_PROMPT_PATH", "prompts/ollama_extract_line_prompt.txt")
)
_DEFAULT_EXTRACT_TEXT_PROMPT_PATH = Path(
    os.getenv("OLLAMA_EXTRACT_TEXT_PROMPT_PATH", "prompts/ollama_extract_text_prompt.txt")
)
_DEFAULT_IMAGE_PROMPT_PATH = Path(
    os.getenv("OLLAMA_IMAGE_PROMPT_PATH", "prompts/ollama_image_prompt_prompt.txt")
)


def _build_pipeline(
    *,
    extractor: str,
    ollama_model: str,
    ollama_model_file_path: Path | None,
    ollama_base_url: str,
    ollama_timeout_sec: int,
    image_prompt_timeout_sec: int,
    ollama_extraction_mode: str,
    ollama_temperature: float | None,
    ollama_top_p: float | None,
    ollama_num_predict: int | None,
    ollama_extract_line_prompt_path: Path,
    ollama_extract_text_prompt_path: Path,
    ollama_image_prompt_path: Path,
) -> LessonImportPipeline:
    extraction_client = StubLessonExtractionClient()
    if extractor == "ollama":
        extraction_client = OllamaLessonExtractionClient(
            model=ollama_model,
            model_file_path=ollama_model_file_path,
            base_url=ollama_base_url,
            timeout=ollama_timeout_sec,
            extraction_mode=ollama_extraction_mode,
            temperature=ollama_temperature,
            top_p=ollama_top_p,
            num_predict=ollama_num_predict,
            extract_line_prompt_path=ollama_extract_line_prompt_path,
            extract_text_prompt_path=ollama_extract_text_prompt_path,
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
                model_file_path=ollama_model_file_path,
                base_url=ollama_base_url,
                timeout=image_prompt_timeout_sec,
                temperature=ollama_temperature,
                top_p=ollama_top_p,
                num_predict=ollama_num_predict,
                prompt_path=ollama_image_prompt_path,
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


def _resolve_db_path(db_path: Path | None) -> Path:
    return db_path or Path(os.getenv("CONTENT_DB_PATH", "data/englishbot.db"))


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
    parsed_output_path: Annotated[
        Path | None,
        typer.Option(
            "--parsed-output",
            help="Optional path for the parsed draft saved before image-prompt generation.",
            dir_okay=False,
        ),
    ] = None,
    extractor: Annotated[
        str,
        typer.Option("--extractor", help="Extraction backend to use."),
    ] = "ollama",
    ollama_model: Annotated[
        str,
        typer.Option("--ollama-model", help="Ollama model name for extraction."),
    ] = resolve_ollama_model(),
    ollama_base_url: Annotated[
        str,
        typer.Option("--ollama-base-url", help="Base URL for the local Ollama server."),
    ] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    ollama_model_file_path: Annotated[
        Path | None,
        typer.Option("--ollama-model-file-path", help="Optional path to a file containing the Ollama model name."),
    ] = Path(os.getenv("OLLAMA_MODEL_FILE_PATH")) if os.getenv("OLLAMA_MODEL_FILE_PATH") else None,
    ollama_timeout_sec: Annotated[
        int,
        typer.Option("--ollama-timeout-sec", help="Timeout in seconds for extraction requests."),
    ] = int(os.getenv("OLLAMA_TIMEOUT_SEC", "120")),
    ollama_extraction_mode: Annotated[
        str,
        typer.Option("--ollama-extraction-mode", help="Extraction mode: line_by_line or full_text."),
    ] = os.getenv("OLLAMA_EXTRACTION_MODE", "line_by_line"),
    include_image_prompts: Annotated[
        bool,
        typer.Option(
            "--include-image-prompts",
            help="Generate image prompts for each extracted vocabulary pair.",
        ),
    ] = False,
    image_prompt_timeout_sec: Annotated[
        int,
        typer.Option(
            "--image-prompt-timeout-sec",
            help="Timeout in seconds for one image-prompt generation request.",
        ),
    ] = int(os.getenv("OLLAMA_IMAGE_PROMPT_TIMEOUT_SEC", "30")),
    ollama_temperature: Annotated[
        float | None,
        typer.Option("--ollama-temperature", help="Optional Ollama temperature."),
    ] = float(os.getenv("OLLAMA_TEMPERATURE")) if os.getenv("OLLAMA_TEMPERATURE") else None,
    ollama_top_p: Annotated[
        float | None,
        typer.Option("--ollama-top-p", help="Optional Ollama top_p."),
    ] = float(os.getenv("OLLAMA_TOP_P")) if os.getenv("OLLAMA_TOP_P") else None,
    ollama_num_predict: Annotated[
        int | None,
        typer.Option("--ollama-num-predict", help="Optional Ollama num_predict."),
    ] = int(os.getenv("OLLAMA_NUM_PREDICT")) if os.getenv("OLLAMA_NUM_PREDICT") else None,
    ollama_extract_line_prompt_path: Annotated[
        Path,
        typer.Option(
            "--ollama-extract-line-prompt-path",
            help="Path to the extraction prompt file.",
            dir_okay=False,
        ),
    ] = _DEFAULT_EXTRACT_PROMPT_PATH,
    ollama_extract_text_prompt_path: Annotated[
        Path,
        typer.Option(
            "--ollama-extract-text-prompt-path",
            help="Path to the full-text extraction prompt file.",
            dir_okay=False,
        ),
    ] = _DEFAULT_EXTRACT_TEXT_PROMPT_PATH,
    ollama_image_prompt_path: Annotated[
        Path,
        typer.Option(
            "--ollama-image-prompt-path",
            help="Path to the image prompt file.",
            dir_okay=False,
        ),
    ] = _DEFAULT_IMAGE_PROMPT_PATH,
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
        ollama_model_file_path=ollama_model_file_path,
        ollama_base_url=ollama_base_url,
        ollama_timeout_sec=ollama_timeout_sec,
        image_prompt_timeout_sec=image_prompt_timeout_sec,
        ollama_extraction_mode=ollama_extraction_mode,
        ollama_temperature=ollama_temperature,
        ollama_top_p=ollama_top_p,
        ollama_num_predict=ollama_num_predict,
        ollama_extract_line_prompt_path=ollama_extract_line_prompt_path,
        ollama_extract_text_prompt_path=ollama_extract_text_prompt_path,
        ollama_image_prompt_path=ollama_image_prompt_path,
    )
    result = pipeline.extract_draft(
        raw_text=raw_text,
        output_path=output_path,
        intermediate_output_path=parsed_output_path,
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


@app.command("reset-db")
def reset_db(
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", dir_okay=False, help="Path to the SQLite runtime database."),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    resolved_db_path = _resolve_db_path(db_path)
    store = SQLiteContentStore(db_path=resolved_db_path)
    store.initialize()
    store.import_json_directories([], replace=True)
    logging.getLogger(__name__).info("SQLite runtime database reset db_path=%s", resolved_db_path)
    typer.echo(str(resolved_db_path))


@app.command("import-json-to-db")
def import_json_to_db(
    input_dir: Annotated[
        list[Path],
        typer.Option(
            "--input-dir",
            exists=True,
            file_okay=False,
            dir_okay=True,
            help="Directory with JSON content packs. Repeat the option for multiple directories.",
        ),
    ],
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", dir_okay=False, help="Path to the SQLite runtime database."),
    ] = None,
    replace: Annotated[
        bool,
        typer.Option("--replace", help="Clear existing runtime data before import."),
    ] = True,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    if not input_dir:
        raise typer.BadParameter("Specify at least one --input-dir.", param_hint="--input-dir")
    configure_logging(log_level.upper())
    resolved_db_path = _resolve_db_path(db_path)
    store = SQLiteContentStore(db_path=resolved_db_path)
    store.import_json_directories(input_dir, replace=replace)
    topics = store.list_topics()
    logging.getLogger(__name__).info(
        "Imported JSON content packs into SQLite db_path=%s topic_count=%s",
        resolved_db_path,
        len(topics),
    )
    typer.echo(f"db={resolved_db_path}")
    typer.echo(f"topics={len(topics)}")


@app.command("show-topics")
def show_topics(
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", dir_okay=False, help="Path to the SQLite runtime database."),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    resolved_db_path = _resolve_db_path(db_path)
    store = SQLiteContentStore(db_path=resolved_db_path)
    topics = store.list_topics()
    typer.echo(
        json.dumps(
            [{"id": topic.id, "title": topic.title} for topic in topics],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("export-topic-from-db")
def export_topic_from_db(
    topic_id: Annotated[
        str,
        typer.Option("--topic-id", help="Topic id to export from the SQLite runtime database."),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", dir_okay=False, help="Path to the exported content pack JSON."),
    ],
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", dir_okay=False, help="Path to the SQLite runtime database."),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    resolved_db_path = _resolve_db_path(db_path)
    store = SQLiteContentStore(db_path=resolved_db_path)
    content_pack = store.get_content_pack(topic_id)
    JsonContentPackWriter().write(
        content_pack=CanonicalContentPack(content_pack),
        output_path=output_path,
    )
    logging.getLogger(__name__).info(
        "Exported topic from SQLite db_path=%s topic_id=%s output_path=%s",
        resolved_db_path,
        topic_id,
        output_path,
    )
    typer.echo(str(output_path))


if __name__ == "__main__":
    app()
