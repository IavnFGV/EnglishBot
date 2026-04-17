from __future__ import annotations

import logging
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from englishbot.cli import configure_cli_logging, create_cli_runtime_config_service
from englishbot.config import Settings
from englishbot.webapp_server import create_web_app as server_create_web_app

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def create_web_app(settings: Settings):
    return server_create_web_app(settings)


def main() -> None:
    config_service = create_cli_runtime_config_service(repo_root=_REPO_ROOT)
    settings = Settings.from_config_service(config_service)
    configure_cli_logging(log_level=settings.log_level, config_service=config_service)
    application = create_web_app(settings)
    logger.info(
        "Starting Telegram Web App server host=%s port=%s db_path=%s",
        settings.web_app_host,
        settings.web_app_port,
        settings.content_db_path,
    )
    with make_server(
        settings.web_app_host,
        settings.web_app_port,
        application,
        server_class=ThreadingWSGIServer,
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
