from __future__ import annotations

import json
from pathlib import Path

from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    GenerateImageReviewCandidatesUseCase,
    PublishImageReviewUseCase,
    SelectImageCandidateUseCase,
    StartPublishedWordImageEditUseCase,
)
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryImageReviewFlowRepository
from englishbot.domain.image_review_models import ImageCandidate


class FakeImageCandidateGenerator:
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
            filename = f"{item_id}--{model_name}.png"
            output_path = assets_dir / topic_id / "review" / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(f"{english_word}|{model_name}|{prompt}".encode())
            candidates.append(
                ImageCandidate(
                    model_name=model_name,
                    image_ref=str(output_path).replace("\\", "/"),
                    output_path=output_path,
                    prompt=prompt,
                )
            )
        return candidates


def test_start_published_word_image_edit_use_case_focuses_selected_item(
    tmp_path: Path,
) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    content_path = content_dir / "fairy-tales.json"
    content_path.write_text(
        json.dumps(
            {
                "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
                "lessons": [],
                "vocabulary_items": [
                    {
                        "id": "dragon",
                        "english_word": "Dragon",
                        "translation": "дракон",
                        "image_prompt": "a green dragon",
                        "image_ref": "assets/fairy-tales/dragon.png",
                    },
                    {
                        "id": "fairy",
                        "english_word": "Fairy",
                        "translation": "фея",
                        "image_prompt": "a tiny fairy",
                        "image_ref": "assets/fairy-tales/fairy.png",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    use_case = StartPublishedWordImageEditUseCase(
        harness=ImageReviewFlowHarness(
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
            candidate_generator=FakeImageCandidateGenerator(),
            assets_dir=tmp_path / "assets",
        ),
        repository=InMemoryImageReviewFlowRepository(),
        content_dir=content_dir,
    )

    flow = use_case.execute(user_id=7, topic_id="fairy-tales", item_id="fairy")

    assert len(flow.items) == 1
    assert flow.current_item is not None
    assert flow.current_item.item_id == "fairy"
    assert flow.current_item.english_word == "Fairy"
    assert flow.output_path == content_path
    assert flow.content_pack["vocabulary_items"][0]["id"] == "dragon"
    assert flow.content_pack["vocabulary_items"][1]["id"] == "fairy"


def test_published_word_image_edit_publishes_back_to_original_file_without_duplicate_topic_file(
    tmp_path: Path,
) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    content_path = content_dir / "fairy-tales.json"
    content_path.write_text(
        json.dumps(
            {
                "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
                "lessons": [],
                "vocabulary_items": [
                    {
                        "id": "dragon",
                        "english_word": "Dragon",
                        "translation": "дракон",
                        "image_prompt": "a green dragon",
                        "image_ref": "assets/fairy-tales/dragon.png",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    repository = InMemoryImageReviewFlowRepository()
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=FakeImageCandidateGenerator(),
        assets_dir=tmp_path / "assets",
    )
    start_use_case = StartPublishedWordImageEditUseCase(
        harness=harness,
        repository=repository,
        content_dir=content_dir,
    )
    generate_use_case = GenerateImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    select_use_case = SelectImageCandidateUseCase(
        harness=harness,
        repository=repository,
    )
    publish_use_case = PublishImageReviewUseCase(
        harness=harness,
        repository=repository,
    )

    flow = start_use_case.execute(user_id=7, topic_id="fairy-tales", item_id="dragon")
    flow = generate_use_case.execute(user_id=7, flow_id=flow.flow_id)
    flow = select_use_case.execute(
        user_id=7,
        flow_id=flow.flow_id,
        item_id="dragon",
        candidate_index=0,
    )
    published_path = publish_use_case.execute(
        user_id=7,
        flow_id=flow.flow_id,
        output_path=flow.output_path,
    )

    assert published_path == content_path
    assert not (content_dir / "fairy-tales-2.json").exists()
    saved = json.loads(content_path.read_text(encoding="utf-8"))
    assert saved["vocabulary_items"][0]["image_ref"].endswith(
        "/fairy-tales/review/dragon--dreamshaper.png"
    )
