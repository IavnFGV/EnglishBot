from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.cli import create_cli_runtime_config_service
from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.importing.runtime import build_lesson_import_pipeline
from englishbot.config import RuntimeConfigService
from englishbot.importing.cli import run_simulate_add_words_flow
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteAddWordsFlowRepository, SQLiteContentStore
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    format_draft_preview,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Run add-words scenarios locally without Telegram.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_config_service() -> RuntimeConfigService:
    return create_cli_runtime_config_service(repo_root=_REPO_ROOT)


@app.command("run")
def run_scenario(
    input_path: Annotated[
        Path,
        typer.Option("--input", exists=True, dir_okay=False, help="Raw lesson text file."),
    ],
    edited_input_path: Annotated[
        Path | None,
        typer.Option(
            "--edited-input",
            exists=True,
            dir_okay=False,
            help="Optional edited draft text file in the same format shown by the harness.",
        ),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Optional final content pack output path for approve step.",
        ),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option(
            "--db-path",
            dir_okay=False,
            help="Path to the SQLite runtime database used for flow checkpoints and published content.",
        ),
    ] = None,
    user_id: Annotated[
        int,
        typer.Option("--user-id", help="Synthetic editor user id for scenario runs."),
    ] = 1,
    ollama_model: Annotated[
        str | None,
        typer.Option("--ollama-model", help="Ollama model name for extraction."),
    ] = None,
    ollama_model_file_path: Annotated[
        Path | None,
        typer.Option("--ollama-model-file-path", help="Optional path to a file containing the Ollama model name."),
    ] = None,
    ollama_base_url: Annotated[
        str | None,
        typer.Option("--ollama-base-url", help="Base URL for the local Ollama server."),
    ] = None,
    ollama_timeout_sec: Annotated[
        int | None,
        typer.Option("--ollama-timeout-sec", help="Timeout in seconds for extraction requests."),
    ] = None,
    ollama_extraction_mode: Annotated[
        str | None,
        typer.Option("--ollama-extraction-mode", help="Extraction mode: line_by_line or full_text."),
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
            dir_okay=False,
            help="Path to the extraction prompt file.",
        ),
    ] = None,
    ollama_extract_text_prompt_path: Annotated[
        Path | None,
        typer.Option(
            "--ollama-extract-text-prompt-path",
            dir_okay=False,
            help="Path to the full-text extraction prompt file.",
        ),
    ] = None,
    ollama_image_prompt_path: Annotated[
        Path | None,
        typer.Option(
            "--ollama-image-prompt-path",
            dir_okay=False,
            help="Path to the image prompt file.",
        ),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    run_simulate_add_words_flow(
        input_path=input_path,
        edited_input_path=edited_input_path,
        output_path=output_path,
        db_path=db_path,
        user_id=user_id,
        ollama_model=ollama_model,
        ollama_model_file_path=ollama_model_file_path,
        ollama_base_url=ollama_base_url,
        ollama_timeout_sec=ollama_timeout_sec,
        ollama_extraction_mode=ollama_extraction_mode,
        ollama_temperature=ollama_temperature,
        ollama_top_p=ollama_top_p,
        ollama_num_predict=ollama_num_predict,
        ollama_extract_line_prompt_path=ollama_extract_line_prompt_path,
        ollama_extract_text_prompt_path=ollama_extract_text_prompt_path,
        ollama_image_prompt_path=ollama_image_prompt_path,
        log_level=log_level,
        configure_logging_fn=configure_logging,
        runtime_config_service_fn=_runtime_config_service,
        build_lesson_import_pipeline_fn=build_lesson_import_pipeline,
        sqlite_content_store_cls=SQLiteContentStore,
        sqlite_add_words_flow_repository_cls=SQLiteAddWordsFlowRepository,
        add_words_flow_harness_cls=AddWordsFlowHarness,
        lesson_extraction_validator_cls=LessonExtractionValidator,
        json_content_pack_writer_cls=JsonContentPackWriter,
        start_add_words_flow_use_case_cls=StartAddWordsFlowUseCase,
        apply_add_words_edit_use_case_cls=ApplyAddWordsEditUseCase,
        approve_add_words_draft_use_case_cls=ApproveAddWordsDraftUseCase,
        format_draft_preview_fn=format_draft_preview,
        format_draft_edit_text_fn=format_draft_edit_text,
    )


if __name__ == "__main__":
    app()
