from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_GUARDED_MODULES = (
    REPO_ROOT / "src" / "englishbot" / "telegram" / "flow_tracking.py",
    REPO_ROOT / "src" / "englishbot" / "telegram" / "interaction.py",
    REPO_ROOT / "src" / "englishbot" / "telegram" / "assignment_progress.py",
    REPO_ROOT / "src" / "englishbot" / "telegram" / "image_review_support.py",
)


def test_tracked_message_modules_do_not_reach_into_bot_for_registry_or_chat_id() -> None:
    forbidden_snippets = (
        "bot_module._telegram_flow_messages(",
        "bot_module._message_chat_id(",
    )
    violations: list[str] = []

    for path in RUNTIME_GUARDED_MODULES:
        text = path.read_text(encoding="utf-8")
        if any(snippet in text for snippet in forbidden_snippets):
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []
