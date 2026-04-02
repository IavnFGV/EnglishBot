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
from englishbot.importing.fallback_parser import TemplateLessonFallbackParser
from englishbot.importing.models import (
    AICapabilityAvailability,
    ExtractedVocabularyItemDraft,
    LessonExtractionDraft,
    SmartParseTimeout,
    SmartParseUnavailable,
)
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.smart_parsing import SmartLessonParsingGateway
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


class _FakeSmartParser(SmartLessonParsingGateway):
    def __init__(self, result) -> None:
        self._result = result

    def check_availability(self) -> AICapabilityAvailability:
        return AICapabilityAvailability(is_available=not isinstance(self._result, SmartParseUnavailable))

    def parse(self, *, raw_text: str):  # noqa: ARG002
        return self._result


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


def test_add_words_edit_splits_slash_synonyms_into_separate_draft_items() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = _harness()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    apply_edit = ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=7, raw_text="messy birthday text")
    updated = apply_edit.execute(
        user_id=7,
        flow_id=flow.flow_id,
        edited_text=(
            "Topic: Birthday Celebration\n"
            "Lesson: -\n\n"
            "Presents / Gifts: подарки\n"
        ),
    )

    assert [item.english_word for item in updated.draft_result.draft.vocabulary_items] == [
        "Presents",
        "Gifts",
    ]
    assert [item.translation for item in updated.draft_result.draft.vocabulary_items] == [
        "подарки",
        "подарки",
    ]


def test_add_words_edit_splits_aligned_slash_pairs_into_two_items() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = _harness()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    apply_edit = ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=7, raw_text="messy birthday text")
    updated = apply_edit.execute(
        user_id=7,
        flow_id=flow.flow_id,
        edited_text=(
            "Topic: Birthday Celebration\n"
            "Lesson: -\n\n"
            "Birthday boy / Birthday girl: именинник / именинница\n"
        ),
    )

    assert [item.english_word for item in updated.draft_result.draft.vocabulary_items] == [
        "Birthday boy",
        "Birthday girl",
    ]
    assert [item.translation for item in updated.draft_result.draft.vocabulary_items] == [
        "именинник",
        "именинница",
    ]


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

    assert isinstance(flow.draft_result.draft, LessonExtractionDraft)
    assert flow.draft_result.validation.is_valid is False
    assert flow.draft_result.validation.errors[0].code == "empty_vocabulary_items"
    assert flow.draft_result.extraction_metadata is not None
    assert flow.draft_result.extraction_metadata.smart_parse_status == "timeout"
    assert get_active.execute(user_id=7) is not None


def test_start_add_words_persists_fallback_draft_when_ai_is_unavailable() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=LessonImportPipeline(
            smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="offline")),
            fallback_parser=TemplateLessonFallbackParser(),
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
        ),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    get_active = GetActiveAddWordsFlowUseCase(repository)

    flow = start.execute(user_id=7, raw_text="Fairy Tales\n\nDragon — дракон")

    assert flow.draft_result.validation.is_valid is True
    assert flow.draft_result.extraction_metadata is not None
    assert flow.draft_result.extraction_metadata.parse_path == "fallback"
    assert [item.english_word for item in flow.draft_result.draft.vocabulary_items] == ["Dragon"]
    assert get_active.execute(user_id=7) is not None


def test_start_add_words_fallback_preview_splits_slash_synonyms_when_ai_is_unavailable() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=LessonImportPipeline(
            smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="offline")),
            fallback_parser=TemplateLessonFallbackParser(),
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
        ),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=7, raw_text="Birthday\n\nPresents / Gifts — подарки.")

    assert [item.english_word for item in flow.draft_result.draft.vocabulary_items] == [
        "Presents",
        "Gifts",
    ]
    assert [item.translation for item in flow.draft_result.draft.vocabulary_items] == [
        "подарки",
        "подарки",
    ]


def test_add_words_edit_rejects_cyrillic_letters_in_english_word() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = _harness()
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)
    apply_edit = ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(user_id=7, raw_text="messy fairy tale text")
    updated = apply_edit.execute(
        user_id=7,
        flow_id=flow.flow_id,
        edited_text=(
            "Topic: Fairy Tales\n"
            "Lesson: -\n\n"
            "Рrincess: принцесса\n"
        ),
    )

    assert updated.draft_result.validation.is_valid is False
    assert any(
        error.code == "cyrillic_in_english_word"
        for error in updated.draft_result.validation.errors
    )


def test_start_add_words_fallback_preview_parses_parentheses_style_teacher_dictionary() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=LessonImportPipeline(
            smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="offline")),
            fallback_parser=TemplateLessonFallbackParser(),
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
        ),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(
        user_id=7,
        raw_text=(
            "Character Traits\n\n"
            "kind (добрый), shy (застенчивый), friendly (дружелюбный), honest (честный)."
        ),
    )

    assert [item.english_word for item in flow.draft_result.draft.vocabulary_items] == [
        "kind",
        "shy",
        "friendly",
        "honest",
    ]
    assert [item.translation for item in flow.draft_result.draft.vocabulary_items] == [
        "добрый",
        "застенчивый",
        "дружелюбный",
        "честный",
    ]


def test_start_add_words_keeps_partial_fallback_result_after_timeout() -> None:
    repository = InMemoryAddWordsFlowRepository()
    harness = AddWordsFlowHarness(
        pipeline=LessonImportPipeline(
            smart_parser=_FakeSmartParser(SmartParseTimeout(detail="read timeout")),
            fallback_parser=TemplateLessonFallbackParser(),
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
        ),
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
    )
    start = StartAddWordsFlowUseCase(harness=harness, flow_repository=repository)

    flow = start.execute(
        user_id=7,
        raw_text="Fairy Tales\n\nDragon — дракон\nсовсем непонятная строка",
    )

    assert flow.draft_result.validation.is_valid is True
    assert flow.draft_result.extraction_metadata is not None
    assert flow.draft_result.extraction_metadata.smart_parse_status == "timeout"
    assert flow.draft_result.draft.unparsed_lines == ["совсем непонятная строка"]


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
