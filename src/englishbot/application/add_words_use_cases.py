from __future__ import annotations

from pathlib import Path

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.domain.add_words_models import AddWordsApprovalResult, AddWordsFlowState
from englishbot.domain.repositories import AddWordsFlowRepository
from englishbot.logging_utils import logged_service_call


def _flow_item_count(flow: AddWordsFlowState) -> int | None:
    draft = flow.draft_result.draft
    return len(draft.vocabulary_items) if hasattr(draft, "vocabulary_items") else None


class StartAddWordsFlowUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "StartAddWordsFlowUseCase.execute",
        include=("user_id",),
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
        result=lambda value: {
            "flow_id": value.flow_id,
            "item_count": _flow_item_count(value),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def execute(self, *, user_id: int, raw_text: str) -> AddWordsFlowState:
        flow = self._harness.extract(editor_user_id=user_id, raw_text=raw_text)
        self._flow_repository.save(flow)
        return flow


class GetActiveAddWordsFlowUseCase:
    def __init__(self, flow_repository: AddWordsFlowRepository) -> None:
        self._flow_repository = flow_repository

    @logged_service_call(
        "GetActiveAddWordsFlowUseCase.execute",
        include=("user_id",),
        result=lambda value: {
            "found": value is not None,
            "flow_id": value.flow_id if value else None,
        },
    )
    def execute(self, *, user_id: int) -> AddWordsFlowState | None:
        return self._flow_repository.get_active_by_user(user_id)


class ApplyAddWordsEditUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "ApplyAddWordsEditUseCase.execute",
        include=("user_id", "flow_id"),
        transforms={"edited_text": lambda value: {"text_length": len(value)}},
        result=lambda value: {
            "flow_id": value.flow_id,
            "item_count": _flow_item_count(value),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        edited_text: str,
    ) -> AddWordsFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.apply_edit(flow=flow, edited_text=edited_text)
        self._flow_repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._flow_repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This draft is no longer active.")
        return flow


class RegenerateAddWordsDraftUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "RegenerateAddWordsDraftUseCase.execute",
        include=("user_id", "flow_id"),
        result=lambda value: {
            "flow_id": value.flow_id,
            "item_count": _flow_item_count(value),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def execute(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.regenerate(flow=flow)
        self._flow_repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._flow_repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This draft is no longer active.")
        return flow


class ApproveAddWordsDraftUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "ApproveAddWordsDraftUseCase.execute",
        include=("user_id", "flow_id"),
        transforms={"output_path": lambda value: {"output_path": value}},
        result=lambda value: {
            "topic_id": value.published_topic_id,
            "output_path": value.output_path,
            "item_count": len(value.import_result.draft.vocabulary_items),
        },
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        output_path: Path | None = None,
    ) -> AddWordsApprovalResult:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        approved = self._harness.approve(flow=flow, output_path=output_path)
        self._flow_repository.discard_active_by_user(user_id)
        return approved

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._flow_repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This draft is no longer active.")
        return flow


class CancelAddWordsFlowUseCase:
    def __init__(self, flow_repository: AddWordsFlowRepository) -> None:
        self._flow_repository = flow_repository

    @logged_service_call(
        "CancelAddWordsFlowUseCase.execute",
        include=("user_id",),
    )
    def execute(self, *, user_id: int) -> None:
        self._flow_repository.discard_active_by_user(user_id)


class SaveApprovedAddWordsDraftUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "SaveApprovedAddWordsDraftUseCase.execute",
        include=("user_id", "flow_id"),
        transforms={"output_path": lambda value: {"output_path": value}},
        result=lambda value: {
            "flow_id": value.flow_id,
            "stage": value.stage,
            "draft_output_path": value.draft_output_path,
        },
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        output_path: Path | None = None,
    ) -> AddWordsFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.save_approved_draft(flow=flow, output_path=output_path)
        self._flow_repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._flow_repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This draft is no longer active.")
        return flow


class GenerateAddWordsImagePromptsUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "GenerateAddWordsImagePromptsUseCase.execute",
        include=("user_id", "flow_id"),
        result=lambda value: {
            "flow_id": value.flow_id,
            "stage": value.stage,
            "item_count": _flow_item_count(value),
            "error_count": len(value.draft_result.validation.errors),
        },
    )
    def execute(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.generate_image_prompts(flow=flow)
        self._flow_repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._flow_repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This draft is no longer active.")
        return flow


class MarkAddWordsImageReviewStartedUseCase:
    def __init__(
        self,
        *,
        harness: AddWordsFlowHarness,
        flow_repository: AddWordsFlowRepository,
    ) -> None:
        self._harness = harness
        self._flow_repository = flow_repository

    @logged_service_call(
        "MarkAddWordsImageReviewStartedUseCase.execute",
        include=("user_id", "flow_id", "image_review_flow_id"),
        result=lambda value: {
            "flow_id": value.flow_id,
            "stage": value.stage,
        },
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        image_review_flow_id: str,
    ) -> AddWordsFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.mark_image_review_started(
            flow=flow,
            image_review_flow_id=image_review_flow_id,
        )
        self._flow_repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> AddWordsFlowState:
        flow = self._flow_repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This draft is no longer active.")
        return flow
