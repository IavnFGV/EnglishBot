from __future__ import annotations

import json
from pathlib import Path

from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import StartPublishedWordImageEditUseCase
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryImageReviewFlowRepository
from tests.support.app_harness import FakeImageCandidateGenerator


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
    assert flow.content_pack["vocabulary_items"][0]["id"] == "dragon"
    assert flow.content_pack["vocabulary_items"][1]["id"] == "fairy"
