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
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository
from englishbot.presentation.add_words_text import (
    format_draft_edit_text,
    format_draft_preview,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Run add-words scenarios locally without Telegram.",
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
    user_id: Annotated[
        int,
        typer.Option("--user-id", help="Synthetic editor user id for scenario runs."),
    ] = 1,
    ollama_model: Annotated[
        str,
        typer.Option("--ollama-model", help="Ollama model name for extraction."),
    ] = os.getenv("OLLAMA_PULL_MODEL", "llama3.2:3b"),
    ollama_base_url: Annotated[
        str,
        typer.Option("--ollama-base-url", help="Base URL for the local Ollama server."),
    ] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    configure_logging(log_level.upper())
    pipeline = build_lesson_import_pipeline(
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
    )
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=pipeline,
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
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
        typer.echo(str(approved.output_path))


if __name__ == "__main__":
    app()
