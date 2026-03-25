from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Protocol

from englishbot.domain.image_review_models import (
    ImageCandidate,
    ImageReviewFlowState,
    ImageReviewItem,
)
from englishbot.image_generation.prompts import compose_image_prompt, fallback_image_prompt
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.models import CanonicalContentPack, LessonExtractionDraft
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.logging_utils import logged_service_call


class ImageCandidateGenerator(Protocol):
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
        ...


class ImageReviewFlowHarness:
    def __init__(
        self,
        *,
        canonicalizer: DraftToContentPackCanonicalizer,
        writer: JsonContentPackWriter,
        candidate_generator: ImageCandidateGenerator,
        assets_dir: Path,
        default_model_names: tuple[str, ...] = (
            "dreamshaper",
            "realistic-vision",
            "sd15",
        ),
    ) -> None:
        self._canonicalizer = canonicalizer
        self._writer = writer
        self._candidate_generator = candidate_generator
        self._assets_dir = assets_dir
        self._default_model_names = default_model_names

    @logged_service_call(
        "ImageReviewFlowHarness.start",
        transforms={"draft": lambda value: {"item_count": len(value.vocabulary_items)}},
        result=lambda value: {"flow_id": value.flow_id, "item_count": len(value.items)},
    )
    def start(
        self,
        *,
        editor_user_id: int,
        draft: LessonExtractionDraft,
        model_names: tuple[str, ...] | None = None,
    ) -> ImageReviewFlowState:
        canonical = self._canonicalizer.convert(draft)
        return self.start_from_content_pack(
            editor_user_id=editor_user_id,
            content_pack=canonical.content_pack.data,
            model_names=model_names,
        )

    @logged_service_call(
        "ImageReviewFlowHarness.start_from_content_pack",
        transforms={
            "content_pack": lambda value: {
                "item_count": (
                    len(value.get("vocabulary_items", [])) if isinstance(value, dict) else None
                )
            }
        },
        include=("editor_user_id",),
        result=lambda value: {"flow_id": value.flow_id, "item_count": len(value.items)},
    )
    def start_from_content_pack(
        self,
        *,
        editor_user_id: int,
        content_pack: dict[str, object],
        model_names: tuple[str, ...] | None = None,
        selected_item_id: str | None = None,
    ) -> ImageReviewFlowState:
        normalized_content_pack = json.loads(json.dumps(content_pack))
        topic = normalized_content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        if not topic_id:
            raise ValueError("topic.id is required to start image review.")
        configured_models = model_names or self._default_model_names
        review_items: list[ImageReviewItem] = []
        found_selected_item = selected_item_id is None
        for raw_item in normalized_content_pack.get("vocabulary_items", []):
            if not isinstance(raw_item, dict):
                continue
            item_id = str(raw_item.get("id", "")).strip()
            english_word = str(raw_item.get("english_word", "")).strip()
            translation = str(raw_item.get("translation", "")).strip()
            if not item_id or not english_word:
                continue
            if selected_item_id is not None and item_id != selected_item_id:
                continue
            found_selected_item = True
            raw_prompt = str(raw_item.get("image_prompt", "")).strip()
            prompt = (
                compose_image_prompt(raw_prompt, english_word=english_word)
                if raw_prompt
                else fallback_image_prompt(english_word)
            )
            review_items.append(
                ImageReviewItem(
                    item_id=item_id,
                    english_word=english_word,
                    translation=translation,
                    prompt=prompt,
                    candidates=[],
                )
            )
        if not found_selected_item:
            raise ValueError("Selected vocabulary item was not found in the content pack.")
        normalized_content_pack.setdefault("metadata", {})
        if isinstance(normalized_content_pack["metadata"], dict):
            normalized_content_pack["metadata"]["image_review_model_names"] = list(
                configured_models
            )
        return ImageReviewFlowState(
            flow_id=uuid.uuid4().hex[:12],
            editor_user_id=editor_user_id,
            content_pack=normalized_content_pack,
            items=review_items,
        )

    @logged_service_call(
        "ImageReviewFlowHarness.generate_current_item_candidates",
        transforms={
            "flow": lambda value: {
                "flow_id": value.flow_id,
                "current_index": value.current_index,
            }
        },
        result=lambda value: {
            "candidate_count": (
                len(value.current_item.candidates) if value.current_item else 0
            )
        },
    )
    def generate_current_item_candidates(
        self,
        *,
        flow: ImageReviewFlowState,
    ) -> ImageReviewFlowState:
        updated = copy.deepcopy(flow)
        current_item = updated.current_item
        if current_item is None:
            return updated
        if current_item.candidates:
            return updated
        topic = updated.content_pack.get("topic", {})
        topic_id = str(topic.get("id", "")).strip() if isinstance(topic, dict) else ""
        if not topic_id:
            raise ValueError("topic.id is required to generate image candidates.")
        metadata = updated.content_pack.get("metadata", {})
        configured_models = self._default_model_names
        if isinstance(metadata, dict):
            raw_model_names = metadata.get("image_review_model_names")
            if isinstance(raw_model_names, list):
                configured_models = tuple(
                    str(value).strip() for value in raw_model_names if str(value).strip()
                ) or self._default_model_names
        current_item.candidates = self._candidate_generator.generate_candidates(
            topic_id=topic_id,
            item_id=current_item.item_id,
            english_word=current_item.english_word,
            prompt=current_item.prompt,
            assets_dir=self._assets_dir,
            model_names=configured_models,
        )
        return updated

    @logged_service_call(
        "ImageReviewFlowHarness.update_current_item_prompt",
        transforms={
            "flow": lambda value: {
                "flow_id": value.flow_id,
                "current_index": value.current_index,
            },
            "prompt": lambda value: {"prompt": value},
        },
        include=("item_id",),
        result=lambda value: {
            "candidate_count": (
                len(value.current_item.candidates) if value.current_item else 0
            )
        },
    )
    def update_current_item_prompt(
        self,
        *,
        flow: ImageReviewFlowState,
        item_id: str,
        prompt: str,
    ) -> ImageReviewFlowState:
        updated = copy.deepcopy(flow)
        current_item = updated.current_item
        if current_item is None or current_item.item_id != item_id:
            raise ValueError("This review item is no longer active.")
        normalized_prompt = " ".join(prompt.split()).strip()
        if not normalized_prompt:
            raise ValueError("Image prompt is required.")
        current_item.prompt = normalized_prompt
        current_item.candidates = []
        current_item.selected_candidate_index = None
        current_item.skipped = False
        return updated

    @logged_service_call(
        "ImageReviewFlowHarness.select_candidate",
        transforms={"flow": lambda value: {"flow_id": value.flow_id}},
        include=("item_id", "candidate_index"),
        result=lambda value: {"current_index": value.current_index, "completed": value.completed},
    )
    def select_candidate(
        self,
        *,
        flow: ImageReviewFlowState,
        item_id: str,
        candidate_index: int,
    ) -> ImageReviewFlowState:
        updated = copy.deepcopy(flow)
        current_item = updated.current_item
        if current_item is None or current_item.item_id != item_id:
            raise ValueError("This review item is no longer active.")
        if candidate_index < 0 or candidate_index >= len(current_item.candidates):
            raise ValueError("Candidate index is out of bounds.")
        current_item.selected_candidate_index = candidate_index
        current_item.skipped = False
        candidate = current_item.candidates[candidate_index]
        self._apply_selected_image_ref(
            updated.content_pack,
            item_id=item_id,
            image_ref=candidate.image_ref,
        )
        updated.current_index += 1
        return updated

    @logged_service_call(
        "ImageReviewFlowHarness.skip_item",
        transforms={"flow": lambda value: {"flow_id": value.flow_id}},
        include=("item_id",),
        result=lambda value: {"current_index": value.current_index, "completed": value.completed},
    )
    def skip_item(self, *, flow: ImageReviewFlowState, item_id: str) -> ImageReviewFlowState:
        updated = copy.deepcopy(flow)
        current_item = updated.current_item
        if current_item is None or current_item.item_id != item_id:
            raise ValueError("This review item is no longer active.")
        current_item.skipped = True
        current_item.selected_candidate_index = None
        updated.current_index += 1
        return updated

    @logged_service_call(
        "ImageReviewFlowHarness.attach_uploaded_image",
        transforms={"flow": lambda value: {"flow_id": value.flow_id}},
        include=("item_id", "image_ref"),
        result=lambda value: {"current_index": value.current_index, "completed": value.completed},
    )
    def attach_uploaded_image(
        self,
        *,
        flow: ImageReviewFlowState,
        item_id: str,
        image_ref: str,
        output_path: Path,
    ) -> ImageReviewFlowState:
        updated = copy.deepcopy(flow)
        current_item = updated.current_item
        if current_item is None or current_item.item_id != item_id:
            raise ValueError("This review item is no longer active.")
        current_item.candidates.append(
            ImageCandidate(
                model_name="user-upload",
                image_ref=image_ref,
                output_path=output_path,
                prompt=current_item.prompt,
            )
        )
        current_item.selected_candidate_index = len(current_item.candidates) - 1
        current_item.skipped = False
        self._apply_selected_image_ref(
            updated.content_pack,
            item_id=item_id,
            image_ref=image_ref,
        )
        updated.current_index += 1
        return updated

    @logged_service_call(
        "ImageReviewFlowHarness.publish",
        transforms={
            "flow": lambda value: {"flow_id": value.flow_id, "item_count": len(value.items)},
            "output_path": lambda value: {"output_path": value},
        },
    )
    def publish(self, *, flow: ImageReviewFlowState, output_path: Path) -> None:
        self._writer.write(
            content_pack=CanonicalContentPack(data=flow.content_pack),
            output_path=output_path,
        )

    def _apply_selected_image_ref(
        self,
        content_pack: dict[str, object],
        *,
        item_id: str,
        image_ref: str,
    ) -> None:
        raw_items = content_pack.get("vocabulary_items", [])
        if not isinstance(raw_items, list):
            return
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("id", "")).strip() != item_id:
                continue
            raw_item["image_ref"] = image_ref
            return
