from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from englishbot.cli import configure_cli_logging, create_cli_runtime_config_service
from englishbot.application.image_rerank_manifest_use_cases import (
    RerankImageManifestUseCase,
    read_image_rerank_manifest,
    write_image_rerank_decisions,
)
from englishbot.image_generation.ollama_reranker import OllamaPixabayVisionRerankerClient
from englishbot.image_generation.pixabay import PixabayImageSearchClient
from englishbot.image_tooling import run_rerank_image_manifest

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
    run_rerank_image_manifest(
        input_path=input,
        output=output,
        candidate_count=candidate_count,
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
        ollama_timeout_sec=ollama_timeout_sec,
        log_level=log_level,
        repo_root=_REPO_ROOT,
        create_runtime_config_service_fn=create_cli_runtime_config_service,
        configure_cli_logging_fn=configure_cli_logging,
        read_image_rerank_manifest_fn=read_image_rerank_manifest,
        rerank_image_manifest_use_case_cls=RerankImageManifestUseCase,
        write_image_rerank_decisions_fn=write_image_rerank_decisions,
        image_search_client_cls=PixabayImageSearchClient,
        reranker_client_cls=OllamaPixabayVisionRerankerClient,
    )


if __name__ == "__main__":
    app()
