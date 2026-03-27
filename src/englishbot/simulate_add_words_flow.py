from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.bootstrap import build_lesson_import_pipeline
from englishbot.config import RuntimeConfigService, create_runtime_config_service
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

def _runtime_config_service() -> RuntimeConfigService:
    return create_runtime_config_service()


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
    configure_logging(log_level.upper())
    config_service = _runtime_config_service()
    resolved_db_path = db_path or config_service.get_path("content_db_path") or Path("data/englishbot.db")
    resolved_ollama_model = ollama_model or config_service.get_str("ollama_model")
    resolved_ollama_model_file_path = (
        ollama_model_file_path or config_service.get_path("ollama_model_file_path")
    )
    resolved_ollama_base_url = ollama_base_url or config_service.get_str("ollama_base_url")
    resolved_ollama_timeout_sec = ollama_timeout_sec or config_service.get_int("ollama_timeout_sec")
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
    content_store = SQLiteContentStore(db_path=resolved_db_path)
    content_store.initialize()
    pipeline = build_lesson_import_pipeline(
        config_service=config_service,
        ollama_model=resolved_ollama_model,
        ollama_model_file_path=resolved_ollama_model_file_path,
        ollama_base_url=resolved_ollama_base_url,
        ollama_timeout_sec=resolved_ollama_timeout_sec,
        ollama_extraction_mode=resolved_ollama_extraction_mode,
        ollama_temperature=resolved_ollama_temperature,
        ollama_top_p=resolved_ollama_top_p,
        ollama_num_predict=resolved_ollama_num_predict,
        ollama_extract_line_prompt_path=resolved_extract_line_prompt_path,
        ollama_extract_text_prompt_path=resolved_extract_text_prompt_path,
        ollama_image_prompt_path=resolved_image_prompt_path,
    )
    repository = SQLiteAddWordsFlowRepository(content_store)
    harness = AddWordsFlowHarness(
        pipeline=pipeline,
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
        content_store=content_store,
    )
    start_flow = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    apply_edit = ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository)
    approve = ApproveAddWordsDraftUseCase(harness=harness, flow_repository=repository)

    raw_text = input_path.read_text(encoding="utf-8")
    logging.getLogger(__name__).info("Scenario step=extract input=%s", input_path)
    flow = start_flow.execute(user_id=user_id, raw_text=raw_text)
    typer.echo(format_draft_preview(flow.draft_result))
    typer.echo("\n--- Editable Draft ---\n")
    typer.echo(format_draft_edit_text(flow.draft_result.draft))

    if edited_input_path is not None:
        logging.getLogger(__name__).info("Scenario step=edit input=%s", edited_input_path)
        edited_text = edited_input_path.read_text(encoding="utf-8")
        flow = apply_edit.execute(user_id=user_id, flow_id=flow.flow_id, edited_text=edited_text)
        typer.echo("\n--- Updated Preview ---\n")
        typer.echo(format_draft_preview(flow.draft_result))

    if output_path is not None:
        logging.getLogger(__name__).info("Scenario step=approve output=%s", output_path)
        approved = approve.execute(user_id=user_id, flow_id=flow.flow_id, output_path=output_path)
        typer.echo("\n--- Approved ---\n")
        typer.echo(f"Topic: {approved.published_topic_id}")
        if approved.output_path is not None:
            typer.echo(str(approved.output_path))


if __name__ == "__main__":
    app()
