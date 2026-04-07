from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TTS_MODULE = REPO_ROOT / "src" / "englishbot" / "telegram" / "tts.py"


def test_tts_module_does_not_pull_private_tts_state_helpers_from_bot() -> None:
    text = TTS_MODULE.read_text(encoding="utf-8")

    forbidden_snippets = (
        "bot_module._tts_task_lock(",
        "bot_module._tts_selected_voice_store(",
        "bot_module._advance_tts_selected_voice_name(",
        "bot_module._tts_recent_request(",
        "bot_module._set_tts_recent_request(",
    )

    assert not any(snippet in text for snippet in forbidden_snippets)
