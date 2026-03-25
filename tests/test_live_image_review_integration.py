import json
import os
from pathlib import Path

import pytest

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    GenerateAddWordsImagePromptsUseCase,
    SaveApprovedAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    GenerateImageReviewCandidatesUseCase,
    PublishImageReviewUseCase,
    SelectImageCandidateUseCase,
    StartImageReviewUseCase,
)
from englishbot.image_generation.review import ComfyUIImageCandidateGenerator
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import (
    InMemoryAddWordsFlowRepository,
    InMemoryImageReviewFlowRepository,
)

_LIVE_IMAGE_REVIEW_TEXT = """[Fantasy Mini]

Dragon — дракон
Wizard — волшебник
"""


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


@pytest.mark.skipif(
    not _enabled("RUN_IMAGE_REVIEW_INTEGRATION_TESTS"),
    reason="Set RUN_IMAGE_REVIEW_INTEGRATION_TESTS=1 to run against live Ollama and ComfyUI.",
)
def test_live_image_review_flow_extracts_prompts_generates_candidates_and_publishes(
    tmp_path: Path,
) -> None:
    """
    sh command
    RUN_IMAGE_REVIEW_INTEGRATION_TESTS=1 \
    python -m pytest -q tests/test_live_image_review_integration.py \
      -s -o log_cli=true --log-cli-level=INFO
    """

    assert Path("/opt/ComfyUI/models/checkpoints/dreamshaper_8.safetensors").exists()
    assert Path("/opt/ComfyUI/models/checkpoints/Realistic_Vision_V5.1.safetensors").exists()

    user_id = 100
    ollama_model = os.getenv("OLLAMA_MODEL") or None
    ollama_base_url = os.getenv("OLLAMA_BASE_URL") or None
    ollama_timeout = int(os.getenv("OLLAMA_TIMEOUT_SEC", "120"))
    comfyui_base_url = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")

    pipeline = LessonImportPipeline(
        extraction_client=OllamaLessonExtractionClient(
            model=ollama_model,
            base_url=ollama_base_url,
            timeout=ollama_timeout,
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=OllamaImagePromptEnricher(
            model=ollama_model,
            base_url=ollama_base_url,
            timeout=ollama_timeout,
        ),
    )
    add_words_harness = AddWordsFlowHarness(
        pipeline=pipeline,
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
        custom_content_dir=tmp_path,
    )
    add_words_repository = InMemoryAddWordsFlowRepository()
    start_add_words = StartAddWordsFlowUseCase(
        harness=add_words_harness,
        flow_repository=add_words_repository,
    )
    save_approved_draft = SaveApprovedAddWordsDraftUseCase(
        harness=add_words_harness,
        flow_repository=add_words_repository,
    )
    generate_image_prompts = GenerateAddWordsImagePromptsUseCase(
        harness=add_words_harness,
        flow_repository=add_words_repository,
    )

    flow = start_add_words.execute(user_id=user_id, raw_text=_LIVE_IMAGE_REVIEW_TEXT)

    assert flow.draft_result.validation.is_valid is True
    assert [item.english_word for item in flow.draft_result.draft.vocabulary_items] == [
        "Dragon",
        "Wizard",
    ]
    assert [item.image_prompt for item in flow.draft_result.draft.vocabulary_items] == [None, None]

    flow = save_approved_draft.execute(
        user_id=user_id,
        flow_id=flow.flow_id,
        output_path=tmp_path / "fantasy-mini.draft.json",
    )
    assert flow.stage == "draft_saved"
    assert flow.draft_output_path == tmp_path / "fantasy-mini.draft.json"
    assert flow.draft_output_path.exists()

    flow = generate_image_prompts.execute(user_id=user_id, flow_id=flow.flow_id)
    assert flow.stage == "prompts_generated"
    assert [bool(item.image_prompt) for item in flow.draft_result.draft.vocabulary_items] == [
        True,
        True,
    ]

    image_review_harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=ComfyUIImageCandidateGenerator(base_url=comfyui_base_url),
        assets_dir=tmp_path / "assets",
    )
    image_review_repository = InMemoryImageReviewFlowRepository()
    start_review = StartImageReviewUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    generate_candidates = GenerateImageReviewCandidatesUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    select_candidate = SelectImageCandidateUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )
    publish_review = PublishImageReviewUseCase(
        harness=image_review_harness,
        repository=image_review_repository,
    )

    review_flow = start_review.execute(
        user_id=user_id,
        draft=flow.draft_result.draft,
        model_names=("dreamshaper", "realistic-vision"),
    )
    assert len(review_flow.items) == 2

    review_flow = generate_candidates.execute(user_id=user_id, flow_id=review_flow.flow_id)
    first_item = review_flow.items[0]
    assert first_item.item_id == "fantasy-mini-dragon"
    assert [candidate.model_name for candidate in first_item.candidates] == [
        "dreamshaper",
        "realistic-vision",
    ]
    assert all(candidate.output_path.exists() for candidate in first_item.candidates)

    review_flow = select_candidate.execute(
        user_id=user_id,
        flow_id=review_flow.flow_id,
        item_id=first_item.item_id,
        candidate_index=0,
    )
    assert review_flow.current_index == 1

    review_flow = generate_candidates.execute(user_id=user_id, flow_id=review_flow.flow_id)
    second_item = review_flow.items[1]
    assert second_item.item_id == "fantasy-mini-wizard"
    assert [candidate.model_name for candidate in second_item.candidates] == [
        "dreamshaper",
        "realistic-vision",
    ]
    assert all(candidate.output_path.exists() for candidate in second_item.candidates)

    review_flow = select_candidate.execute(
        user_id=user_id,
        flow_id=review_flow.flow_id,
        item_id=second_item.item_id,
        candidate_index=1,
    )
    assert review_flow.completed is True

    output_path = tmp_path / "fantasy-mini.json"
    published_path = publish_review.execute(
        user_id=user_id,
        flow_id=review_flow.flow_id,
        output_path=output_path,
    )

    assert published_path == output_path
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    items_by_id = {
        item["id"]: item for item in payload["vocabulary_items"] if isinstance(item, dict)
    }
    assert items_by_id["fantasy-mini-dragon"]["image_ref"].endswith(
        "/fantasy-mini/review/fantasy-mini-dragon--dreamshaper.png"
    )
    assert items_by_id["fantasy-mini-wizard"]["image_ref"].endswith(
        "/fantasy-mini/review/fantasy-mini-wizard--realistic-vision.png"
    )
