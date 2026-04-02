from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import FakeLessonExtractionClient, OllamaLessonExtractionClient
from englishbot.importing.fallback_parser import TemplateLessonFallbackParser
from englishbot.importing.draft_io import JsonDraftReader
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.models import (
    AICapabilityAvailability,
    ExtractedVocabularyItemDraft,
    LessonExtractionDraft,
    SmartParseInvalidResponse,
    SmartParseSuccess,
    SmartParseTimeout,
    SmartParseUnavailable,
)
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.smart_parsing import SmartLessonParsingGateway
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter


def build_pipeline(draft: LessonExtractionDraft | object) -> LessonImportPipeline:
    return LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(draft),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )


class _FakeSmartParser(SmartLessonParsingGateway):
    def __init__(self, result) -> None:
        self._result = result

    def check_availability(self) -> AICapabilityAvailability:
        return AICapabilityAvailability(is_available=True)

    def parse(self, *, raw_text: str):  # noqa: ARG002
        return self._result


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


def test_cyrillic_characters_in_english_word_are_rejected() -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Рrincess",
                translation="принцесса",
                source_fragment="Рrincess - принцесса",
            ),
        ],
    )
    result = build_pipeline(draft).run(raw_text="cyrillic typo")

    assert result.validation.is_valid is False
    assert any(error.code == "cyrillic_in_english_word" for error in result.validation.errors)


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
    assert result.validation.errors[0].code == "empty_vocabulary_items"
    assert result.canonicalization is None
    assert result.extraction_metadata is not None
    assert result.extraction_metadata.parse_path == "fallback"
    assert result.extraction_metadata.smart_parse_status == "invalid_response"


def test_smart_parse_success_path_marks_metadata() -> None:
    draft = LessonExtractionDraft(
        topic_title="Weather",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Sun",
                translation="солнце",
                source_fragment="Sun — солнце",
            )
        ],
    )
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseSuccess(draft=draft)),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(raw_text="Sun — солнце")

    assert result.validation.is_valid is True
    assert result.extraction_metadata is not None
    assert result.extraction_metadata.parse_path == "smart"
    assert result.extraction_metadata.smart_parse_status == "success"


def test_ai_unavailable_falls_back_to_template_parse() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="health check failed")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(raw_text="Fairy Tales\n\nDragon — дракон")

    assert result.validation.is_valid is True
    assert [item.english_word for item in result.draft.vocabulary_items] == ["Dragon"]
    assert result.extraction_metadata is not None
    assert result.extraction_metadata.parse_path == "fallback"
    assert result.extraction_metadata.smart_parse_status == "unavailable"
    assert "Smart parsing is currently unavailable." in result.extraction_metadata.status_messages[0]


def test_ai_unavailable_fallback_strips_leading_numbers_from_initial_raw_input() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="health check failed")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(raw_text="Birthday\n\n1. Birthday boy — именинник")

    assert result.validation.is_valid is True
    assert [item.english_word for item in result.draft.vocabulary_items] == ["Birthday boy"]
    assert [item.translation for item in result.draft.vocabulary_items] == ["именинник"]
    assert [item.source_fragment for item in result.draft.vocabulary_items] == [
        "Birthday boy — именинник"
    ]


def test_ai_unavailable_fallback_splits_slash_synonyms_in_preview_draft() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="health check failed")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(raw_text="Birthday\n\nPresents / Gifts — подарки.")

    assert result.validation.is_valid is True
    assert [item.english_word for item in result.draft.vocabulary_items] == [
        "Presents",
        "Gifts",
    ]
    assert [item.translation for item in result.draft.vocabulary_items] == [
        "подарки",
        "подарки",
    ]


def test_ai_unavailable_fallback_splits_aligned_slash_pairs_in_preview_draft() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="health check failed")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(
        raw_text="Birthday\n\nBirthday boy / Birthday girl — именинник / именинница."
    )

    assert result.validation.is_valid is True
    assert [item.english_word for item in result.draft.vocabulary_items] == [
        "Birthday boy",
        "Birthday girl",
    ]
    assert [item.translation for item in result.draft.vocabulary_items] == [
        "именинник",
        "именинница",
    ]


def test_ai_unavailable_fallback_parses_parentheses_style_teacher_dictionary_lines() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="health check failed")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(
        raw_text=(
            "Character Traits\n\n"
            "kind (добрый),\n"
            "shy (застенчивый),\n"
            "friendly (дружелюбный),\n"
            "lazy (ленивый),\n"
            "smart (умный),\n"
            "funny (смешной),\n"
            "honest (честный)."
        )
    )

    assert result.validation.is_valid is True
    assert [item.english_word for item in result.draft.vocabulary_items] == [
        "kind",
        "shy",
        "friendly",
        "lazy",
        "smart",
        "funny",
        "honest",
    ]
    assert [item.translation for item in result.draft.vocabulary_items] == [
        "добрый",
        "застенчивый",
        "дружелюбный",
        "ленивый",
        "умный",
        "смешной",
        "честный",
    ]


def test_ai_unavailable_fallback_parses_multiple_parentheses_pairs_in_one_line() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="health check failed")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(
        raw_text="Character Traits\n\nkind (добрый), shy (застенчивый), friendly (дружелюбный)."
    )

    assert result.validation.is_valid is True
    assert [item.english_word for item in result.draft.vocabulary_items] == [
        "kind",
        "shy",
        "friendly",
    ]
    assert [item.translation for item in result.draft.vocabulary_items] == [
        "добрый",
        "застенчивый",
        "дружелюбный",
    ]


def test_ai_timeout_falls_back_and_marks_partial_result() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseTimeout(detail="read timeout")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(
        raw_text="Fairy Tales\n\nDragon — дракон\n?? mystery line"
    )

    assert result.validation.is_valid is True
    assert result.extraction_metadata is not None
    assert result.extraction_metadata.parse_path == "fallback"
    assert result.extraction_metadata.smart_parse_status == "timeout"
    assert result.extraction_metadata.fallback_is_partial is True
    assert result.draft.unparsed_lines == ["?? mystery line"]
    assert any("partial result" in warning.lower() for warning in result.draft.warnings)


def test_ai_invalid_response_falls_back_with_warnings() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseInvalidResponse(detail="bad json")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(raw_text="Topic: Fairy Tales\n\nDragon: дракон")

    assert result.validation.is_valid is True
    assert result.extraction_metadata is not None
    assert result.extraction_metadata.smart_parse_status == "invalid_response"
    assert "simpler template-based parse" in result.draft.warnings[0]


def test_fallback_partial_parse_keeps_unparsed_lines_and_validation_error_when_no_items() -> None:
    pipeline = LessonImportPipeline(
        smart_parser=_FakeSmartParser(SmartParseUnavailable(detail="offline")),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.extract_draft(raw_text="Fairy Tales\n\nсовсем непонятный текст")

    assert result.validation.is_valid is False
    assert [error.code for error in result.validation.errors] == ["empty_vocabulary_items"]
    assert result.draft.unparsed_lines == ["совсем непонятный текст"]


def test_extract_draft_writes_editable_json(tmp_path: Path) -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Dragon",
                translation="дракон",
                source_fragment="Dragon — дракон",
                image_prompt="A friendly dragon.",
            )
        ],
    )
    output_path = tmp_path / "fairy-draft.json"
    result = build_pipeline(draft).extract_draft(
        raw_text="Dragon — дракон",
        output_path=output_path,
    )

    assert result.validation.is_valid is True
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["topic_title"] == "Fairy Tales"
    assert data["vocabulary_items"][0]["english_word"] == "Dragon"
    assert data["vocabulary_items"][0]["image_prompt"] == "A friendly dragon."


def test_finalize_reviewed_draft_allows_manual_add_and_remove(tmp_path: Path) -> None:
    reviewed_draft_path = tmp_path / "reviewed.json"
    reviewed_draft_path.write_text(
        json.dumps(
            {
                "topic_title": "Fairy Tales",
                "lesson_title": None,
                "vocabulary_items": [
                    {
                        "english_word": "Castle",
                        "translation": "замок",
                        "source_fragment": "Castle — замок",
                        "image_prompt": "A big stone castle.",
                    },
                    {
                        "english_word": "Elf",
                        "translation": "эльф",
                        "source_fragment": "Elf — эльф",
                        "notes": "Added by human reviewer",
                    },
                ],
                "warnings": [],
                "unparsed_lines": [],
                "confidence_notes": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "final.json"
    pipeline = LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(
            LessonExtractionDraft(topic_title="", vocabulary_items=[])
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.finalize_draft_from_file(
        input_path=reviewed_draft_path,
        output_path=output_path,
    )

    assert result.validation.is_valid is True
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert [item["english_word"] for item in data["vocabulary_items"]] == ["Castle", "Elf"]
    assert data["vocabulary_items"][1]["notes"] == "Added by human reviewer"


def test_finalize_reviewed_draft_returns_field_errors_for_broken_manual_edit() -> None:
    reader = JsonDraftReader()
    reviewed_draft = reader.read_data(
        {
            "topic_title": "Fairy Tales",
            "vocabulary_items": [
                {
                    "english_word": "Dragon",
                    "translation": "",
                    "source_fragment": "Dragon — дракон",
                }
            ],
        }
    )
    pipeline = LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(
            LessonExtractionDraft(topic_title="", vocabulary_items=[])
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    result = pipeline.finalize_draft(draft=reviewed_draft)

    assert result.validation.is_valid is False
    assert any(error.code == "empty_translation" for error in result.validation.errors)


def test_ollama_extraction_client_builds_draft_from_http_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "topic_title": "Fairy Tales",
                            "lesson_title": None,
                            "vocabulary_items": [
                                {
                                    "english_word": "Princess / Prince",
                                    "translation": "принцесса / принц",
                                    "notes": None,
                                    "image_prompt": "storybook prince and princess",
                                    "source_fragment": "Princess / Prince — принцесса / принц",
                                }
                            ],
                            "warnings": [],
                            "unparsed_lines": [],
                            "confidence_notes": ["high confidence"],
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "qwen2.5:7b"
            assert timeout == 120
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    draft = client.extract("Fairy Tales\n\nPrincess / Prince — принцесса / принц")
    assert isinstance(draft, LessonExtractionDraft)
    assert draft.topic_title == "Fairy Tales"
    assert len(draft.vocabulary_items) == 2
    assert draft.vocabulary_items[0].english_word == "Princess"
    assert draft.vocabulary_items[0].translation == "принцесса"
    assert draft.vocabulary_items[0].source_fragment == "Princess — принцесса"
    assert draft.vocabulary_items[1].english_word == "Prince"
    assert draft.vocabulary_items[1].translation == "принц"
    assert draft.vocabulary_items[1].source_fragment == "Prince — принц"
    assert draft.vocabulary_items[0].image_prompt is None


def test_ollama_extraction_client_repairs_half_paired_item_from_source_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "topic_title": "Fairy Tales",
                            "lesson_title": None,
                            "vocabulary_items": [
                                {
                                    "english_word": "King",
                                    "translation": "король / королева",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "King / Queen — король / королева",
                                }
                            ],
                            "warnings": [],
                            "unparsed_lines": [],
                            "confidence_notes": [],
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "qwen2.5:7b"
            assert timeout == 120
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    draft = client.extract("Fairy Tales\n\nKing / Queen — король / королева")

    assert isinstance(draft, LessonExtractionDraft)
    assert [item.english_word for item in draft.vocabulary_items] == ["King", "Queen"]
    assert [item.translation for item in draft.vocabulary_items] == ["король", "королева"]


def test_ollama_extraction_client_does_not_duplicate_already_split_pair_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_text = (
        "Fairy Tales\n\n"
        "Рrincess / Prince — принцесса / принц\n"
        "Castle — замок\n"
        "King / Queen — король / королева\n"
        "Dragon — дракон\n"
        "Fairy — фея\n"
        "Wizard — волшебник\n"
        "Mermaid — русалка\n"
        "Giant — великан\n"
        "Magic lamp — магическая лампа\n"
        "Jinn — джинн\n"
        "Ghost — привидение\n"
        "Dwarf — гномик\n"
        "Troll — тролль\n"
        "Ogre — огр (великан)\n"
        "Werewolf — оборотень\n"
        "Magic potion — волшебный эликсир\n"
        "Monster — чудовище\n"
        "Elf — эльф\n"
    )

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": self._content
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "qwen2.5:7b"
            assert timeout == 120
            source_line = json["messages"][-1]["content"]
            dumps = __import__("json").dumps
            if source_line == "Рrincess / Prince — принцесса / принц":
                return FakeResponse(
                    dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Princess",
                                    "translation": "принцесса",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                                {
                                    "english_word": "Prince",
                                    "translation": "принц",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                            ]
                        }
                    )
                )
            if source_line == "King / Queen — король / королева":
                return FakeResponse(
                    dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "King",
                                    "translation": "король",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                                {
                                    "english_word": "Queen",
                                    "translation": "королева",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                            ]
                        }
                    )
                )
            english_word, translation = [
                part.strip() for part in source_line.split("—", maxsplit=1)
            ]
            return FakeResponse(
                dumps(
                    {
                        "vocabulary_items": [
                            {
                                "english_word": english_word,
                                "translation": translation,
                                "notes": None,
                                "image_prompt": None,
                                "source_fragment": source_line,
                            }
                        ]
                    }
                )
            )

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert len(draft.vocabulary_items) == 20
    assert [item.english_word for item in draft.vocabulary_items[:5]] == [
        "Princess",
        "Prince",
        "Castle",
        "King",
        "Queen",
    ]
    assert [item.english_word for item in draft.vocabulary_items].count("King") == 1
    assert [item.english_word for item in draft.vocabulary_items].count("Queen") == 1
    assert [item.english_word for item in draft.vocabulary_items].count("Prince") == 1


def test_ollama_extraction_client_does_not_duplicate_already_split_pair_items_with_periods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_text = (
        "Birtday celebration\n\n"
        "Birthday boy / Birthday girl — именинник / именинница.\n"
    )
    source_line = "Birthday boy / Birthday girl — именинник / именинница."

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Birthday boy",
                                    "translation": "именинник",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                                {
                                    "english_word": "Birthday girl",
                                    "translation": "именинница",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["messages"][-1]["content"] == source_line
            assert timeout == 120
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert [item.english_word for item in draft.vocabulary_items] == [
        "Birthday boy",
        "Birthday girl",
    ]
    assert [item.translation for item in draft.vocabulary_items] == [
        "именинник",
        "именинница",
    ]


def test_ollama_extraction_client_parses_birthday_celebration_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_text = (
        "Birtday celebration\n\n"
        "Birthday boy / Birthday girl — именинник / именинница.\n\n"
        "Birthday cake — торт ко дню рождения.\n"
        "Candles — свечи.\n\n"
        "Balloons — воздушные шары.\n"
        "Presents / Gifts — подарки.\n\n"
        "Card — открытка.\n\n"
        "To celebrate — праздновать.\n"
    )

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": self._content}}

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "qwen2.5:7b"
            assert timeout == 120
            source_line = json["messages"][-1]["content"]
            dumps = __import__("json").dumps
            if "/" in source_line:
                english_word, translation = [
                    part.strip().rstrip(".")
                    for part in source_line.split("—", maxsplit=1)
                ]
                return FakeResponse(
                    dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": english_word,
                                    "translation": translation,
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                }
                            ]
                        }
                    )
                )
            english_word, translation = [
                part.strip().rstrip(".")
                for part in source_line.split("—", maxsplit=1)
            ]
            return FakeResponse(
                dumps(
                    {
                        "vocabulary_items": [
                            {
                                "english_word": english_word,
                                "translation": translation,
                                "notes": None,
                                "image_prompt": None,
                                "source_fragment": source_line.rstrip("."),
                            }
                        ]
                    }
                )
            )

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert draft.topic_title == "Birtday celebration"
    assert draft.unparsed_lines == []
    assert len(draft.vocabulary_items) == 8
    assert [item.english_word for item in draft.vocabulary_items] == [
        "Birthday boy",
        "Birthday girl",
        "Birthday cake",
        "Candles",
        "Balloons",
        "Presents / Gifts",
        "Card",
        "To celebrate",
    ]
    assert [item.translation for item in draft.vocabulary_items] == [
        "именинник",
        "именинница",
        "торт ко дню рождения",
        "свечи",
        "воздушные шары",
        "подарки",
        "открытка",
        "праздновать",
    ]


def test_ollama_extraction_client_full_text_mode_uses_single_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_text = (
        "Birthday celebration\n\n"
        "Birthday boy / Birthday girl — именинник / именинница.\n"
        "Birthday cake — торт ко дню рождения.\n"
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Birthday boy",
                                    "translation": "именинник",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Birthday boy / Birthday girl — именинник / именинница.",
                                },
                                {
                                    "english_word": "Birthday girl",
                                    "translation": "именинница",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Birthday boy / Birthday girl — именинник / именинница.",
                                },
                                {
                                    "english_word": "Birthday cake",
                                    "translation": "торт ко дню рождения",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Birthday cake — торт ко дню рождения.",
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        call_count = 0

        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            FakeRequestsModule.call_count += 1
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "qwen2.5:7b"
            assert json["messages"][-1]["content"] == raw_text
            assert "You extract vocabulary items from teacher-written lesson text." in json["messages"][0]["content"]
            assert timeout == 120
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        extraction_mode="full_text",
    )

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert FakeRequestsModule.call_count == 1
    assert draft.topic_title == "Birthday celebration"
    assert [item.english_word for item in draft.vocabulary_items] == [
        "Birthday boy",
        "Birthday girl",
        "Birthday cake",
    ]


def test_ollama_extraction_client_reloads_model_name_from_file_between_requests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "ollama_model.txt"
    model_path.write_text("qwen3.5:4b", encoding="utf-8")
    seen_models: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Pencil",
                                    "translation": "карандаш",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pencil — карандаш",
                                }
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:  # noqa: ARG004
            seen_models.append(str(json["model"]))
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(
        model="fallback-model",
        model_file_path=model_path,
        base_url="http://127.0.0.1:11434",
        extraction_mode="full_text",
    )

    raw_text = "School supplies\n\nPencil — карандаш"
    first = client.extract(raw_text)
    model_path.write_text("qwen3.5:8b", encoding="utf-8")
    second = client.extract(raw_text)

    assert isinstance(first, LessonExtractionDraft)
    assert isinstance(second, LessonExtractionDraft)
    assert seen_models == ["qwen3.5:4b", "qwen3.5:8b"]


def test_ollama_extraction_client_logs_full_text_metrics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_text = "School supplies\n\nPencil — карандаш\nPen — ручка"

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Pencil",
                                    "translation": "карандаш",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pencil — карандаш",
                                },
                                {
                                    "english_word": "Pen",
                                    "translation": "ручка",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pen — ручка",
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:  # noqa: ARG004
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    caplog.set_level(logging.INFO, logger="englishbot.importing.clients")
    client = OllamaLessonExtractionClient(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        extraction_mode="full_text",
    )

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert (
        "OllamaLessonExtractionClient metrics mode=full_text request_count=1 "
        "source_line_count=2 parsed_line_count=2 unparsed_line_count=0 raw_item_count=2 "
        "final_item_count=2 infer_topic_requested=false"
    ) in caplog.text


def test_ollama_extraction_client_logs_line_by_line_metrics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_text = "Pencil — карандаш\nPen — ручка"

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": self._content}}

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:  # noqa: ARG004
            source_line = json["messages"][-1]["content"]
            if source_line.startswith("Extracted words:"):
                return FakeResponse("School supplies")
            english_word, translation = [part.strip() for part in source_line.split("—", maxsplit=1)]
            return FakeResponse(
                json_module.dumps(
                    {
                        "vocabulary_items": [
                            {
                                "english_word": english_word,
                                "translation": translation,
                                "notes": None,
                                "image_prompt": None,
                                "source_fragment": source_line,
                            }
                        ]
                    }
                )
            )

    json_module = json
    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    caplog.set_level(logging.INFO, logger="englishbot.importing.clients")
    client = OllamaLessonExtractionClient(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        extraction_mode="line_by_line",
    )

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert (
        "OllamaLessonExtractionClient metrics mode=line_by_line request_count=3 "
        "source_line_count=2 parsed_line_count=2 unparsed_line_count=0 raw_item_count=none "
        "final_item_count=2 infer_topic_requested=true"
    ) in caplog.text


def test_ollama_extraction_client_writes_trace_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_text = "School supplies\n\nPencil — карандаш\nPen — ручка"
    trace_path = tmp_path / "ollama_extraction.jsonl"

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Pencil",
                                    "translation": "карандаш",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pencil — карандаш",
                                },
                                {
                                    "english_word": "Pen",
                                    "translation": "ручка",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pen — ручка",
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:  # noqa: ARG004
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        extraction_mode="full_text",
        trace_file_path=trace_path,
    )

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(events) == 1
    assert events[0]["kind"] == "ollama_extraction"
    assert events[0]["success"] is True
    assert events[0]["mode"] == "full_text"
    assert events[0]["request_count"] == 1
    assert events[0]["source_line_count"] == 2
    assert events[0]["final_item_count"] == 2
    assert events[0]["resolved_model"] == "qwen2.5:7b"
    assert events[0]["prompt_path"] == "None"
    assert events[0]["model_output_items"] == [
        {
            "english_word": "Pencil",
            "translation": "карандаш",
            "source_fragment": "Pencil — карандаш",
            "item_id": None,
            "notes": None,
            "image_prompt": None,
        },
        {
            "english_word": "Pen",
            "translation": "ручка",
            "source_fragment": "Pen — ручка",
            "item_id": None,
            "notes": None,
            "image_prompt": None,
        },
    ]
    assert events[0]["normalized_items"] == [
        {
            "english_word": "Pencil",
            "translation": "карандаш",
            "source_fragment": "Pencil — карандаш",
            "item_id": None,
            "notes": None,
            "image_prompt": None,
        },
        {
            "english_word": "Pen",
            "translation": "ручка",
            "source_fragment": "Pen — ручка",
            "item_id": None,
            "notes": None,
            "image_prompt": None,
        },
    ]


def test_ollama_extraction_client_writes_trace_event_on_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_text = "Pencil — карандаш"
    trace_path = tmp_path / "ollama_extraction.jsonl"

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> None:  # noqa: ARG004
            raise TimeoutError("timed out")

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        extraction_mode="full_text",
        trace_file_path=trace_path,
    )

    result = client.extract(raw_text)

    assert result == {"error": "timed out"}
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(events) == 1
    assert events[0]["success"] is False
    assert events[0]["error_type"] == "TimeoutError"
    assert events[0]["error"] == "timed out"
    assert events[0]["mode"] == "full_text"


def test_ollama_extraction_client_repairs_translation_from_source_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "topic_title": "Fairy Tales",
                            "lesson_title": None,
                            "vocabulary_items": [
                                {
                                    "english_word": "Dwarf",
                                    "translation": "gnomik",
                                    "notes": None,
                                    "image_prompt": "small dwarf in a cave",
                                    "source_fragment": "Dwarf — гномик",
                                }
                            ],
                            "warnings": [],
                            "unparsed_lines": [],
                            "confidence_notes": [],
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    draft = client.extract("Dwarf — гномик")
    assert isinstance(draft, LessonExtractionDraft)
    assert draft.vocabulary_items[0].translation == "гномик"
    assert draft.vocabulary_items[0].image_prompt is None


def test_ollama_extraction_client_recovers_malformed_paired_source_fragment_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_text = "School Supplies\n\nPupil / Student — ученик"

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Pupil",
                                    "translation": "ученик /think",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pupil / Student — ученик /think",
                                },
                                {
                                    "english_word": "Student",
                                    "translation": "ученик /think",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "Pupil / Student — ученик /think",
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:  # noqa: ARG004
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        extraction_mode="full_text",
    )

    draft = client.extract(raw_text)

    assert isinstance(draft, LessonExtractionDraft)
    assert [item.english_word for item in draft.vocabulary_items] == ["Pupil", "Student"]
    assert [item.translation for item in draft.vocabulary_items] == ["ученик", "ученик"]
    assert all(item.source_fragment == "Pupil / Student — ученик" for item in draft.vocabulary_items)


def test_ollama_extraction_client_recovers_missing_source_fragment_from_raw_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "topic_title": "Fairy Tales",
                            "lesson_title": None,
                            "vocabulary_items": [
                                {
                                    "english_word": "Castle",
                                    "translation": "замок",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "",
                                }
                            ],
                            "warnings": [],
                            "unparsed_lines": [],
                            "confidence_notes": [],
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    draft = client.extract("Fairy Tales\n\nCastle — замок")
    assert isinstance(draft, LessonExtractionDraft)
    assert draft.vocabulary_items[0].source_fragment == "Castle — замок"


def test_ollama_extraction_client_recovers_source_fragment_before_translation_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "topic_title": "Fairy Tales",
                            "lesson_title": None,
                            "vocabulary_items": [
                                {
                                    "english_word": "Dwarf",
                                    "translation": "gnomik",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": "",
                                }
                            ],
                            "warnings": [],
                            "unparsed_lines": [],
                            "confidence_notes": [],
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    draft = client.extract("Fairy Tales\n\nDwarf — гномик")
    assert isinstance(draft, LessonExtractionDraft)
    assert draft.vocabulary_items[0].source_fragment == "Dwarf — гномик"
    assert draft.vocabulary_items[0].translation == "гномик"


def test_ollama_extraction_client_accepts_parentheses_style_multi_pair_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_line = "kind (добрый), shy (застенчивый), friendly (дружелюбный)"

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "kind",
                                    "translation": "добрый",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                                {
                                    "english_word": "shy",
                                    "translation": "застенчивый",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                                {
                                    "english_word": "friendly",
                                    "translation": "дружелюбный",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["messages"][-1]["content"] == source_line
            assert timeout == 120
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")

    draft = client.extract(f"Character traits\n\n{source_line}")

    assert isinstance(draft, LessonExtractionDraft)
    assert draft.topic_title == "Character traits"
    assert draft.unparsed_lines == []
    assert [item.english_word for item in draft.vocabulary_items] == [
        "kind",
        "shy",
        "friendly",
    ]
    assert [item.translation for item in draft.vocabulary_items] == [
        "добрый",
        "застенчивый",
        "дружелюбный",
    ]


def test_ollama_extraction_client_uses_bracketed_first_line_as_explicit_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_line = "kind (добрый), shy (застенчивый)"

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "kind",
                                    "translation": "добрый",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                                {
                                    "english_word": "shy",
                                    "translation": "застенчивый",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": source_line,
                                },
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert json["messages"][-1]["content"] == source_line
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")

    draft = client.extract(f"[Character Traits]\n{source_line}")

    assert isinstance(draft, LessonExtractionDraft)
    assert draft.topic_title == "Character Traits"
    assert [item.english_word for item in draft.vocabulary_items] == ["kind", "shy"]


def test_ollama_extraction_client_infers_topic_when_first_line_is_not_explicit_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_line = "kind (добрый), shy (застенчивый)"
    second_line = "friendly (дружелюбный), honest (честный)"

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": self._content}}

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            user_content = json["messages"][-1]["content"]
            assert timeout == 120
            if user_content == first_line:
                return FakeResponse(
                    json_module.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "kind",
                                    "translation": "добрый",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": first_line,
                                },
                                {
                                    "english_word": "shy",
                                    "translation": "застенчивый",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": first_line,
                                },
                            ]
                        }
                    )
                )
            if user_content == second_line:
                return FakeResponse(
                    json_module.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "friendly",
                                    "translation": "дружелюбный",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": second_line,
                                },
                                {
                                    "english_word": "honest",
                                    "translation": "честный",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": second_line,
                                },
                            ]
                        }
                    )
                )
            assert "Extracted words:" in user_content
            return FakeResponse("Character Traits")

    json_module = json
    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")

    draft = client.extract(f"{first_line}\n{second_line}")

    assert isinstance(draft, LessonExtractionDraft)
    assert draft.topic_title == "Character Traits"
    assert [item.english_word for item in draft.vocabulary_items] == [
        "kind",
        "shy",
        "friendly",
        "honest",
    ]


def test_ollama_extraction_client_treats_empty_object_line_response_as_unparsed_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = [
        "Mathematics математика/maths",
        "Science естественные науки",
        "English английский язык",
        "History история",
    ]

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": self._content}}

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            user_content = json["messages"][-1]["content"]
            if user_content == lines[0]:
                return FakeResponse(
                    json_module.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Mathematics",
                                    "translation": "математика",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": lines[0],
                                },
                                {
                                    "english_word": "maths",
                                    "translation": "математика",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": lines[0],
                                },
                            ]
                        }
                    )
                )
            if user_content == lines[1]:
                return FakeResponse(
                    json_module.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "Science",
                                    "translation": "естественные науки",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": lines[1],
                                }
                            ]
                        }
                    )
                )
            if user_content == lines[2]:
                return FakeResponse("{}")
            if user_content == lines[3]:
                return FakeResponse(
                    json_module.dumps(
                        {
                            "vocabulary_items": [
                                {
                                    "english_word": "History",
                                    "translation": "история",
                                    "notes": None,
                                    "image_prompt": None,
                                    "source_fragment": lines[3],
                                }
                            ]
                        }
                    )
                )
            assert "Extracted words:" in user_content
            return FakeResponse("School Subjects")

    json_module = json
    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")

    draft = client.extract("\n".join(lines))

    assert isinstance(draft, LessonExtractionDraft)
    assert draft.topic_title == "School Subjects"
    assert [item.english_word for item in draft.vocabulary_items] == [
        "Mathematics",
        "maths",
        "Science",
        "History",
    ]
    assert draft.unparsed_lines == ["English английский язык"]


def test_pipeline_can_enrich_image_prompts_per_item(tmp_path: Path) -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Dragon",
                translation="дракон",
                source_fragment="Dragon — дракон",
            ),
            ExtractedVocabularyItemDraft(
                english_word="Fairy",
                translation="фея",
                source_fragment="Fairy — фея",
            ),
        ],
    )

    class FakeEnricher:
        def enrich(
            self,
            *,
            topic_title: str,
            vocabulary_items: list[dict[str, object]],
        ) -> list[dict[str, object]]:
            assert topic_title == "Fairy Tales"
            enriched = []
            for item in vocabulary_items:
                updated = dict(item)
                updated["image_prompt"] = f"Prompt for {item['english_word']}"
                enriched.append(updated)
            return enriched

    output_path = tmp_path / "fairy.json"
    pipeline = LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(draft),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=FakeEnricher(),  # type: ignore[arg-type]
    )
    result = pipeline.run(
        raw_text="fairy tale words",
        output_path=output_path,
        enrich_image_prompts=True,
    )
    assert result.canonicalization is not None
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["vocabulary_items"][0]["image_prompt"] == "Prompt for Dragon"
    assert data["vocabulary_items"][1]["image_prompt"] == "Prompt for Fairy"


def test_extract_draft_writes_intermediate_parsed_output_before_enrichment(
    tmp_path: Path,
) -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Dragon",
                translation="дракон",
                source_fragment="Dragon — дракон",
            )
        ],
    )

    class FakeEnricher:
        def enrich(
            self,
            *,
            topic_title: str,
            vocabulary_items: list[dict[str, object]],
        ) -> list[dict[str, object]]:
            updated = dict(vocabulary_items[0])
            updated["image_prompt"] = "Prompt for Dragon"
            return [updated]

    output_path = tmp_path / "fairy-tales.draft.json"
    parsed_output_path = tmp_path / "fairy-tales.draft.parsed.json"
    pipeline = LessonImportPipeline(
        extraction_client=FakeLessonExtractionClient(draft),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=FakeEnricher(),  # type: ignore[arg-type]
    )

    result = pipeline.extract_draft(
        raw_text="fairy tale words",
        output_path=output_path,
        intermediate_output_path=parsed_output_path,
        enrich_image_prompts=True,
    )

    assert result.validation.is_valid is True
    parsed_data = json.loads(parsed_output_path.read_text(encoding="utf-8"))
    final_data = json.loads(output_path.read_text(encoding="utf-8"))
    assert parsed_data["vocabulary_items"][0]["image_prompt"] is None
    assert final_data["vocabulary_items"][0]["image_prompt"] == "Prompt for Dragon"


def test_ollama_image_prompt_enricher_builds_prompts_from_http_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "image_prompts": [
                                {
                                    "id": "fairy-tales-dragon",
                                    "english_word": "Dragon",
                                    "translation": "дракон",
                                    "image_prompt": "A friendly dragon beside a castle.",
                                }
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "qwen2.5:7b"
            system_prompt = json["messages"][0]["content"]
            assert "children's vocabulary flashcard app" in system_prompt
            assert "One object only." in system_prompt
            assert "White background only." in system_prompt
            assert (
                "simple cartoon style, centered, white background, colorful, no text"
                in system_prompt
            )
            assert "Input: king." in system_prompt
            assert "Input: dragon." in system_prompt
            assert "TASK: Generate the prompt." in system_prompt
            assert "INPUT WORD:" in system_prompt
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )
    enriched = enricher.enrich(
        topic_title="Fairy Tales",
        vocabulary_items=[
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
                "image_ref": None,
            }
        ],
    )
    assert enriched[0]["image_prompt"] == "A friendly dragon beside a castle."


def test_ollama_image_prompt_enricher_falls_back_to_english_word_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "items": [
                                {
                                    "word": "Dwarf",
                                    "description": "A cheerful dwarf with a lantern.",
                                }
                            ]
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )
    enriched = enricher.enrich(
        topic_title="Fairy Tales",
        vocabulary_items=[
            {
                "id": "fairy-tales-dwarf",
                "english_word": "Dwarf",
                "translation": "гномик",
                "image_ref": None,
            }
        ],
    )
    assert enriched[0]["image_prompt"] == "A cheerful dwarf with a lantern."


def test_ollama_image_prompt_enricher_accepts_plain_text_prompt_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": (
                        "cute children's flashcard illustration of a green dragon, "
                        "simple cartoon style, centered, white background, colorful, no text"
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )
    enriched = enricher.enrich(
        topic_title="Fairy Tales",
        vocabulary_items=[
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
                "image_ref": None,
            }
        ],
    )
    assert (
        enriched[0]["image_prompt"]
        == "cute children's flashcard illustration of a green dragon, "
        "simple cartoon style, centered, white background, colorful, no text"
    )


def test_ollama_image_prompt_enricher_accepts_single_json_object_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "image_prompt": (
                                "cute children's flashcard illustration of a green dragon, "
                                "simple cartoon style, centered, white background, "
                                "colorful, no text"
                            )
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )
    enriched = enricher.enrich(
        topic_title="Fairy Tales",
        vocabulary_items=[
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
                "image_ref": None,
            }
        ],
    )
    assert (
        enriched[0]["image_prompt"]
        == "cute children's flashcard illustration of a green dragon, "
        "simple cartoon style, centered, white background, colorful, no text"
    )


def test_ollama_image_prompt_enricher_accepts_object_under_image_prompts_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "image_prompts": {
                                "image_prompt": (
                                    "cute children's flashcard illustration of a green dragon, "
                                    "simple cartoon style, centered, white background, "
                                    "colorful, no text"
                                )
                            }
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )
    enriched = enricher.enrich(
        topic_title="Fairy Tales",
        vocabulary_items=[
            {
                "id": "fairy-tales-dragon",
                "english_word": "Dragon",
                "translation": "дракон",
                "image_ref": None,
            }
        ],
    )
    assert (
        enriched[0]["image_prompt"]
        == "cute children's flashcard illustration of a green dragon, "
        "simple cartoon style, centered, white background, colorful, no text"
    )


def test_ollama_image_prompt_enricher_accepts_result_prompt_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "result_prompt": (
                                "simple cartoon illustration of a closed book, centered, "
                                "white background, bright colors, no text"
                            )
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )
    enriched = enricher.enrich(
        topic_title="School Supplies",
        vocabulary_items=[
            {
                "id": "school-supplies-book",
                "english_word": "Book",
                "translation": "книга",
            }
        ],
    )
    assert (
        enriched[0]["image_prompt"]
        == "simple cartoon illustration of a closed book, centered, "
        "white background, bright colors, no text"
    )


def test_ollama_image_prompt_enricher_logs_full_request_and_response_payloads(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "result_prompt": (
                                "simple cartoon illustration of a human king with a golden crown, "
                                "centered, white background, bright colors, no text"
                            )
                        }
                    )
                }
            }

    class FakeRequestsModule:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    caplog.set_level(logging.DEBUG, logger="englishbot.importing.enrichment")
    enricher = OllamaImagePromptEnricher(
        model="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
    )

    enriched = enricher.enrich(
        topic_title="Fairy Tales",
        vocabulary_items=[
            {
                "id": "fairy-tales-king",
                "english_word": "King",
                "translation": "король",
            }
        ],
    )

    assert enriched[0]["image_prompt"].startswith("simple cartoon illustration of a human king")
    assert "request payload system_prompt=" in caplog.text
    assert '"english_word": "King"' in caplog.text
    assert "response english_word=King" in caplog.text
    assert "result_prompt" in caplog.text


def test_canonicalizer_splits_slash_synonyms_into_separate_vocabulary_items() -> None:
    result = DraftToContentPackCanonicalizer().convert(
        LessonExtractionDraft(
            topic_title="School Things",
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    item_id="eraser-rubber",
                    english_word="Eraser / Rubber",
                    translation="ластик",
                    source_fragment="Eraser / Rubber — ластик",
                )
            ],
        )
    )

    assert result.content_pack.data["vocabulary_items"] == [
        {
            "id": "eraser-rubber-eraser",
            "english_word": "Eraser",
            "translation": "ластик",
            "image_ref": None,
            "source_fragment": "Eraser / Rubber — ластик",
        },
        {
            "id": "eraser-rubber-rubber",
            "english_word": "Rubber",
            "translation": "ластик",
            "image_ref": None,
            "source_fragment": "Eraser / Rubber — ластик",
        },
    ]
