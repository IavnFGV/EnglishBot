from __future__ import annotations

from pathlib import Path

import pytest

from englishbot.bot import _send_question
from englishbot.domain.models import TrainingMode, TrainingQuestion
from englishbot.image_generation.clients import (
    ComfyUIImageGenerationClient,
    _negative_prompt_for_word,
)
from englishbot.image_generation.paths import build_item_asset_path
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_generation.prompts import compose_image_prompt, fallback_image_prompt


def test_fallback_image_prompt_generation() -> None:
    assert (
        fallback_image_prompt("Dragon")
        == "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. Show dragon."
    )


def test_compose_image_prompt_wraps_subject_in_shared_style() -> None:
    assert compose_image_prompt("a red dragon with small wings.") == (
        "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. Show a red dragon with small wings."
    )


def test_compose_image_prompt_strengthens_human_royal_roles() -> None:
    assert compose_image_prompt("a prince with a crown", english_word="Prince") == (
        "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. "
        "Show a human prince wearing a golden crown and royal clothes."
    )


def test_compose_image_prompt_deduplicates_already_wrapped_prompt() -> None:
    raw = (
        "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. Show illustration of a green dragon, "
        "simple cartoon style, centered, white background, colorful, no text."
    )

    assert compose_image_prompt(raw, english_word="Dragon") == raw


def test_compose_image_prompt_deduplicates_legacy_wrapped_prompt() -> None:
    raw = (
        "Children's vocabulary flashcard, cute cartoon illustration, single main subject, "
        "centered composition, soft colors, clean light background, thick friendly outlines, "
        "simple shapes, educational card for a young child. Show illustration of a green dragon, "
        "simple cartoon style, centered, white background, colorful, no text."
    )

    assert compose_image_prompt(raw, english_word="Dragon") == (
        "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. Show illustration of a green dragon, simple cartoon style, centered, white "
        "background, colorful, no text."
    )


def test_negative_prompt_for_human_royal_roles_blocks_animal_bias() -> None:
    negative = _negative_prompt_for_word("Prince")
    assert "dog" in negative
    assert "animal" in negative
    assert "snout" in negative


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


def test_existing_image_prompt_is_wrapped_in_shared_style(
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
                "image_prompt": "a red dragon with tiny wings",
            }
        ],
    }
    client = RecordingClient()
    enricher = ContentPackImageEnricher(client)  # type: ignore[arg-type]

    enriched = enricher.enrich_content_pack(
        content_pack=content_pack,
        assets_dir=Path("assets"),
    )

    expected_prompt = compose_image_prompt("a red dragon with tiny wings")
    assert enriched["vocabulary_items"][0]["image_prompt"] == expected_prompt
    assert client.calls[0][0] == expected_prompt


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


def test_comfyui_client_generates_image_via_http_protocol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_bytes = b"png-data"

    class FakeResponse:
        def __init__(self, payload=None, content: bytes | None = None) -> None:
            self._payload = payload or {}
            self.content = content or b""

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:8188/prompt"
            assert "prompt" in json
            sampler = json["prompt"]["3"]["inputs"]
            assert sampler["seed"] == 77
            return FakeResponse({"prompt_id": "prompt-123"})

        @staticmethod
        def get(url: str, params=None, timeout: int = 120) -> FakeResponse:
            if url == "http://127.0.0.1:8188/history/prompt-123":
                return FakeResponse(
                    {
                        "prompt-123": {
                            "outputs": {
                                "9": {
                                    "images": [
                                        {
                                            "filename": "dragon.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                )
            if url == "http://127.0.0.1:8188/view":
                assert params == {
                    "filename": "dragon.png",
                    "subfolder": "",
                    "type": "output",
                }
                return FakeResponse(content=image_bytes)
            raise AssertionError(f"Unexpected URL: {url}")

    import sys

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = ComfyUIImageGenerationClient(base_url="http://127.0.0.1:8188", timeout=5, seed=77)
    output_path = tmp_path / "dragon.png"

    client.generate(
        prompt="A child-friendly dragon.",
        english_word="Dragon",
        output_path=output_path,
    )

    assert output_path.read_bytes() == image_bytes


def test_comfyui_client_uses_explicit_vae_loader_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_bytes = b"png-data"

    class FakeResponse:
        def __init__(self, payload=None, content: bytes | None = None) -> None:
            self._payload = payload or {}
            self.content = content or b""

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert json["prompt"]["10"]["class_type"] == "VAELoader"
            assert json["prompt"]["10"]["inputs"]["vae_name"] == "ReVAnimatedVAE.safetensors"
            assert json["prompt"]["8"]["inputs"]["vae"] == ["10", 0]
            return FakeResponse({"prompt_id": "prompt-123"})

        @staticmethod
        def get(url: str, params=None, timeout: int = 120) -> FakeResponse:
            if url.endswith("/history/prompt-123"):
                return FakeResponse(
                    {
                        "prompt-123": {
                            "outputs": {
                                "9": {
                                    "images": [
                                        {
                                            "filename": "dragon.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                )
            if url.endswith("/view"):
                return FakeResponse(content=image_bytes)
            raise AssertionError(f"Unexpected URL: {url}")

    import sys

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = ComfyUIImageGenerationClient(
        base_url="http://127.0.0.1:8188",
        timeout=5,
        vae_name="ReVAnimatedVAE.safetensors",
    )
    output_path = tmp_path / "dragon.png"

    client.generate(
        prompt="A child-friendly dragon.",
        english_word="Dragon",
        output_path=output_path,
    )

    assert output_path.read_bytes() == image_bytes


def test_comfyui_client_raises_runtime_error_from_execution_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeResponse:
        def __init__(self, payload=None, content: bytes | None = None) -> None:
            self._payload = payload or {}
            self.content = content or b""

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse({"prompt_id": "prompt-123"})

        @staticmethod
        def get(url: str, params=None, timeout: int = 120) -> FakeResponse:
            if url.endswith("/history/prompt-123"):
                return FakeResponse(
                    {
                        "prompt-123": {
                            "status": {
                                "messages": [
                                    [
                                        "execution_error",
                                        {"exception_message": "ERROR: VAE is invalid: None"},
                                    ]
                                ]
                            },
                            "outputs": {},
                        }
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    import sys

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = ComfyUIImageGenerationClient(base_url="http://127.0.0.1:8188", timeout=5)

    with pytest.raises(RuntimeError, match="VAE is invalid"):
        client.generate(
            prompt="A child-friendly dragon.",
            english_word="Dragon",
            output_path=tmp_path / "dragon.png",
        )
