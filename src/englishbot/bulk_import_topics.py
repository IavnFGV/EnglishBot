from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from englishbot.__main__ import configure_logging
from englishbot.config import create_runtime_config_service
from englishbot.importing.bulk_topics import parse_bulk_topic_text, write_bulk_topic_content_packs

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Bulk-import multiple topic word lists from one text file.",
)


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
    configure_logging(log_level.upper())
    config_service = create_runtime_config_service()
    resolved_db_path = None if no_db_import else (db_path or config_service.get_path("content_db_path"))
    if no_db_import and output_dir is None:
        raise typer.BadParameter(
            "Use --output-dir when --no-db-import is set.",
            param_hint="--output-dir",
        )

    text = input_path.read_text(encoding="utf-8")
    drafts = parse_bulk_topic_text(text)
    results = write_bulk_topic_content_packs(
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


if __name__ == "__main__":
    app()
