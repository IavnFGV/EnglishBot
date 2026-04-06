from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from englishbot.__main__ import configure_logging
from englishbot.application.image_rerank_manifest_use_cases import (
    RerankImageManifestUseCase,
    read_image_rerank_manifest,
    write_image_rerank_decisions,
)
from englishbot.config import create_runtime_config_service
from englishbot.image_generation.ollama_reranker import OllamaPixabayVisionRerankerClient
from englishbot.image_generation.pixabay import PixabayImageSearchClient

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Read an exported manifest, rerank Pixabay candidates with Ollama, and write decisions JSON.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@app.command()
def main(
    input: Annotated[
        Path,
        typer.Option("--input", help="Path to the manifest JSON file."),
    ] = Path("output/image-rerank-manifest.json"),
    output: Annotated[
        Path,
        typer.Option("--output", help="Path to the decisions JSON file."),
    ] = Path("output/image-rerank-decisions.json"),
    candidate_count: Annotated[
        int,
        typer.Option("--candidate-count", min=1, max=6, help="How many top Pixabay candidates to evaluate."),
    ] = 3,
    ollama_model: Annotated[
        str | None,
        typer.Option("--ollama-model", help="Override Ollama model name."),
    ] = None,
    ollama_base_url: Annotated[
        str | None,
        typer.Option("--ollama-base-url", help="Override Ollama base URL."),
    ] = None,
    ollama_timeout_sec: Annotated[
        int | None,
        typer.Option("--ollama-timeout-sec", min=1, help="Override Ollama timeout in seconds."),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    env_file_path = _REPO_ROOT / ".env"
    load_dotenv(env_file_path, override=True)
    config_service = create_runtime_config_service(env_file_path=env_file_path)
    configure_logging(
        log_level.upper() or config_service.get_str("log_level"),
        log_file_path=config_service.get_path("log_file_path"),
        log_max_bytes=config_service.get_int("log_max_bytes"),
        log_backup_count=config_service.get_int("log_backup_count"),
    )
    manifest = read_image_rerank_manifest(input_path=input)
    resolved_model = ollama_model or config_service.get_str("ollama_model")
    resolved_base_url = ollama_base_url or config_service.get_str("ollama_base_url")
    resolved_timeout = ollama_timeout_sec or config_service.get_int("ollama_timeout_sec")
    use_case = RerankImageManifestUseCase(
        image_search_client=PixabayImageSearchClient(config_service=config_service),
        reranker_client=OllamaPixabayVisionRerankerClient(
            base_url=resolved_base_url,
            model=resolved_model,
            timeout=resolved_timeout,
        ),
        candidate_count=candidate_count,
    )
    decisions = use_case.execute(
        manifest=manifest,
        model_name=resolved_model,
        progress_callback=lambda partial_decisions: write_image_rerank_decisions(
            decisions=partial_decisions,
            output_path=output,
        ),
    )
    write_image_rerank_decisions(decisions=decisions, output_path=output)
    logging.getLogger(__name__).info(
        "Image rerank decisions written output=%s item_count=%s model=%s candidate_count=%s",
        output,
        decisions.item_count,
        resolved_model,
        candidate_count,
    )


if __name__ == "__main__":
    app()
