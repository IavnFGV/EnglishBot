from __future__ import annotations

from pathlib import Path

from englishbot.application.content_pack_image_use_cases import GenerateContentPackImagesUseCase
from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    AttachUploadedImageUseCase,
    CancelImageReviewFlowUseCase,
    GenerateImageReviewCandidatesUseCase,
    GetActiveImageReviewUseCase,
    LoadNextImageReviewCandidatesUseCase,
    LoadPreviousImageReviewCandidatesUseCase,
    PublishImageReviewUseCase,
    SearchImageReviewCandidatesUseCase,
    SelectImageCandidateUseCase,
    SkipImageReviewItemUseCase,
    StartImageReviewUseCase,
    StartPublishedWordImageEditUseCase,
    UpdateImageReviewPromptUseCase,
)
from englishbot.image_generation.clients import (
    ComfyUIImageGenerationClient,
    LocalPlaceholderImageGenerationClient,
)
from englishbot.image_generation.pipeline import ContentPackImageEnricher
from englishbot.image_generation.pixabay import PixabayImageSearchClient, RemoteImageDownloader
from englishbot.image_generation.resilient import ResilientImageGenerator
from englishbot.image_generation.review import ComfyUIImageCandidateGenerator
from englishbot.image_generation.smart_generation import (
    ComfyUIImageGenerationGateway,
    DisabledImageGenerationGateway,
)
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteImageReviewFlowRepository


def build_image_generation_gateway(*, settings, config_service):
    ai_images = settings.ai_images
    if not ai_images.enabled:
        return DisabledImageGenerationGateway()
    return ComfyUIImageGenerationGateway(
        ComfyUIImageGenerationClient(config_service=config_service)
    )


def build_image_review_harness(*, settings, config_service, content_store):
    ai_images = settings.ai_images
    return ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=ComfyUIImageCandidateGenerator(),
        image_search_client=(
            PixabayImageSearchClient(
                config_service=config_service,
                api_key=ai_images.pixabay_api_key,
                base_url=ai_images.pixabay_base_url,
            )
            if ai_images.pixabay_api_key
            else None
        ),
        remote_image_downloader=RemoteImageDownloader(),
        assets_dir=Path("assets"),
        content_store=content_store,
    )


def build_content_pack_image_enricher(*, settings, config_service):
    return ContentPackImageEnricher(
        ResilientImageGenerator(
            external_gateway=build_image_generation_gateway(
                settings=settings,
                config_service=config_service,
            ),
            fallback_client=LocalPlaceholderImageGenerationClient(),
        )
    )


def register_ai_image_capability(*, app, settings, config_service, content_store) -> None:
    image_generation_gateway = build_image_generation_gateway(
        settings=settings,
        config_service=config_service,
    )
    app.bot_data["image_generation_gateway"] = image_generation_gateway

    image_review_repository = SQLiteImageReviewFlowRepository(content_store)
    image_review_harness = build_image_review_harness(
        settings=settings,
        config_service=config_service,
        content_store=content_store,
    )
    app.bot_data["image_review_start_use_case"] = StartImageReviewUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_start_published_word_use_case"] = (
        StartPublishedWordImageEditUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
            db_path=settings.content_db_path,
        )
    )
    app.bot_data["image_review_get_active_use_case"] = GetActiveImageReviewUseCase(
        image_review_repository
    )
    app.bot_data["image_review_cancel_use_case"] = CancelImageReviewFlowUseCase(
        image_review_repository
    )
    app.bot_data["image_review_generate_use_case"] = GenerateImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_search_use_case"] = SearchImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_next_use_case"] = LoadNextImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_previous_use_case"] = LoadPreviousImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_select_use_case"] = SelectImageCandidateUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_skip_use_case"] = SkipImageReviewItemUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_publish_use_case"] = PublishImageReviewUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_update_prompt_use_case"] = UpdateImageReviewPromptUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_attach_uploaded_image_use_case"] = AttachUploadedImageUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    app.bot_data["image_review_assets_dir"] = Path("assets")
    app.bot_data["content_pack_generate_images_use_case"] = GenerateContentPackImagesUseCase(
        enricher=build_content_pack_image_enricher(
            settings=settings,
            config_service=config_service,
        ),
        db_path=settings.content_db_path,
    )
