from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "englishbot"
ALLOWED_DIRECT_BUTTON_MODULES = {
    SRC_ROOT / "telegram" / "buttons.py",
}


def _iter_python_files() -> list[Path]:
    return sorted(path for path in SRC_ROOT.rglob("*.py") if path not in ALLOWED_DIRECT_BUTTON_MODULES)


def test_project_does_not_import_inlinekeyboardbutton_directly_from_telegram() -> None:
    violations: list[str] = []

    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "telegram":
                for alias in node.names:
                    if alias.name == "InlineKeyboardButton":
                        violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_project_does_not_call_telegram_inlinekeyboardbutton_directly() -> None:
    violations: list[str] = []

    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "InlineKeyboardButton":
                violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []
