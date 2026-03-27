from __future__ import annotations

import logging
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
from englishbot.image_generation.resilient import ResilientImageGenerationResult
from englishbot.image_generation.resilient import (
    ExternalImageCapabilityAvailability,
    ExternalImageGenerationGateway,
    ExternalImageGenerationTimeout,
    ExternalImageGenerationUnavailable,
    ResilientImageGenerator,
)
from englishbot.domain.image_review_models import ImageGenerationMetadata


def test_fallback_image_prompt_generation() -> None:
    assert fallback_image_prompt("Dragon") == (
        "dragon, cartoon style, simple, centered, white background"
    )


def test_compose_image_prompt_wraps_subject_in_shared_style() -> None:
    assert compose_image_prompt("a red dragon with small wings.") == (
        "a red dragon with small wings, cartoon style, simple, centered, white background"
    )


def test_compose_image_prompt_strengthens_human_royal_roles() -> None:
    assert compose_image_prompt("a prince with a crown", english_word="Prince") == (
        "a human prince wearing a golden crown and royal clothes, cartoon style, simple, "
        "centered, white background"
    )


def test_compose_image_prompt_deduplicates_already_wrapped_prompt() -> None:
    raw = (
        "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. Show a green dragon."
    )

    assert compose_image_prompt(raw, english_word="Dragon") == (
        "a green dragon, cartoon style, simple, centered, white background"
    )


def test_compose_image_prompt_deduplicates_legacy_wrapped_prompt() -> None:
    raw = (
        "Children's vocabulary flashcard, cute cartoon illustration, single main subject, "
        "centered composition, soft colors, clean light background, thick friendly outlines, "
        "simple shapes, educational card for a young child. Show a green dragon."
    )

    assert compose_image_prompt(raw, english_word="Dragon") == (
        "a green dragon, cartoon style, simple, centered, white background"
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

        def generate(self, *, prompt: str, english_word: str, output_path: Path):
            self.calls.append((prompt, english_word, output_path))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return ResilientImageGenerationResult(
                output_path=output_path,
                metadata=ImageGenerationMetadata(
                    path="smart",
                    smart_generation_status="success",
                ),
            )

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
        enriched.content_pack["vocabulary_items"][0]["image_ref"]
        == "assets/fairy-tales/fairy-tales-dragon.png"
    )
    assert (
        enriched.content_pack["vocabulary_items"][0]["image_prompt"]
        == fallback_image_prompt("Dragon")
    )
    assert client.calls[0][2] == Path("assets/fairy-tales/fairy-tales-dragon.png")


def test_existing_image_prompt_is_wrapped_in_shared_style(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    class RecordingClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, Path]] = []

        def generate(self, *, prompt: str, english_word: str, output_path: Path):
            self.calls.append((prompt, english_word, output_path))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return ResilientImageGenerationResult(
                output_path=output_path,
                metadata=ImageGenerationMetadata(
                    path="smart",
                    smart_generation_status="success",
                ),
            )

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
    assert enriched.content_pack["vocabulary_items"][0]["image_prompt"] == expected_prompt
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
        enriched.content_pack["vocabulary_items"][0]["image_ref"]
        == "assets/fairy-tales/fairy-tales-dragon.png"
    )
    assert client.called is False


def test_image_enrichment_reports_progress_for_each_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    class RecordingClient:
        def generate(self, *, prompt: str, english_word: str, output_path: Path):  # noqa: ARG002
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return ResilientImageGenerationResult(
                output_path=output_path,
                metadata=ImageGenerationMetadata(
                    path="smart",
                    smart_generation_status="success",
                ),
            )

    content_pack = {
        "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
        "lessons": [],
        "vocabulary_items": [
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
            },
            {
                "id": "fairy-tales-fairy",
                "english_word": "Fairy",
                "translation": "фея",
            },
        ],
    }
    client = RecordingClient()
    enricher = ContentPackImageEnricher(client)  # type: ignore[arg-type]
    reported_progress: list[tuple[int, int]] = []

    enricher.enrich_content_pack(
        content_pack=content_pack,
        assets_dir=Path("assets"),
        progress_callback=lambda processed, total: reported_progress.append((processed, total)),
    )

    assert reported_progress == [(1, 2), (2, 2)]


def test_content_pack_enrichment_keeps_fallback_generation_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    class RecordingClient:
        def generate(self, *, prompt: str, english_word: str, output_path: Path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"placeholder")
            return ResilientImageGenerationResult(
                output_path=output_path,
                metadata=ImageGenerationMetadata(
                    path="fallback",
                    smart_generation_status="unavailable",
                    status_messages=[
                        "Local AI image generation is currently unavailable. I will use placeholder images for now.",
                    ],
                ),
            )

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

    result = ContentPackImageEnricher(RecordingClient()).enrich_content_pack(
        content_pack=content_pack,
        assets_dir=Path("assets"),
    )

    assert result.generation_metadata is not None
    assert result.generation_metadata.path == "fallback"
    metadata = result.content_pack["metadata"]["image_generation"]
    assert metadata["smart_generation_status"] == "unavailable"


def test_resilient_image_generator_falls_back_when_external_service_is_unavailable(
    tmp_path: Path,
) -> None:
    class UnavailableGateway(ExternalImageGenerationGateway):
        def check_availability(self) -> ExternalImageCapabilityAvailability:
            return ExternalImageCapabilityAvailability(is_available=False, detail="offline")

        def generate(self, *, prompt: str, english_word: str, output_path: Path):  # noqa: ARG002
            return ExternalImageGenerationUnavailable(detail="offline")

    class PlaceholderClient:
        def generate(self, *, prompt: str, english_word: str, output_path: Path) -> None:  # noqa: ARG002
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"placeholder")

    result = ResilientImageGenerator(
        external_gateway=UnavailableGateway(),
        fallback_client=PlaceholderClient(),  # type: ignore[arg-type]
    ).generate(
        prompt="dragon",
        english_word="Dragon",
        output_path=tmp_path / "dragon.png",
    )

    assert result.metadata.path == "fallback"
    assert result.metadata.smart_generation_status == "unavailable"
    assert result.output_path.exists()


def test_resilient_image_generator_falls_back_after_timeout(
    tmp_path: Path,
) -> None:
    class TimeoutGateway(ExternalImageGenerationGateway):
        def check_availability(self) -> ExternalImageCapabilityAvailability:
            return ExternalImageCapabilityAvailability(is_available=True)

        def generate(self, *, prompt: str, english_word: str, output_path: Path):  # noqa: ARG002
            return ExternalImageGenerationTimeout(detail="read timeout")

    class PlaceholderClient:
        def generate(self, *, prompt: str, english_word: str, output_path: Path) -> None:  # noqa: ARG002
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"placeholder")

    result = ResilientImageGenerator(
        external_gateway=TimeoutGateway(),
        fallback_client=PlaceholderClient(),  # type: ignore[arg-type]
    ).generate(
        prompt="dragon",
        english_word="Dragon",
        output_path=tmp_path / "dragon.png",
    )

    assert result.metadata.path == "fallback"
    assert result.metadata.smart_generation_status == "timeout"


@pytest.mark.anyio
async def test_bot_rendering_falls_back_when_image_file_is_missing() -> None:
    class FakeMessage:
        def __init__(self) -> None:
            self.text_calls: list[tuple[str, object, str | None]] = []
            self.photo_calls: list[tuple[object, str | None, object, str | None]] = []

        async def reply_text(self, text: str, reply_markup=None, parse_mode=None) -> None:
            self.text_calls.append((text, reply_markup, parse_mode))

        async def reply_photo(self, photo, caption=None, reply_markup=None, parse_mode=None) -> None:
            self.photo_calls.append((photo, caption, reply_markup, parse_mode))

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
    assert message.text_calls[0][0] == "<b>Dragon question</b>"
    assert message.text_calls[0][2] == "HTML"


@pytest.mark.anyio
async def test_bot_rendering_uses_compact_text_prompt_for_text_mode() -> None:
    class FakeMessage:
        def __init__(self) -> None:
            self.text_calls: list[tuple[str, object, str | None]] = []

        async def reply_text(self, text: str, reply_markup=None, parse_mode=None) -> None:
            self.text_calls.append((text, reply_markup, parse_mode))

    class FakeUpdate:
        def __init__(self, message: FakeMessage) -> None:
            self.effective_message = message

    message = FakeMessage()
    update = FakeUpdate(message)
    question = TrainingQuestion(
        session_id="session-1",
        item_id="dragon",
        mode=TrainingMode.MEDIUM,
        prompt="Translation: дракон\nVisual clue: Image is shown above.\nShuffled letters hint: agrnod\nType the English word.",
        image_ref=None,
        correct_answer="Dragon",
        letter_hint="agrnod",
    )

    await _send_question(update, None, question)  # type: ignore[arg-type]

    assert message.text_calls == [
        ("<b>дракон</b>\n\n<b>agrnod</b>", None, "HTML")
    ]


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


def test_comfyui_client_logs_full_prompt_and_model_parameters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
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
    caplog.set_level(logging.DEBUG, logger="englishbot.image_generation.clients")
    client = ComfyUIImageGenerationClient(
        base_url="http://127.0.0.1:8188",
        timeout=5,
        checkpoint_name="dreamshaper_8.safetensors",
        seed=77,
    )
    prompt = (
        "Vocabulary flashcard, clear cartoon illustration, single main subject, centered "
        "composition, soft colors, clean light background, thick friendly outlines, simple "
        "shapes. Show a green dragon with small wings."
    )

    client.generate(
        prompt=prompt,
        english_word="Dragon",
        output_path=tmp_path / "dragon.png",
    )

    assert prompt in caplog.text
    assert "checkpoint=dreamshaper_8.safetensors" in caplog.text
    assert "negative_prompt=" in caplog.text
    assert "blurry, distorted, text, watermark, horror, gore" in caplog.text


def test_comfyui_client_logs_full_request_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
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
    caplog.set_level(logging.DEBUG, logger="englishbot.image_generation.clients")
    client = ComfyUIImageGenerationClient(
        base_url="http://127.0.0.1:8188",
        timeout=5,
        checkpoint_name="dreamshaper_8.safetensors",
        seed=77,
        width=256,
        height=256,
    )

    client.generate(
        prompt="Vocabulary flashcard. Show scissors, closed.",
        english_word="Scissors",
        output_path=tmp_path / "scissors.png",
    )

    assert (
        "ComfyUIImageGenerationClient request payload url=http://127.0.0.1:8188/prompt"
        in caplog.text
    )
    assert '"client_id":' in caplog.text
    assert '"prompt_id":' in caplog.text
    assert '"ckpt_name": "dreamshaper_8.safetensors"' in caplog.text
    assert '"width": 256' in caplog.text
    assert '"height": 256' in caplog.text
    assert '"sampler_name": "euler"' in caplog.text
    assert '"scheduler": "normal"' in caplog.text
    assert '"steps": 20' in caplog.text
    assert '"cfg": 7' in caplog.text


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


def test_comfyui_client_uses_configured_preview_size(
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
            assert json["prompt"]["5"]["inputs"]["width"] == 256
            assert json["prompt"]["5"]["inputs"]["height"] == 256
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
        width=256,
        height=256,
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
