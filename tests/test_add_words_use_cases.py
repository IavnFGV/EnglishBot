from pathlib import Path

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    GenerateAddWordsImagePromptsUseCase,
    GetActiveAddWordsFlowUseCase,
    RegenerateAddWordsDraftUseCase,
    SaveApprovedAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import FakeLessonExtractionClient
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository


class FakeImagePromptEnricher:
    def enrich(
        self,
        *,
        topic_title: str,  # noqa: ARG002
        vocabulary_items: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        enriched: list[dict[str, object]] = []
        for item in vocabulary_items:
            updated = dict(item)
            updated["image_prompt"] = f"Prompt for {item['english_word']}"
            enriched.append(updated)
        return enriched


def _pipeline() -> LessonImportPipeline:
    return LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(
            LessonExtractionDraft(
                topic_title="Fairy Tales",
                lesson_title=None,
                vocabulary_items=[
                    ExtractedVocabularyItemDraft(
                        item_id="princess",
                        english_word="Princess",
                        translation="принцесса",
                        source_fragment="Princess — принцесса",
                    ),
                    ExtractedVocabularyItemDraft(
                        item_id="prince",
                        english_word="Prince",
                        translation="принц",
                        source_fragment="Prince — принц",
                    ),
                ],
            )
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=FakeImagePromptEnricher(),  # type: ignore[arg-type]
    )


def _harness() -> AddWordsFlowHarness:
    return AddWordsFlowHarness(
        pipeline=_pipeline(),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )


def test_add_words_use_cases_support_extract_and_edit() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = _harness()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    get_active = GetActiveAddWordsFlowUseCase(repository)
    apply_edit = ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=7, raw_text="messy fairy tale text")

    assert flow.editor_user_id == 7
    assert get_active.execute(user_id=7) is not None
    assert [item.english_word for item in flow.draft_result.draft.vocabulary_items] == [
        "Princess",
        "Prince",
    ]

    updated = apply_edit.execute(
        user_id=7,
        flow_id=flow.flow_id,
        edited_text=(
            "Topic: Fairy Tales\n"
            "Lesson: Royal Family\n\n"
            "Princess: принцесса\n"
            "Queen: королева\n"
        ),
    )

    assert updated.draft_result.draft.lesson_title == "Royal Family"
    assert [item.english_word for item in updated.draft_result.draft.vocabulary_items] == [
        "Princess",
        "Queen",
    ]
    assert [item.translation for item in updated.draft_result.draft.vocabulary_items] == [
        "принцесса",
        "королева",
    ]
    assert updated.raw_text.startswith("Topic: Fairy Tales\nLesson: Royal Family")
    assert flow.draft_result.draft.vocabulary_items[0].image_prompt is None


def test_start_add_words_does_not_persist_malformed_extraction_result() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=LessonImportPipeline(
            extraction_client=FakeLessonExtractionClient({"error": "timeout"}),
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
        ),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    get_active = GetActiveAddWordsFlowUseCase(repository)

    flow = start.execute(user_id=7, raw_text="broken teacher text")

    assert isinstance(flow.draft_result.draft, dict)
    assert flow.draft_result.validation.is_valid is False
    assert flow.draft_result.validation.errors[0].code == "malformed_result"
    assert get_active.execute(user_id=7) is None


def test_regenerate_uses_edited_text_as_new_source() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=LessonImportPipeline(
            extraction_client=FakeLessonExtractionClient(
                LessonExtractionDraft(
                    topic_title="Fairy Tales",
                    lesson_title=None,
                    vocabulary_items=[
                        ExtractedVocabularyItemDraft(
                            english_word="Dragon",
                            translation="дракон",
                            source_fragment="Dragon — дракон",
                        )
                    ],
                )
            ),
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
            image_prompt_enricher=FakeImagePromptEnricher(),  # type: ignore[arg-type]
        ),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    apply_edit = ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository)
    regenerate = RegenerateAddWordsDraftUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=7, raw_text="messy fairy tale text")
    updated = apply_edit.execute(
        user_id=7,
        flow_id=flow.flow_id,
        edited_text=(
            "Topic: Fairy Tales\n"
            "Lesson: Royal Family\n\n"
            "Dragon: дракон\n"
        ),
    )
    regenerated = regenerate.execute(user_id=7, flow_id=flow.flow_id)

    assert updated.raw_text.startswith("Topic: Fairy Tales\nLesson: Royal Family")
    assert regenerated.raw_text == updated.raw_text


def test_add_words_use_cases_can_approve_and_write_content_pack(tmp_path: Path) -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = _harness()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    approve = ApproveAddWordsDraftUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=8, raw_text="messy fairy tale text")
    output_path = tmp_path / "fairy-tales.json"
    approved = approve.execute(user_id=8, flow_id=flow.flow_id, output_path=output_path)

    assert approved.published_topic_id == "fairy-tales"
    assert approved.output_path == output_path
    assert output_path.exists()
    assert repository.get_active_by_user(8) is None


def test_add_words_use_cases_can_save_draft_then_generate_image_prompts(tmp_path: Path) -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = _harness()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    save_approved_draft = SaveApprovedAddWordsDraftUseCase(
        harness=harness,
        flow_repository=repository,
    )
    generate_image_prompts = GenerateAddWordsImagePromptsUseCase(
        harness=harness,
        flow_repository=repository,
    )

    flow = start.execute(user_id=8, raw_text="messy fairy tale text")
    draft_path = tmp_path / "fairy-tales.draft.json"
    saved_flow = save_approved_draft.execute(
        user_id=8,
        flow_id=flow.flow_id,
        output_path=draft_path,
    )
    prompts_flow = generate_image_prompts.execute(user_id=8, flow_id=flow.flow_id)

    assert saved_flow.stage == "draft_saved"
    assert saved_flow.draft_output_path == draft_path
    assert draft_path.exists()
    assert prompts_flow.stage == "prompts_generated"
    assert [item.image_prompt for item in prompts_flow.draft_result.draft.vocabulary_items] == [
        "Prompt for Princess",
        "Prompt for Prince",
    ]
