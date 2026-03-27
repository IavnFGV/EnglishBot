from __future__ import annotations

import logging
import os
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
from englishbot.config import resolve_ollama_model
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

_DEFAULT_EXTRACT_PROMPT_PATH = Path(
    os.getenv("OLLAMA_EXTRACT_LINE_PROMPT_PATH", "prompts/ollama_extract_line_prompt.txt")
)
_DEFAULT_EXTRACT_TEXT_PROMPT_PATH = Path(
    os.getenv("OLLAMA_EXTRACT_TEXT_PROMPT_PATH", "prompts/ollama_extract_text_prompt.txt")
)
_DEFAULT_IMAGE_PROMPT_PATH = Path(
    os.getenv("OLLAMA_IMAGE_PROMPT_PATH", "prompts/ollama_image_prompt_prompt.txt")
)


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
        Path,
        typer.Option(
            "--db-path",
            dir_okay=False,
            help="Path to the SQLite runtime database used for flow checkpoints and published content.",
        ),
    ] = Path(os.getenv("CONTENT_DB_PATH", "data/englishbot.db")),
    user_id: Annotated[
        int,
        typer.Option("--user-id", help="Synthetic editor user id for scenario runs."),
    ] = 1,
    ollama_model: Annotated[
        str,
        typer.Option("--ollama-model", help="Ollama model name for extraction."),
    ] = resolve_ollama_model(),
    ollama_model_file_path: Annotated[
        Path | None,
        typer.Option("--ollama-model-file-path", help="Optional path to a file containing the Ollama model name."),
    ] = Path(os.getenv("OLLAMA_MODEL_FILE_PATH")) if os.getenv("OLLAMA_MODEL_FILE_PATH") else None,
    ollama_base_url: Annotated[
        str,
        typer.Option("--ollama-base-url", help="Base URL for the local Ollama server."),
    ] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    ollama_timeout_sec: Annotated[
        int,
        typer.Option("--ollama-timeout-sec", help="Timeout in seconds for extraction requests."),
    ] = int(os.getenv("OLLAMA_TIMEOUT_SEC", "120")),
    ollama_extraction_mode: Annotated[
        str,
        typer.Option("--ollama-extraction-mode", help="Extraction mode: line_by_line or full_text."),
    ] = os.getenv("OLLAMA_EXTRACTION_MODE", "line_by_line"),
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
            dir_okay=False,
            help="Path to the extraction prompt file.",
        ),
    ] = _DEFAULT_EXTRACT_PROMPT_PATH,
    ollama_extract_text_prompt_path: Annotated[
        Path,
        typer.Option(
            "--ollama-extract-text-prompt-path",
            dir_okay=False,
            help="Path to the full-text extraction prompt file.",
        ),
    ] = _DEFAULT_EXTRACT_TEXT_PROMPT_PATH,
    ollama_image_prompt_path: Annotated[
        Path,
        typer.Option(
            "--ollama-image-prompt-path",
            dir_okay=False,
            help="Path to the image prompt file.",
        ),
    ] = _DEFAULT_IMAGE_PROMPT_PATH,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    content_store = SQLiteContentStore(db_path=db_path)
    content_store.initialize()
    pipeline = build_lesson_import_pipeline(
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
