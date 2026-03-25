from __future__ import annotations

import json
from pathlib import Path

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import FakeLessonExtractionClient
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter


def build_pipeline(draft: LessonExtractionDraft | object) -> LessonImportPipeline:
    return LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(draft),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )


def test_valid_extracted_draft_becomes_canonical_content_pack(tmp_path: Path) -> None:
    draft = LessonExtractionDraft(
        topic_title="Weather",
        lesson_title="Lesson 1",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word=" Sun ",
                translation=" солнце ",
                notes="common weather word",
                image_prompt="bright yellow sun",
                source_fragment="Sun - солнце",
            )
        ],
        warnings=["Needs teacher review"],
    )
    output_path = tmp_path / "weather.json"
    result = build_pipeline(draft).run(raw_text="messy teacher text", output_path=output_path)

    assert result.validation.is_valid is True
    assert result.canonicalization is not None
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["topic"]["id"] == "weather"
    assert data["lessons"][0]["id"] == "weather-lesson-1"
    assert data["vocabulary_items"][0]["id"] == "weather-sun"
    assert data["vocabulary_items"][0]["translation"] == "солнце"
    assert data["vocabulary_items"][0]["notes"] == "common weather word"
    assert data["vocabulary_items"][0]["image_prompt"] == "bright yellow sun"
    assert data["vocabulary_items"][0]["source_fragment"] == "Sun - солнце"
    assert data["vocabulary_items"][0]["image_ref"] is None


def test_validation_failures_are_returned_structurally() -> None:
    draft = LessonExtractionDraft(
        topic_title="",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="",
                translation="",
                source_fragment="",
            )
        ],
    )
    result = build_pipeline(draft).run(raw_text="bad draft")
    assert result.validation.is_valid is False
    assert {error.code for error in result.validation.errors} == {
        "empty_topic_title",
        "empty_english_word",
        "empty_translation",
        "empty_source_fragment",
    }
    assert result.canonicalization is None


def test_duplicate_handling_rejects_duplicate_words() -> None:
    draft = LessonExtractionDraft(
        topic_title="Weather",
        lesson_title="Lesson 1",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Sun",
                translation="солнце",
                source_fragment="Sun - солнце",
            ),
            ExtractedVocabularyItemDraft(
                english_word=" sun ",
                translation="солнышко",
                source_fragment="sun - солнышко",
            ),
        ],
    )
    result = build_pipeline(draft).run(raw_text="duplicate words")
    assert result.validation.is_valid is False
    assert any(error.code == "duplicate_english_word" for error in result.validation.errors)


def test_duplicate_proposed_ids_are_rejected() -> None:
    draft = LessonExtractionDraft(
        topic_title="Weather",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                item_id="custom-id",
                english_word="sun",
                translation="солнце",
                source_fragment="Sun - солнце",
            ),
            ExtractedVocabularyItemDraft(
                item_id=" custom-id ",
                english_word="rain",
                translation="дождь",
                source_fragment="Rain - дождь",
            ),
        ],
    )
    result = build_pipeline(draft).run(raw_text="duplicate ids")
    assert result.validation.is_valid is False
    assert any(error.code == "duplicate_item_id" for error in result.validation.errors)


def test_id_generation_is_stable_and_unique() -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Magic Wand",
                translation="волшебная палочка",
                source_fragment="Magic Wand - волшебная палочка",
            ),
            ExtractedVocabularyItemDraft(
                english_word="Magic Wand!",
                translation="палочка",
                source_fragment="Magic Wand! - палочка",
                item_id="fairy-tales-magic-wand",
            ),
        ],
    )
    result = build_pipeline(draft).run(raw_text="fairy tale words")
    assert result.canonicalization is not None
    items = result.canonicalization.content_pack.data["vocabulary_items"]
    assert items[0]["id"] == "fairy-tales-magic-wand"
    assert items[1]["id"] == "fairy-tales-magic-wand-2"


def test_warning_propagation_reaches_canonical_result() -> None:
    draft = LessonExtractionDraft(
        topic_title="Weather",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="cloud",
                translation="облако",
                source_fragment="cloud - облако",
            )
        ],
        warnings=["One line was ambiguous"],
        confidence_notes=["Low confidence on translation tone"],
        unparsed_lines=["maybe storm?"],
    )
    result = build_pipeline(draft).run(raw_text="ambiguous text")
    assert result.canonicalization is not None
    assert result.canonicalization.warnings == ["One line was ambiguous"]
    metadata = result.canonicalization.content_pack.data["metadata"]
    assert metadata["draft_warnings"] == ["One line was ambiguous"]
    assert metadata["confidence_notes"] == ["Low confidence on translation tone"]
    assert metadata["unparsed_lines"] == ["maybe storm?"]


def test_malformed_extraction_results_do_not_crash_pipeline() -> None:
    result = build_pipeline({"unexpected": "shape"}).run(raw_text="broken")
    assert result.validation.is_valid is False
    assert result.validation.errors[0].code == "malformed_result"
    assert result.canonicalization is None
