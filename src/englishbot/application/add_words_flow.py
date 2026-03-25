from __future__ import annotations

import uuid
from pathlib import Path

from englishbot.domain.add_words_models import AddWordsApprovalResult, AddWordsFlowState
from englishbot.importing.models import ImportLessonResult
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.logging_utils import logged_service_call
from englishbot.presentation.add_words_text import parse_edited_draft_text

_CUSTOM_CONTENT_DIR = Path("content/custom")


def _draft_item_count(result: ImportLessonResult) -> int | None:
    draft = result.draft
    return len(draft.vocabulary_items) if hasattr(draft, "vocabulary_items") else None


class AddWordsFlowHarness:
    def __init__(
        self,
        *,
        pipeline: LessonImportPipeline,
        validator: LessonExtractionValidator | None = None,
        writer: JsonContentPackWriter | None = None,
        custom_content_dir: Path = _CUSTOM_CONTENT_DIR,
    ) -> None:
        self._pipeline = pipeline
        self._validator = validator or LessonExtractionValidator()
        self._writer = writer or JsonContentPackWriter()
        self._custom_content_dir = custom_content_dir

    @logged_service_call(
        "AddWordsFlowHarness.extract",
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
        result=lambda value: {
            "flow_id": value.flow_id,
            "item_count": _draft_item_count(value.draft_result),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def extract(self, *, editor_user_id: int, raw_text: str) -> AddWordsFlowState:
        result = self._pipeline.extract_draft(
            raw_text=raw_text,
            enrich_image_prompts=False,
        )
        return AddWordsFlowState(
            flow_id=uuid.uuid4().hex[:12],
            editor_user_id=editor_user_id,
            raw_text=raw_text,
            draft_result=result,
        )

    @logged_service_call(
        "AddWordsFlowHarness.regenerate",
        transforms={"flow": lambda value: {"flow_id": value.flow_id}},
        result=lambda value: {
            "flow_id": value.flow_id,
            "item_count": _draft_item_count(value.draft_result),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def regenerate(self, *, flow: AddWordsFlowState) -> AddWordsFlowState:
        return AddWordsFlowState(
            flow_id=flow.flow_id,
            editor_user_id=flow.editor_user_id,
            raw_text=flow.raw_text,
            draft_result=self._pipeline.extract_draft(
                raw_text=flow.raw_text,
                enrich_image_prompts=False,
            ),
        )

    @logged_service_call(
        "AddWordsFlowHarness.apply_edit",
        transforms={
            "flow": lambda value: {"flow_id": value.flow_id},
            "edited_text": lambda value: {"text_length": len(value)},
        },
        result=lambda value: {
            "flow_id": value.flow_id,
            "item_count": _draft_item_count(value.draft_result),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def apply_edit(
        self,
        *,
        flow: AddWordsFlowState,
        edited_text: str,
    ) -> AddWordsFlowState:
        updated_draft = parse_edited_draft_text(
            edited_text,
            previous_draft=flow.draft_result.draft,
        )
        validation = self._validator.validate(updated_draft)
        return AddWordsFlowState(
            flow_id=flow.flow_id,
            editor_user_id=flow.editor_user_id,
            raw_text=edited_text,
            draft_result=ImportLessonResult(
                draft=updated_draft,
                validation=validation,
            ),
        )

    @logged_service_call(
        "AddWordsFlowHarness.approve",
        transforms={
            "flow": lambda value: {"flow_id": value.flow_id},
            "output_path": lambda value: {"output_path": value},
        },
        result=lambda value: {
            "item_count": len(value.import_result.draft.vocabulary_items),
            "output_path": value.output_path,
        },
    )
    def approve(
        self,
        *,
        flow: AddWordsFlowState,
        output_path: Path | None = None,
    ) -> AddWordsApprovalResult:
        finalized = self._pipeline.finalize_draft(draft=flow.draft_result.draft)
        if not finalized.validation.is_valid or finalized.canonicalization is None:
            raise ValueError("Draft finalization failed.")
        resolved_output_path = output_path or build_publish_output_path(
            finalized.canonicalization.content_pack.data,
            custom_content_dir=self._custom_content_dir,
        )
        self._writer.write(
            content_pack=finalized.canonicalization.content_pack,
            output_path=resolved_output_path,
        )
        return AddWordsApprovalResult(
            import_result=finalized,
            output_path=resolved_output_path,
        )


def build_publish_output_path(
    content_pack: dict[str, object],
    *,
    custom_content_dir: Path = _CUSTOM_CONTENT_DIR,
) -> Path:
    topic = content_pack.get("topic", {})
    if not isinstance(topic, dict):
        topic = {}
    topic_id = str(topic.get("id", "imported-topic")).strip() or "imported-topic"
    base_path = custom_content_dir / f"{topic_id}.json"
    if not base_path.exists():
        return base_path
    suffix = 2
    while True:
        candidate = custom_content_dir / f"{topic_id}-{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1
