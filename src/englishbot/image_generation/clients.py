from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Protocol

from englishbot.logging_utils import logged_service_call


class ImageGenerationClient(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        ...


class FakeImageGenerationClient:
    @logged_service_call(
        "FakeImageGenerationClient.generate",
        transforms={
            "prompt": lambda value: {"prompt": value},
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"fake-image:{english_word}|{prompt}".encode())


class LocalPlaceholderImageGenerationClient:
    """Simple local placeholder image generator for offline development."""

    @logged_service_call(
        "LocalPlaceholderImageGenerationClient.generate",
        transforms={
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as error:
            raise RuntimeError(
                "Pillow is required for local placeholder image generation."
            ) from error

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1024, 1024), color=(248, 244, 232))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        draw.rounded_rectangle(
            (80, 80, 944, 944),
            radius=48,
            fill=(255, 252, 246),
            outline=(64, 92, 118),
            width=6,
        )
        draw.ellipse((120, 120, 280, 280), fill=(255, 208, 122), outline=(64, 92, 118), width=4)
        draw.rectangle((744, 120, 904, 280), fill=(154, 208, 194), outline=(64, 92, 118), width=4)

        draw.text((120, 340), english_word[:48], fill=(35, 47, 62), font=font)
        prompt_lines = _wrap_text(prompt, max_line_length=38)[:8]
        y = 430
        for line in prompt_lines:
            draw.text((120, y), line, fill=(70, 82, 94), font=font)
            y += 40

        image.save(output_path, format="PNG")


class ComfyUIImageGenerationClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: int = 300,
        poll_interval_seconds: float = 1.0,
        checkpoint_name: str | None = None,
        vae_name: str | None = None,
        seed: int | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")).rstrip(
            "/"
        )
        self._timeout = timeout
        self._poll_interval_seconds = poll_interval_seconds
        self._checkpoint_name = checkpoint_name or os.getenv(
            "COMFYUI_CHECKPOINT_NAME",
            "v1-5-pruned-emaonly.safetensors",
        )
        self._vae_name = vae_name or os.getenv("COMFYUI_VAE_NAME", "")
        self._seed = seed if seed is not None else int(os.getenv("COMFYUI_SEED", "5"))

    @logged_service_call(
        "ComfyUIImageGenerationClient.generate",
        transforms={
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> None:
        try:
            import requests
        except ImportError as error:
            raise RuntimeError("requests is required for ComfyUI image generation.") from error

        output_path.parent.mkdir(parents=True, exist_ok=True)
        client_id = str(uuid.uuid4())
        prompt_id = str(uuid.uuid4())
        workflow = self._build_workflow(
            prompt=prompt,
            english_word=english_word,
        )
        queue_response = requests.post(
            f"{self._base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id, "prompt_id": prompt_id},
            timeout=self._timeout,
        )
        queue_response.raise_for_status()
        prompt_id = str(queue_response.json().get("prompt_id", prompt_id))
        image_data = self._wait_for_image_bytes(
            requests_module=requests,
            prompt_id=prompt_id,
        )
        output_path.write_bytes(image_data)

    def _wait_for_image_bytes(self, *, requests_module, prompt_id: str) -> bytes:
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            response = requests_module.get(
                f"{self._base_url}/history/{prompt_id}",
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            history = payload.get(prompt_id)
            if not isinstance(history, dict):
                time.sleep(self._poll_interval_seconds)
                continue
            status = history.get("status", {})
            if isinstance(status, dict):
                failure_message = _extract_comfyui_failure_message(status.get("messages"))
                if failure_message is not None:
                    raise RuntimeError(f"ComfyUI prompt failed: {failure_message}")
            outputs = history.get("outputs", {})
            if not isinstance(outputs, dict):
                time.sleep(self._poll_interval_seconds)
                continue
            image_descriptor = self._extract_first_image_descriptor(outputs)
            if image_descriptor is None:
                time.sleep(self._poll_interval_seconds)
                continue
            image_response = requests_module.get(
                f"{self._base_url}/view",
                params=image_descriptor,
                timeout=self._timeout,
            )
            image_response.raise_for_status()
            return image_response.content
        raise TimeoutError(f"Timed out waiting for ComfyUI prompt_id={prompt_id}")

    def _extract_first_image_descriptor(self, outputs: dict[str, object]) -> dict[str, str] | None:
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get("images")
            if not isinstance(images, list) or not images:
                continue
            image = images[0]
            if not isinstance(image, dict):
                continue
            filename = image.get("filename")
            subfolder = image.get("subfolder", "")
            folder_type = image.get("type", "output")
            if not isinstance(filename, str) or not filename.strip():
                continue
            return {
                "filename": filename,
                "subfolder": str(subfolder),
                "type": str(folder_type),
            }
        return None

    def _build_workflow(self, *, prompt: str, english_word: str) -> dict[str, object]:
        negative_prompt = _negative_prompt_for_word(english_word)
        filename_prefix = f"EnglishBot_{_safe_prefix(english_word)}"
        workflow: dict[str, object] = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 7,
                    "denoise": 1,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "seed": self._seed,
                    "steps": 20,
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": self._checkpoint_name,
                },
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "batch_size": 1,
                    "height": 512,
                    "width": 512,
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": prompt,
                },
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": negative_prompt,
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2],
                },
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["8", 0],
                },
            },
        }
        if self._vae_name:
            workflow["10"] = {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": self._vae_name,
                },
            }
            workflow["8"]["inputs"]["vae"] = ["10", 0]
        return json.loads(json.dumps(workflow))


def _wrap_text(text: str, *, max_line_length: int) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) <= max_line_length:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _safe_prefix(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.strip())[:48] or "image"


def _negative_prompt_for_word(english_word: str) -> str:
    base = "blurry, distorted, text, watermark, horror, gore, scary, low quality, dark"
    normalized = english_word.strip().lower()
    if normalized in {"king", "queen", "prince", "princess", "wizard"}:
        return (
            base
            + ", animal, dog, wolf, furry, snout, muzzle, beak, paws, tail, animal ears,"
            " non-human face"
        )
    return base


def _extract_comfyui_failure_message(messages: object) -> str | None:
    if not isinstance(messages, list):
        return None
    for entry in messages:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        event_type, payload = entry
        if event_type != "execution_error" or not isinstance(payload, dict):
            continue
        exception_message = payload.get("exception_message")
        if isinstance(exception_message, str) and exception_message.strip():
            return exception_message.strip()
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
    return None
