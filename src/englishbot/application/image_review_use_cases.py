from __future__ import annotations
from pathlib import Path

from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.domain.image_review_models import ImageReviewFlowState
from englishbot.domain.repositories import ImageReviewFlowRepository
from englishbot.importing.models import LessonExtractionDraft
from englishbot.logging_utils import logged_service_call
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class StartImageReviewUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "StartImageReviewUseCase.execute",
        include=("user_id",),
        transforms={"draft": lambda value: {"item_count": len(value.vocabulary_items)}},
        result=lambda value: {"flow_id": value.flow_id, "item_count": len(value.items)},
    )
    def execute(
        self,
        *,
        user_id: int,
        draft: LessonExtractionDraft,
        model_names: tuple[str, ...] | None = None,
    ) -> ImageReviewFlowState:
        flow = self._harness.start(
            editor_user_id=user_id,
            draft=draft,
            model_names=model_names,
        )
        self._repository.save(flow)
        return flow


class StartPublishedWordImageEditUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
        db_path: Path,
    ) -> None:
        self._harness = harness
        self._repository = repository
        self._store = SQLiteContentStore(db_path=db_path)
        self._store.initialize()

    @logged_service_call(
        "StartPublishedWordImageEditUseCase.execute",
        include=("user_id", "topic_id", "item_id"),
        result=lambda value: {"flow_id": value.flow_id, "item_count": len(value.items)},
    )
    def execute(
        self,
        *,
        user_id: int,
        topic_id: str,
        item_id: str,
        model_names: tuple[str, ...] | None = None,
    ) -> ImageReviewFlowState:
        content_pack = self._store.get_content_pack(topic_id)
        flow = self._harness.start_from_content_pack(
            editor_user_id=user_id,
            content_pack=content_pack,
            model_names=model_names,
            selected_item_id=item_id,
        )
        self._repository.save(flow)
        return flow


class GenerateImageReviewCandidatesUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "GenerateImageReviewCandidatesUseCase.execute",
        include=("user_id", "flow_id"),
        result=lambda value: {
            "current_index": value.current_index,
            "candidate_count": len(value.current_item.candidates) if value.current_item else 0,
        },
    )
    def execute(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.generate_current_item_candidates(flow=flow)
        self._repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This image review flow is no longer active.")
        return flow


class GetActiveImageReviewUseCase:
    def __init__(self, repository: ImageReviewFlowRepository) -> None:
        self._repository = repository

    @logged_service_call(
        "GetActiveImageReviewUseCase.execute",
        include=("user_id",),
        result=lambda value: {
            "found": value is not None,
            "flow_id": value.flow_id if value else None,
        },
    )
    def execute(self, *, user_id: int) -> ImageReviewFlowState | None:
        return self._repository.get_active_by_user(user_id)


class SelectImageCandidateUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "SelectImageCandidateUseCase.execute",
        include=("user_id", "flow_id", "item_id", "candidate_index"),
        result=lambda value: {"current_index": value.current_index, "completed": value.completed},
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        item_id: str,
        candidate_index: int,
    ) -> ImageReviewFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.select_candidate(
            flow=flow,
            item_id=item_id,
            candidate_index=candidate_index,
        )
        self._repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This image review flow is no longer active.")
        return flow


class SkipImageReviewItemUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "SkipImageReviewItemUseCase.execute",
        include=("user_id", "flow_id", "item_id"),
        result=lambda value: {"current_index": value.current_index, "completed": value.completed},
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        item_id: str,
    ) -> ImageReviewFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.skip_item(flow=flow, item_id=item_id)
        self._repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This image review flow is no longer active.")
        return flow


class PublishImageReviewUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "PublishImageReviewUseCase.execute",
        include=("user_id", "flow_id"),
        transforms={"output_path": lambda value: {"output_path": value}},
    )
    def execute(self, *, user_id: int, flow_id: str, output_path: Path | None = None) -> Path | None:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        self._harness.publish(flow=flow, output_path=output_path)
        self._repository.discard_active_by_user(user_id)
        return output_path

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This image review flow is no longer active.")
        return flow


class UpdateImageReviewPromptUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "UpdateImageReviewPromptUseCase.execute",
        include=("user_id", "flow_id", "item_id"),
        transforms={"prompt": lambda value: {"prompt": value}},
        result=lambda value: {
            "current_index": value.current_index,
            "candidate_count": len(value.current_item.candidates) if value.current_item else 0,
        },
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        item_id: str,
        prompt: str,
    ) -> ImageReviewFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.update_current_item_prompt(
            flow=flow,
            item_id=item_id,
            prompt=prompt,
        )
        self._repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This image review flow is no longer active.")
        return flow


class AttachUploadedImageUseCase:
    def __init__(
        self,
        *,
        harness: ImageReviewFlowHarness,
        repository: ImageReviewFlowRepository,
    ) -> None:
        self._harness = harness
        self._repository = repository

    @logged_service_call(
        "AttachUploadedImageUseCase.execute",
        include=("user_id", "flow_id", "item_id", "image_ref"),
        transforms={"output_path": lambda value: {"output_path": value}},
        result=lambda value: {"current_index": value.current_index, "completed": value.completed},
    )
    def execute(
        self,
        *,
        user_id: int,
        flow_id: str,
        item_id: str,
        image_ref: str,
        output_path: Path,
    ) -> ImageReviewFlowState:
        flow = self._require_active_flow(user_id=user_id, flow_id=flow_id)
        updated = self._harness.attach_uploaded_image(
            flow=flow,
            item_id=item_id,
            image_ref=image_ref,
            output_path=output_path,
        )
        self._repository.save(updated)
        return updated

    def _require_active_flow(self, *, user_id: int, flow_id: str) -> ImageReviewFlowState:
        flow = self._repository.get_active_by_user(user_id)
        if flow is None or flow.flow_id != flow_id:
            raise ValueError("This image review flow is no longer active.")
        return flow
