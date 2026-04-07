from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import typer


def print_validation_errors(errors: list[object]) -> None:
    typer.echo(
        json.dumps(
            [asdict(error) for error in errors],
            ensure_ascii=False,
            indent=2,
        )
    )


def resolve_db_path(
    db_path: Path | None,
    *,
    config_service: Any,
) -> Path:
    return db_path or config_service.get_path("content_db_path") or Path("data/englishbot.db")


def run_extract_draft(
    *,
    input_path: Path,
    output_path: Path,
    parsed_output_path: Path | None,
    extractor: str,
    ollama_model: str | None,
    ollama_base_url: str | None,
    ollama_model_file_path: Path | None,
    ollama_timeout_sec: int | None,
    ollama_extraction_mode: str | None,
    include_image_prompts: bool,
    image_prompt_timeout_sec: int | None,
    ollama_temperature: float | None,
    ollama_top_p: float | None,
    ollama_num_predict: int | None,
    ollama_extract_line_prompt_path: Path | None,
    ollama_extract_text_prompt_path: Path | None,
    ollama_image_prompt_path: Path | None,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    runtime_config_service_fn: Callable[[], Any],
    build_pipeline_fn: Callable[..., Any],
) -> None:
    if extractor not in {"ollama", "stub"}:
        raise typer.BadParameter(
            "Extractor must be one of: ollama, stub.",
            param_hint="--extractor",
        )
    configure_logging_fn(log_level.upper())
    config_service = runtime_config_service_fn()
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
    pipeline = build_pipeline_fn(
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
        print_validation_errors(result.validation.errors)
        raise typer.Exit(code=1)
    logging.getLogger(__name__).info(
        "Draft extraction completed item_count=%s output_path=%s",
        len(result.draft.vocabulary_items),
        output_path,
    )


def run_finalize_draft(
    *,
    input_path: Path,
    output_path: Path,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    lesson_import_pipeline_cls: type[Any],
    legacy_smart_lesson_parsing_gateway_cls: type[Any],
    stub_lesson_extraction_client_cls: type[Any],
    template_lesson_fallback_parser_cls: type[Any],
    lesson_extraction_validator_cls: type[Any],
    draft_to_content_pack_canonicalizer_cls: type[Any],
    json_content_pack_writer_cls: type[Any],
    json_draft_writer_cls: type[Any],
    json_draft_reader_cls: type[Any],
) -> None:
    configure_logging_fn(log_level.upper())
    pipeline = lesson_import_pipeline_cls(
        smart_parser=legacy_smart_lesson_parsing_gateway_cls(stub_lesson_extraction_client_cls()),
        fallback_parser=template_lesson_fallback_parser_cls(),
        validator=lesson_extraction_validator_cls(),
        canonicalizer=draft_to_content_pack_canonicalizer_cls(),
        writer=json_content_pack_writer_cls(),
        draft_writer=json_draft_writer_cls(),
        draft_reader=json_draft_reader_cls(),
    )
    result = pipeline.finalize_draft_from_file(
        input_path=input_path,
        output_path=output_path,
    )
    if not result.validation.is_valid:
        print_validation_errors(result.validation.errors)
        raise typer.Exit(code=1)
    warning_count = (
        len(result.canonicalization.warnings) if result.canonicalization is not None else 0
    )
    logging.getLogger(__name__).info(
        "Draft finalization completed warnings=%s output_path=%s",
        warning_count,
        output_path,
    )


def run_reset_db(
    *,
    db_path: Path | None,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    runtime_config_service_fn: Callable[[], Any],
    sqlite_content_store_cls: type[Any],
) -> None:
    configure_logging_fn(log_level.upper())
    resolved_db_path = resolve_db_path(db_path, config_service=runtime_config_service_fn())
    store = sqlite_content_store_cls(db_path=resolved_db_path)
    store.initialize()
    store.import_json_directories([], replace=True)
    logging.getLogger(__name__).info("SQLite runtime database reset db_path=%s", resolved_db_path)
    typer.echo(str(resolved_db_path))


def run_import_json_to_db(
    *,
    input_dir: list[Path],
    db_path: Path | None,
    replace: bool,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    runtime_config_service_fn: Callable[[], Any],
    sqlite_content_store_cls: type[Any],
) -> None:
    if not input_dir:
        raise typer.BadParameter("Specify at least one --input-dir.", param_hint="--input-dir")
    configure_logging_fn(log_level.upper())
    resolved_db_path = resolve_db_path(db_path, config_service=runtime_config_service_fn())
    store = sqlite_content_store_cls(db_path=resolved_db_path)
    store.import_json_directories(input_dir, replace=replace)
    topics = store.list_topics()
    logging.getLogger(__name__).info(
        "Imported JSON content packs into SQLite db_path=%s topic_count=%s",
        resolved_db_path,
        len(topics),
    )
    typer.echo(f"db={resolved_db_path}")
    typer.echo(f"topics={len(topics)}")


def run_show_topics(
    *,
    db_path: Path | None,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    runtime_config_service_fn: Callable[[], Any],
    sqlite_content_store_cls: type[Any],
) -> None:
    configure_logging_fn(log_level.upper())
    resolved_db_path = resolve_db_path(db_path, config_service=runtime_config_service_fn())
    store = sqlite_content_store_cls(db_path=resolved_db_path)
    topics = store.list_topics()
    typer.echo(
        json.dumps(
            [{"id": topic.id, "title": topic.title} for topic in topics],
            ensure_ascii=False,
            indent=2,
        )
    )


def run_export_topic_from_db(
    *,
    topic_id: str,
    output_path: Path,
    db_path: Path | None,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    runtime_config_service_fn: Callable[[], Any],
    sqlite_content_store_cls: type[Any],
    json_content_pack_writer_cls: type[Any],
    canonical_content_pack_cls: type[Any],
) -> None:
    configure_logging_fn(log_level.upper())
    resolved_db_path = resolve_db_path(db_path, config_service=runtime_config_service_fn())
    store = sqlite_content_store_cls(db_path=resolved_db_path)
    content_pack = store.get_content_pack(topic_id)
    json_content_pack_writer_cls().write(
        content_pack=canonical_content_pack_cls(content_pack),
        output_path=output_path,
    )
    logging.getLogger(__name__).info(
        "Exported topic from SQLite db_path=%s topic_id=%s output_path=%s",
        resolved_db_path,
        topic_id,
        output_path,
    )
    typer.echo(str(output_path))


def run_bulk_import_topics(
    *,
    input_path: Path,
    output_dir: Path | None,
    db_path: Path | None,
    no_db_import: bool,
    log_level: str,
    repo_root: Path,
    create_runtime_config_service_fn: Callable[..., Any],
    configure_cli_logging_fn: Callable[..., None],
    parse_bulk_topic_text_fn: Callable[[str], Any],
    write_bulk_topic_content_packs_fn: Callable[..., Any],
) -> None:
    config_service = create_runtime_config_service_fn(repo_root=repo_root)
    configure_cli_logging_fn(log_level=log_level, config_service=config_service)
    resolved_db_path = None if no_db_import else (db_path or config_service.get_path("content_db_path"))
    if no_db_import and output_dir is None:
        raise typer.BadParameter(
            "Use --output-dir when --no-db-import is set.",
            param_hint="--output-dir",
        )
    text = input_path.read_text(encoding="utf-8")
    drafts = parse_bulk_topic_text_fn(text)
    results = write_bulk_topic_content_packs_fn(
        drafts=drafts,
        output_dir=output_dir,
        db_path=resolved_db_path,
    )
    typer.echo(
        json.dumps(
            [
                {
                    "topic_title": result.topic_title,
                    "topic_id": result.topic_id,
                    **(
                        {"output_path": str(result.output_path)}
                        if result.output_path is not None
                        else {}
                    ),
                    "item_count": result.item_count,
                }
                for result in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


def run_simulate_add_words_flow(
    *,
    input_path: Path,
    edited_input_path: Path | None,
    output_path: Path | None,
    db_path: Path | None,
    user_id: int,
    ollama_model: str | None,
    ollama_model_file_path: Path | None,
    ollama_base_url: str | None,
    ollama_timeout_sec: int | None,
    ollama_extraction_mode: str | None,
    ollama_temperature: float | None,
    ollama_top_p: float | None,
    ollama_num_predict: int | None,
    ollama_extract_line_prompt_path: Path | None,
    ollama_extract_text_prompt_path: Path | None,
    ollama_image_prompt_path: Path | None,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    runtime_config_service_fn: Callable[[], Any],
    build_lesson_import_pipeline_fn: Callable[..., Any],
    sqlite_content_store_cls: type[Any],
    sqlite_add_words_flow_repository_cls: type[Any],
    add_words_flow_harness_cls: type[Any],
    lesson_extraction_validator_cls: type[Any],
    json_content_pack_writer_cls: type[Any],
    start_add_words_flow_use_case_cls: type[Any],
    apply_add_words_edit_use_case_cls: type[Any],
    approve_add_words_draft_use_case_cls: type[Any],
    format_draft_preview_fn: Callable[[Any], str],
    format_draft_edit_text_fn: Callable[[Any], str],
) -> None:
    configure_logging_fn(log_level.upper())
    config_service = runtime_config_service_fn()
    resolved_db_path = resolve_db_path(db_path, config_service=config_service)
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
    content_store = sqlite_content_store_cls(db_path=resolved_db_path)
    content_store.initialize()
    pipeline = build_lesson_import_pipeline_fn(
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
    repository = sqlite_add_words_flow_repository_cls(content_store)
    harness = add_words_flow_harness_cls(
        pipeline=pipeline,
        validator=lesson_extraction_validator_cls(),
        writer=json_content_pack_writer_cls(),
        content_store=content_store,
    )
    start_flow = start_add_words_flow_use_case_cls(harness=harness, flow_repository=repository)
    apply_edit = apply_add_words_edit_use_case_cls(harness=harness, flow_repository=repository)
    approve = approve_add_words_draft_use_case_cls(harness=harness, flow_repository=repository)

    raw_text = input_path.read_text(encoding="utf-8")
    logging.getLogger(__name__).info("Scenario step=extract input=%s", input_path)
    flow = start_flow.execute(user_id=user_id, raw_text=raw_text)
    typer.echo(format_draft_preview_fn(flow.draft_result))
    typer.echo("\n--- Editable Draft ---\n")
    typer.echo(format_draft_edit_text_fn(flow.draft_result.draft))

    if edited_input_path is not None:
        logging.getLogger(__name__).info("Scenario step=edit input=%s", edited_input_path)
        edited_text = edited_input_path.read_text(encoding="utf-8")
        flow = apply_edit.execute(user_id=user_id, flow_id=flow.flow_id, edited_text=edited_text)
        typer.echo("\n--- Updated Preview ---\n")
        typer.echo(format_draft_preview_fn(flow.draft_result))

    if output_path is not None:
        logging.getLogger(__name__).info("Scenario step=approve output=%s", output_path)
        approved = approve.execute(user_id=user_id, flow_id=flow.flow_id, output_path=output_path)
        typer.echo("\n--- Approved ---\n")
        typer.echo(f"Topic: {approved.published_topic_id}")
        if approved.output_path is not None:
            typer.echo(str(approved.output_path))
