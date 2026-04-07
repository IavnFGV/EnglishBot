from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_MODULES = (
    REPO_ROOT / "src" / "englishbot" / "telegram" / "editor_add_words.py",
    REPO_ROOT / "src" / "englishbot" / "telegram" / "editor_images.py",
)


def test_editor_modules_do_not_call_bot_private_helpers_directly() -> None:
    violations: list[str] = []

    for path in EDITOR_MODULES:
        text = path.read_text(encoding="utf-8")
        if "bot_module._" in text:
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []
