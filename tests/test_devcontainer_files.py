from pathlib import Path


def test_devcontainer_installs_sqlite3_binary() -> None:
    dockerfile = Path(".devcontainer/Dockerfile").read_text(encoding="utf-8")

    assert "sqlite3" in dockerfile


def test_devcontainer_recommends_vscode_sqlite_extension() -> None:
    devcontainer = Path(".devcontainer/devcontainer.json").read_text(encoding="utf-8")

    assert "alexcvzz.vscode-sqlite" in devcontainer
