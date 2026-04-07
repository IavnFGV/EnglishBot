from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.cli import create_cli_runtime_config_service
from englishbot.config import RuntimeConfigService
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient, StubLessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader, JsonDraftWriter
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.fallback_parser import TemplateLessonFallbackParser
from englishbot.importing.models import CanonicalContentPack
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.smart_parsing import LegacySmartLessonParsingGateway, OllamaSmartLessonParsingGateway
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteContentStore

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Extract editable lesson drafts from text and finalize reviewed drafts.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_config_service() -> RuntimeConfigService:
    return create_cli_runtime_config_service(repo_root=_REPO_ROOT)


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
    smart_parser = (
        OllamaSmartLessonParsingGateway(extraction_client)
        if extractor == "ollama"
        else LegacySmartLessonParsingGateway(extraction_client)
    )
    return LessonImportPipeline(
        smart_parser=smart_parser,
        fallback_parser=TemplateLessonFallbackParser(),
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


def _resolve_db_path(
    db_path: Path | None,
    *,
    config_service: RuntimeConfigService | None = None,
) -> Path:
    service = config_service or _runtime_config_service()
    return db_path or service.get_path("content_db_path") or Path("data/englishbot.db")


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
        str | None,
        typer.Option("--ollama-model", help="Ollama model name for extraction."),
    ] = None,
    ollama_base_url: Annotated[
        str | None,
        typer.Option("--ollama-base-url", help="Base URL for the local Ollama server."),
    ] = None,
    ollama_model_file_path: Annotated[
        Path | None,
        typer.Option("--ollama-model-file-path", help="Optional path to a file containing the Ollama model name."),
    ] = None,
    ollama_timeout_sec: Annotated[
        int | None,
        typer.Option("--ollama-timeout-sec", help="Timeout in seconds for extraction requests."),
    ] = None,
    ollama_extraction_mode: Annotated[
        str | None,
        typer.Option("--ollama-extraction-mode", help="Extraction mode: line_by_line or full_text."),
    ] = None,
    include_image_prompts: Annotated[
        bool,
        typer.Option(
            "--include-image-prompts",
            help="Generate image prompts for each extracted vocabulary pair.",
        ),
    ] = False,
    image_prompt_timeout_sec: Annotated[
        int | None,
        typer.Option(
            "--image-prompt-timeout-sec",
            help="Timeout in seconds for one image-prompt generation request.",
        ),
    ] = None,
    ollama_temperature: Annotated[
        float | None,
        typer.Option("--ollama-temperature", help="Optional Ollama temperature."),
    ] = None,
    ollama_top_p: Annotated[
        float | None,
        typer.Option("--ollama-top-p", help="Optional Ollama top_p."),
    ] = None,
    ollama_num_predict: Annotated[
        int | None,
        typer.Option("--ollama-num-predict", help="Optional Ollama num_predict."),
    ] = None,
    ollama_extract_line_prompt_path: Annotated[
        Path | None,
        typer.Option(
            "--ollama-extract-line-prompt-path",
            help="Path to the extraction prompt file.",
            dir_okay=False,
        ),
    ] = None,
    ollama_extract_text_prompt_path: Annotated[
        Path | None,
        typer.Option(
            "--ollama-extract-text-prompt-path",
            help="Path to the full-text extraction prompt file.",
            dir_okay=False,
        ),
    ] = None,
    ollama_image_prompt_path: Annotated[
        Path | None,
        typer.Option(
            "--ollama-image-prompt-path",
            help="Path to the image prompt file.",
            dir_okay=False,
        ),
    ] = None,
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
    config_service = _runtime_config_service()
    resolved_ollama_model = ollama_model or config_service.get_str("ollama_model")
    resolved_ollama_base_url = ollama_base_url or config_service.get_str("ollama_base_url")
    resolved_ollama_model_file_path = (
        ollama_model_file_path or config_service.get_path("ollama_model_file_path")
    )
    resolved_ollama_timeout_sec = ollama_timeout_sec or config_service.get_int("ollama_timeout_sec")
    resolved_image_prompt_timeout_sec = image_prompt_timeout_sec or config_service.get_int(
        "ollama_image_prompt_timeout_sec"
    )
    resolved_ollama_extraction_mode = (
        ollama_extraction_mode or config_service.get_str("ollama_extraction_mode")
    )
    resolved_ollama_temperature = (
        ollama_temperature
        if ollama_temperature is not None
        else config_service.get_float("ollama_temperature")
    )
    resolved_ollama_top_p = (
        ollama_top_p if ollama_top_p is not None else config_service.get_float("ollama_top_p")
    )
    resolved_ollama_num_predict = (
        ollama_num_predict
        if ollama_num_predict is not None
        else config_service.get("ollama_num_predict")
    )
    resolved_extract_line_prompt_path = (
        ollama_extract_line_prompt_path
        or config_service.get_path("ollama_extract_line_prompt_path")
        or Path("prompts/ollama_extract_line_prompt.txt")
    )
    resolved_extract_text_prompt_path = (
        ollama_extract_text_prompt_path
        or config_service.get_path("ollama_extract_text_prompt_path")
        or Path("prompts/ollama_extract_text_prompt.txt")
    )
    resolved_image_prompt_path = (
        ollama_image_prompt_path
        or config_service.get_path("ollama_image_prompt_path")
        or Path("prompts/ollama_image_prompt_prompt.txt")
    )
    raw_text = input_path.read_text(encoding="utf-8")
    pipeline = _build_pipeline(
        extractor=extractor,
        ollama_model=resolved_ollama_model,
        ollama_model_file_path=resolved_ollama_model_file_path,
        ollama_base_url=resolved_ollama_base_url,
        ollama_timeout_sec=resolved_ollama_timeout_sec,
        image_prompt_timeout_sec=resolved_image_prompt_timeout_sec,
        ollama_extraction_mode=resolved_ollama_extraction_mode,
        ollama_temperature=resolved_ollama_temperature,
        ollama_top_p=resolved_ollama_top_p,
        ollama_num_predict=resolved_ollama_num_predict,
        ollama_extract_line_prompt_path=resolved_extract_line_prompt_path,
        ollama_extract_text_prompt_path=resolved_extract_text_prompt_path,
        ollama_image_prompt_path=resolved_image_prompt_path,
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
        smart_parser=LegacySmartLessonParsingGateway(StubLessonExtractionClient()),
        fallback_parser=TemplateLessonFallbackParser(),
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
