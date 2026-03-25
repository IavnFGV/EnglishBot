from __future__ import annotations

from pathlib import Path

from englishbot.application.image_review_flow import ImageCandidateGenerator
from englishbot.domain.image_review_models import ImageCandidate
from englishbot.image_generation.clients import ComfyUIImageGenerationClient
from englishbot.image_generation.paths import build_item_image_ref

_DEFAULT_MODEL_PRESETS: dict[str, tuple[str, str | None]] = {
    "dreamshaper": ("dreamshaper_8.safetensors", None),
    "realistic-vision": (
        "Realistic_Vision_V5.1.safetensors",
        "vae-ft-mse-840000-ema-pruned.safetensors",
    ),
    "sd15": ("v1-5-pruned-emaonly.safetensors", None),
}


class ComfyUIImageCandidateGenerator(ImageCandidateGenerator):
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8188",
        model_presets: dict[str, tuple[str, str | None]] | None = None,
        width: int = 512,
        height: int = 512,
    ) -> None:
        self._base_url = base_url
        self._model_presets = model_presets or dict(_DEFAULT_MODEL_PRESETS)
        self._width = width
        self._height = height

    def generate_candidates(
        self,
        *,
        topic_id: str,
        item_id: str,
        english_word: str,
        prompt: str,
        assets_dir: Path,
        model_names: tuple[str, ...],
    ) -> list[ImageCandidate]:
        candidates: list[ImageCandidate] = []
        for model_name in model_names:
            checkpoint_name, vae_name = self._resolve_model_preset(model_name)
            output_path = assets_dir / topic_id / "review" / f"{item_id}--{model_name}.png"
            client = ComfyUIImageGenerationClient(
                base_url=self._base_url,
                checkpoint_name=checkpoint_name,
                vae_name=vae_name,
                width=self._width,
                height=self._height,
            )
            client.generate(
                prompt=prompt,
                english_word=english_word,
                output_path=output_path,
            )
            candidates.append(
                ImageCandidate(
                    model_name=model_name,
                    image_ref=build_item_image_ref(
                        assets_dir=assets_dir,
                        topic_id=topic_id,
                        item_id=f"review/{item_id}--{model_name}",
                    ),
                    output_path=output_path,
                    prompt=prompt,
                )
            )
        return candidates

    def _resolve_model_preset(self, model_name: str) -> tuple[str, str | None]:
        preset = self._model_presets.get(model_name)
        if preset is None:
            raise ValueError(f"Unknown image review model preset: {model_name}")
        return preset
