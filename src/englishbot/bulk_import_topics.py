from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from englishbot.cli import configure_cli_logging, create_cli_runtime_config_service
from englishbot.importing.bulk_topics import parse_bulk_topic_text, write_bulk_topic_content_packs
from englishbot.importing.cli import run_bulk_import_topics

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Bulk-import multiple topic word lists from one text file.",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@app.command()
def run(
    input_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, help="Bulk text file with multiple topic blocks."),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            dir_okay=True,
            file_okay=False,
            help="Optional directory for generated content pack JSON files.",
        ),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option(
            "--db-path",
            dir_okay=False,
            help="Optional SQLite database path for immediate import.",
        ),
    ] = None,
    no_db_import: Annotated[
        bool,
        typer.Option(
            "--no-db-import",
            help="Skip SQLite import.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level, for example INFO or DEBUG."),
    ] = "INFO",
) -> None:
    run_bulk_import_topics(
        input_path=input_path,
        output_dir=output_dir,
        db_path=db_path,
        no_db_import=no_db_import,
        log_level=log_level,
        repo_root=_REPO_ROOT,
        create_runtime_config_service_fn=create_cli_runtime_config_service,
        configure_cli_logging_fn=configure_cli_logging,
        parse_bulk_topic_text_fn=parse_bulk_topic_text,
        write_bulk_topic_content_packs_fn=write_bulk_topic_content_packs,
    )


if __name__ == "__main__":
    app()
