from __future__ import annotations

import json
from pathlib import Path

from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    GenerateImageReviewCandidatesUseCase,
    LoadNextImageReviewCandidatesUseCase,
    LoadPreviousImageReviewCandidatesUseCase,
    PublishImageReviewUseCase,
    SearchImageReviewCandidatesUseCase,
    SelectImageCandidateUseCase,
    StartPublishedWordImageEditUseCase,
)
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryImageReviewFlowRepository
from englishbot.domain.image_review_models import ImageCandidate
from englishbot.image_generation.pixabay import PixabayImageResult


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


class FakePixabaySearchClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, int, int]] = []

    def search(
        self,
        *,
        english_word: str,
        query: str | None = None,
        page: int = 1,
        per_page: int = 6,
    ) -> tuple[str, list[PixabayImageResult]]:
        self.calls.append((english_word, query, page, per_page))
        normalized_query = query or english_word
        start_index = (page - 1) * per_page
        return normalized_query, [
            PixabayImageResult(
                source_id=f"{1000 + start_index + offset}",
                preview_url=f"https://cdn.example/{page}-{offset}.jpg",
                full_image_url=f"https://cdn.example/full-{page}-{offset}.jpg",
                source_page_url=f"https://pixabay.example/{page}-{offset}",
                width=640,
                height=480,
            )
            for offset in range(per_page)
        ]


class FakeRemoteImageDownloader:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, Path]] = []

    def download(self, *, url: str, output_path: Path) -> None:
        self.downloads.append((url, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(url.encode("utf-8"))


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
    from englishbot.infrastructure.sqlite_store import SQLiteContentStore

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.import_json_directories([content_dir], replace=True)
    use_case = StartPublishedWordImageEditUseCase(
        harness=ImageReviewFlowHarness(
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
            candidate_generator=FakeImageCandidateGenerator(),
            assets_dir=tmp_path / "assets",
            content_store=store,
        ),
        repository=InMemoryImageReviewFlowRepository(),
        db_path=tmp_path / "data" / "englishbot.db",
    )

    flow = use_case.execute(user_id=7, topic_id="fairy-tales", item_id="fairy")

    assert len(flow.items) == 1
    assert flow.current_item is not None
    assert flow.current_item.item_id == "fairy"
    assert flow.current_item.english_word == "Fairy"
    assert flow.output_path is None
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
    from englishbot.infrastructure.sqlite_store import SQLiteContentStore

    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.import_json_directories([content_dir], replace=True)
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=FakeImageCandidateGenerator(),
        assets_dir=tmp_path / "assets",
        content_store=store,
    )
    start_use_case = StartPublishedWordImageEditUseCase(
        harness=harness,
        repository=repository,
        db_path=tmp_path / "data" / "englishbot.db",
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

    assert published_path is None
    saved = store.get_content_pack("fairy-tales")
    assert saved["vocabulary_items"][0]["image_ref"].endswith(
        "/fairy-tales/review/dragon--dreamshaper.png"
    )


def test_pixabay_search_and_next_page_replace_candidates_and_preserve_query(
    tmp_path: Path,
) -> None:
    repository = InMemoryImageReviewFlowRepository()
    search_client = FakePixabaySearchClient()
    downloader = FakeRemoteImageDownloader()
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=FakeImageCandidateGenerator(),
        image_search_client=search_client,
        remote_image_downloader=downloader,
        assets_dir=tmp_path / "assets",
    )
    flow = harness.start_from_content_pack(
        editor_user_id=7,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "dragon", "english_word": "Dragon", "translation": "дракон"}
            ],
        },
    )
    repository.save(flow)
    search_use_case = SearchImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    next_use_case = LoadNextImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )

    searched_flow = search_use_case.execute(user_id=7, flow_id=flow.flow_id)
    assert searched_flow.current_item is not None
    assert searched_flow.current_item.candidate_source_type == "pixabay"
    assert searched_flow.current_item.search_page == 1
    assert searched_flow.current_item.search_query == "Dragon"
    assert len(searched_flow.current_item.candidates) == 6
    assert searched_flow.current_item.candidates[0].source_type == "pixabay"
    assert searched_flow.current_item.candidates[0].source_id == "1000"

    next_flow = next_use_case.execute(user_id=7, flow_id=flow.flow_id)
    assert next_flow.current_item is not None
    assert next_flow.current_item.search_page == 2
    assert next_flow.current_item.search_query == "Dragon"
    assert len(next_flow.current_item.candidates) == 6
    assert next_flow.current_item.candidates[0].source_id == "1006"
    assert downloader.downloads[0][0] == "https://cdn.example/1-0.jpg"
    assert search_client.calls == [
        ("Dragon", None, 1, 6),
        ("Dragon", "Dragon", 2, 6),
    ]


def test_pixabay_previous_page_loads_prior_candidates_and_preserves_query(
    tmp_path: Path,
) -> None:
    repository = InMemoryImageReviewFlowRepository()
    search_client = FakePixabaySearchClient()
    downloader = FakeRemoteImageDownloader()
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=FakeImageCandidateGenerator(),
        image_search_client=search_client,
        remote_image_downloader=downloader,
        assets_dir=tmp_path / "assets",
    )
    flow = harness.start_from_content_pack(
        editor_user_id=7,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "dragon", "english_word": "Dragon", "translation": "дракон"}
            ],
        },
    )
    repository.save(flow)
    search_use_case = SearchImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    next_use_case = LoadNextImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    previous_use_case = LoadPreviousImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )

    search_use_case.execute(user_id=7, flow_id=flow.flow_id)
    next_use_case.execute(user_id=7, flow_id=flow.flow_id)
    previous_flow = previous_use_case.execute(user_id=7, flow_id=flow.flow_id)

    assert previous_flow.current_item is not None
    assert previous_flow.current_item.search_page == 1
    assert previous_flow.current_item.search_query == "Dragon"
    assert len(previous_flow.current_item.candidates) == 6
    assert previous_flow.current_item.candidates[0].source_id == "1000"
    assert search_client.calls == [
        ("Dragon", None, 1, 6),
        ("Dragon", "Dragon", 2, 6),
        ("Dragon", "Dragon", 1, 6),
    ]


def test_selecting_pixabay_candidate_downloads_full_image_and_updates_image_source(
    tmp_path: Path,
) -> None:
    repository = InMemoryImageReviewFlowRepository()
    search_client = FakePixabaySearchClient()
    downloader = FakeRemoteImageDownloader()
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=FakeImageCandidateGenerator(),
        image_search_client=search_client,
        remote_image_downloader=downloader,
        assets_dir=tmp_path / "assets",
    )
    search_use_case = SearchImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    select_use_case = SelectImageCandidateUseCase(
        harness=harness,
        repository=repository,
    )
    flow = harness.start_from_content_pack(
        editor_user_id=7,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "dragon", "english_word": "Dragon", "translation": "дракон"}
            ],
        },
    )
    repository.save(flow)

    searched_flow = search_use_case.execute(user_id=7, flow_id=flow.flow_id)
    selected_flow = select_use_case.execute(
        user_id=7,
        flow_id=flow.flow_id,
        item_id="dragon",
        candidate_index=0,
    )

    assert searched_flow.current_item is not None
    assert selected_flow.completed is True
    saved_item = selected_flow.content_pack["vocabulary_items"][0]
    assert saved_item["image_ref"] == (tmp_path / "assets" / "fairy-tales" / "dragon.png").as_posix()
    assert saved_item["image_source"] == "pixabay"
    assert downloader.downloads[0][0] == "https://cdn.example/1-0.jpg"
    assert downloader.downloads[-1][0] == "https://cdn.example/full-1-0.jpg"
    assert downloader.downloads[-1][1] == tmp_path / "assets" / "fairy-tales" / "dragon.png"


def test_generation_fallback_still_works_after_pixabay_search(
    tmp_path: Path,
) -> None:
    repository = InMemoryImageReviewFlowRepository()
    harness = ImageReviewFlowHarness(
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        candidate_generator=FakeImageCandidateGenerator(),
        image_search_client=FakePixabaySearchClient(),
        remote_image_downloader=FakeRemoteImageDownloader(),
        assets_dir=tmp_path / "assets",
        default_model_names=("dreamshaper",),
    )
    search_use_case = SearchImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    generate_use_case = GenerateImageReviewCandidatesUseCase(
        harness=harness,
        repository=repository,
    )
    flow = harness.start_from_content_pack(
        editor_user_id=7,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "lessons": [],
            "vocabulary_items": [
                {"id": "dragon", "english_word": "Dragon", "translation": "дракон"}
            ],
        },
    )
    repository.save(flow)

    searched_flow = search_use_case.execute(user_id=7, flow_id=flow.flow_id)
    generated_flow = generate_use_case.execute(user_id=7, flow_id=flow.flow_id)

    assert searched_flow.current_item is not None
    assert generated_flow.current_item is not None
    assert generated_flow.current_item.candidate_source_type == "generated"
    assert generated_flow.current_item.candidates[0].model_name == "dreamshaper"
