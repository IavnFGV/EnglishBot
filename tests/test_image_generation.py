from __future__ import annotations

from pathlib import Path

import pytest

from englishbot.bot import _send_question
from englishbot.domain.models import TrainingMode, TrainingQuestion
from englishbot.image_generation.paths import build_item_asset_path
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_generation.prompts import fallback_image_prompt


def test_fallback_image_prompt_generation() -> None:
    assert (
        fallback_image_prompt("Dragon")
        == "A simple child-friendly illustration of dragon on a clean light background."
    )


def test_deterministic_asset_path_generation() -> None:
    assert build_item_asset_path(
        assets_dir=Path("assets"),
        topic_id="fairy-tales",
        item_id="fairy-tales-dragon",
    ) == Path("assets/fairy-tales/fairy-tales-dragon.png")


def test_content_pack_update_after_image_enrichment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    class RecordingClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, Path]] = []

        def generate(self, *, prompt: str, english_word: str, output_path: Path) -> None:
            self.calls.append((prompt, english_word, output_path))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")

    content_pack = {
        "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
        "lessons": [],
        "vocabulary_items": [
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
                "image_ref": None,
            }
        ],
    }
    client = RecordingClient()
    enricher = ContentPackImageEnricher(client)  # type: ignore[arg-type]

    enriched = enricher.enrich_content_pack(
        content_pack=content_pack,
        assets_dir=Path("assets"),
    )

    assert (
        enriched["vocabulary_items"][0]["image_ref"]
        == "assets/fairy-tales/fairy-tales-dragon.png"
    )
    assert enriched["vocabulary_items"][0]["image_prompt"] == fallback_image_prompt("Dragon")
    assert client.calls[0][2] == Path("assets/fairy-tales/fairy-tales-dragon.png")


def test_skip_behavior_when_image_already_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    existing_path = Path("assets/fairy-tales/fairy-tales-dragon.png")
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_bytes(b"existing")

    class RecordingClient:
        def __init__(self) -> None:
            self.called = False

        def generate(self, *, prompt: str, english_word: str, output_path: Path) -> None:
            self.called = True

    content_pack = {
        "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
        "lessons": [],
        "vocabulary_items": [
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
                "image_ref": "assets/fairy-tales/fairy-tales-dragon.png",
                "image_prompt": "Existing prompt",
            }
        ],
    }
    client = RecordingClient()
    enricher = ContentPackImageEnricher(client)  # type: ignore[arg-type]

    enriched = enricher.enrich_content_pack(
        content_pack=content_pack,
        assets_dir=Path("assets"),
        force=False,
    )

    assert (
        enriched["vocabulary_items"][0]["image_ref"]
        == "assets/fairy-tales/fairy-tales-dragon.png"
    )
    assert client.called is False


@pytest.mark.anyio
async def test_bot_rendering_falls_back_when_image_file_is_missing() -> None:
    class FakeMessage:
        def __init__(self) -> None:
            self.text_calls: list[tuple[str, object]] = []
            self.photo_calls: list[tuple[object, str | None, object]] = []

        async def reply_text(self, text: str, reply_markup=None) -> None:
            self.text_calls.append((text, reply_markup))

        async def reply_photo(self, photo, caption=None, reply_markup=None) -> None:
            self.photo_calls.append((photo, caption, reply_markup))

    class FakeUpdate:
        def __init__(self, message: FakeMessage) -> None:
            self.effective_message = message

    message = FakeMessage()
    update = FakeUpdate(message)
    question = TrainingQuestion(
        session_id="session-1",
        item_id="dragon",
        mode=TrainingMode.EASY,
        prompt="Dragon question",
        image_ref="assets/fairy-tales/missing.png",
        correct_answer="Dragon",
        options=["Dragon", "Castle", "Fairy"],
    )

    await _send_question(update, None, question)  # type: ignore[arg-type]

    assert len(message.text_calls) == 1
    assert len(message.photo_calls) == 0
