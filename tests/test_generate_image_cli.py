from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from englishbot import generate_image


def test_generate_image_cli_uses_comfyui_client(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(
            self,
            *,
            base_url: str | None = None,
            checkpoint_name: str | None = None,
            vae_name: str | None = None,
            width: int = 512,
            height: int = 512,
        ) -> None:
            calls.append(
                {
                    "base_url": base_url,
                    "checkpoint_name": checkpoint_name,
                    "vae_name": vae_name,
                    "width": width,
                    "height": height,
                }
            )

        def generate(self, *, prompt: str, english_word: str, output_path: Path) -> None:
            output_path.write_bytes(b"png")
            calls.append(
                {
                    "prompt": prompt,
                    "english_word": english_word,
                    "output_path": output_path,
                }
            )

    monkeypatch.setattr(generate_image, "ComfyUIImageGenerationClient", FakeClient)
    monkeypatch.setattr(generate_image, "configure_logging", lambda level: None)
    runner = CliRunner()
    output_path = tmp_path / "dragon.png"

    result = runner.invoke(
        generate_image.app,
        [
            "--prompt",
            "Vocabulary flashcard. Show a dragon.",
            "--english-word",
            "Dragon",
            "--output",
            str(output_path),
            "--backend",
            "comfyui",
            "--comfyui-checkpoint",
            "dreamshaper_8.safetensors",
            "--width",
            "256",
            "--height",
            "256",
        ],
    )

    assert result.exit_code == 0
    assert output_path.read_bytes() == b"png"
    assert calls[0] == {
        "base_url": "http://127.0.0.1:8188",
        "checkpoint_name": "dreamshaper_8.safetensors",
        "vae_name": None,
        "width": 256,
        "height": 256,
    }
    assert calls[1] == {
        "prompt": "Vocabulary flashcard. Show a dragon.",
        "english_word": "Dragon",
        "output_path": output_path,
    }


def test_generate_image_cli_uses_placeholder_backend(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class FakePlaceholderClient:
        def generate(self, *, prompt: str, english_word: str, output_path: Path) -> None:
            output_path.write_bytes(b"placeholder")
            calls.append(
                {
                    "prompt": prompt,
                    "english_word": english_word,
                    "output_path": output_path,
                }
            )

    monkeypatch.setattr(
        generate_image,
        "LocalPlaceholderImageGenerationClient",
        lambda: FakePlaceholderClient(),
    )
    monkeypatch.setattr(generate_image, "configure_logging", lambda level: None)
    runner = CliRunner()
    output_path = tmp_path / "placeholder.png"

    result = runner.invoke(
        generate_image.app,
        [
            "--prompt",
            "Show scissors, closed.",
            "--output",
            str(output_path),
            "--backend",
            "placeholder",
        ],
    )

    assert result.exit_code == 0
    assert output_path.read_bytes() == b"placeholder"
    assert calls == [
        {
            "prompt": "Show scissors, closed.",
            "english_word": "image",
            "output_path": output_path,
        }
    ]
