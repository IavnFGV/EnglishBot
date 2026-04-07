from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import typer


def _build_image_client(
    *,
    backend: str,
    comfyui_client_cls: type[Any],
    placeholder_client_factory: Callable[[], Any],
    comfyui_base_url: str,
    comfyui_checkpoint: str,
    comfyui_vae: str | None,
    width: int | None = None,
    height: int | None = None,
) -> Any:
    if backend == "placeholder":
        return placeholder_client_factory()
    if backend == "comfyui":
        kwargs: dict[str, Any] = {
            "base_url": comfyui_base_url,
            "checkpoint_name": comfyui_checkpoint,
            "vae_name": comfyui_vae,
        }
        if width is not None:
            kwargs["width"] = width
        if height is not None:
            kwargs["height"] = height
        return comfyui_client_cls(**kwargs)
    raise typer.BadParameter(
        "Backend must be one of: placeholder, comfyui.",
        param_hint="--backend",
    )


def run_generate_image(
    *,
    prompt: str,
    output_path: Path,
    english_word: str,
    backend: str,
    comfyui_base_url: str,
    comfyui_checkpoint: str,
    comfyui_vae: str | None,
    width: int,
    height: int,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    comfyui_client_cls: type[Any],
    placeholder_client_factory: Callable[[], Any],
) -> None:
    configure_logging_fn(log_level.upper())
    image_client = _build_image_client(
        backend=backend,
        comfyui_client_cls=comfyui_client_cls,
        placeholder_client_factory=placeholder_client_factory,
        comfyui_base_url=comfyui_base_url,
        comfyui_checkpoint=comfyui_checkpoint,
        comfyui_vae=comfyui_vae,
        width=width,
        height=height,
    )
    image_client.generate(
        prompt=prompt,
        english_word=english_word,
        output_path=output_path,
    )
    logging.getLogger(__name__).info(
        "Single image generation completed output_path=%s english_word=%s",
        output_path,
        english_word,
    )


def run_generate_lesson_images(
    *,
    input_path: Path,
    assets_dir: Path,
    backend: str,
    comfyui_base_url: str,
    comfyui_checkpoint: str,
    comfyui_vae: str | None,
    force: bool,
    log_level: str,
    configure_logging_fn: Callable[[str], None],
    comfyui_client_cls: type[Any],
    placeholder_client_factory: Callable[[], Any],
    content_pack_image_enricher_cls: type[Any],
) -> None:
    configure_logging_fn(log_level.upper())
    image_client = _build_image_client(
        backend=backend,
        comfyui_client_cls=comfyui_client_cls,
        placeholder_client_factory=placeholder_client_factory,
        comfyui_base_url=comfyui_base_url,
        comfyui_checkpoint=comfyui_checkpoint,
        comfyui_vae=comfyui_vae,
    )
    enricher = content_pack_image_enricher_cls(image_client)
    enriched_pack = enricher.enrich_file(
        input_path=input_path,
        assets_dir=assets_dir,
        force=force,
    )
    logging.getLogger(__name__).info(
        "Image generation completed item_count=%s input_path=%s",
        len(enriched_pack.get("vocabulary_items", [])),
        input_path,
    )


def run_fill_word_images(
    *,
    topic_id: str | None,
    assets_dir: Path,
    limit: int | None,
    force: bool,
    dry_run: bool,
    delay_sec: float,
    log_level: str,
    repo_root: Path,
    create_runtime_config_service_fn: Callable[..., Any],
    configure_cli_logging_fn: Callable[..., None],
    create_content_store_fn: Callable[..., Any],
    fill_word_images_use_case_cls: type[Any],
    image_search_client_cls: type[Any],
    remote_image_downloader_cls: type[Any],
) -> None:
    config_service = create_runtime_config_service_fn(repo_root=repo_root)
    configure_cli_logging_fn(log_level=log_level, config_service=config_service)
    store = create_content_store_fn(config_service=config_service)
    use_case = fill_word_images_use_case_cls(
        store=store,
        image_search_client=image_search_client_cls(config_service=config_service),
        remote_image_downloader=remote_image_downloader_cls(),
        assets_dir=assets_dir,
    )
    summary = use_case.execute(
        topic_id=topic_id,
        limit=limit,
        force=force,
        dry_run=dry_run,
        delay_sec=delay_sec,
    )
    logging.getLogger(__name__).info(
        "Word image backfill completed scanned=%s updated=%s skipped=%s failed=%s topic_id=%s dry_run=%s",
        summary.scanned_count,
        summary.updated_count,
        summary.skipped_count,
        summary.failed_count,
        topic_id,
        dry_run,
    )


def run_export_image_rerank_manifest(
    *,
    output: Path,
    topic_id: str | None,
    limit: int | None,
    only_missing_images: bool,
    log_level: str,
    repo_root: Path,
    create_runtime_config_service_fn: Callable[..., Any],
    configure_cli_logging_fn: Callable[..., None],
    create_content_store_fn: Callable[..., Any],
    export_image_rerank_manifest_use_case_cls: type[Any],
    write_image_rerank_manifest_fn: Callable[..., None],
) -> None:
    config_service = create_runtime_config_service_fn(repo_root=repo_root)
    configure_cli_logging_fn(log_level=log_level, config_service=config_service)
    store = create_content_store_fn(config_service=config_service)
    manifest = export_image_rerank_manifest_use_case_cls(store=store).execute(
        topic_id=topic_id,
        limit=limit,
        only_missing_images=only_missing_images,
    )
    write_image_rerank_manifest_fn(manifest=manifest, output_path=output)
    logging.getLogger(__name__).info(
        "Image rerank manifest exported output=%s item_count=%s topic_id=%s only_missing_images=%s",
        output,
        manifest.item_count,
        topic_id,
        only_missing_images,
    )


def run_rerank_image_manifest(
    *,
    input_path: Path,
    output: Path,
    candidate_count: int,
    ollama_model: str | None,
    ollama_base_url: str | None,
    ollama_timeout_sec: int | None,
    log_level: str,
    repo_root: Path,
    create_runtime_config_service_fn: Callable[..., Any],
    configure_cli_logging_fn: Callable[..., None],
    read_image_rerank_manifest_fn: Callable[..., Any],
    rerank_image_manifest_use_case_cls: type[Any],
    write_image_rerank_decisions_fn: Callable[..., None],
    image_search_client_cls: type[Any],
    reranker_client_cls: type[Any],
) -> None:
    config_service = create_runtime_config_service_fn(repo_root=repo_root)
    configure_cli_logging_fn(log_level=log_level, config_service=config_service)
    manifest = read_image_rerank_manifest_fn(input_path=input_path)
    resolved_model = ollama_model or config_service.get_str("ollama_model")
    resolved_base_url = ollama_base_url or config_service.get_str("ollama_base_url")
    resolved_timeout = ollama_timeout_sec or config_service.get_int("ollama_timeout_sec")
    use_case = rerank_image_manifest_use_case_cls(
        image_search_client=image_search_client_cls(config_service=config_service),
        reranker_client=reranker_client_cls(
            base_url=resolved_base_url,
            model=resolved_model,
            timeout=resolved_timeout,
        ),
        candidate_count=candidate_count,
    )
    decisions = use_case.execute(
        manifest=manifest,
        model_name=resolved_model,
        progress_callback=lambda partial_decisions: write_image_rerank_decisions_fn(
            decisions=partial_decisions,
            output_path=output,
        ),
    )
    write_image_rerank_decisions_fn(decisions=decisions, output_path=output)
    logging.getLogger(__name__).info(
        "Image rerank decisions written output=%s item_count=%s model=%s candidate_count=%s",
        output,
        decisions.item_count,
        resolved_model,
        candidate_count,
    )


def run_apply_image_rerank_decisions(
    *,
    input_path: Path,
    assets_dir: Path,
    dry_run: bool,
    log_level: str,
    repo_root: Path,
    create_runtime_config_service_fn: Callable[..., Any],
    configure_cli_logging_fn: Callable[..., None],
    create_content_store_fn: Callable[..., Any],
    read_image_rerank_decisions_fn: Callable[..., Any],
    apply_image_rerank_decisions_use_case_cls: type[Any],
    remote_image_downloader_cls: type[Any],
) -> None:
    config_service = create_runtime_config_service_fn(repo_root=repo_root)
    configure_cli_logging_fn(log_level=log_level, config_service=config_service)
    store = create_content_store_fn(config_service=config_service)
    decisions = read_image_rerank_decisions_fn(input_path=input_path)
    summary = apply_image_rerank_decisions_use_case_cls(
        store=store,
        remote_image_downloader=remote_image_downloader_cls(),
        assets_dir=assets_dir,
    ).execute(
        decisions=decisions,
        dry_run=dry_run,
    )
    logging.getLogger(__name__).info(
        "Image rerank decisions applied input=%s updated=%s failed=%s dry_run=%s",
        input_path,
        summary["updated_count"],
        summary["failed_count"],
        dry_run,
    )
