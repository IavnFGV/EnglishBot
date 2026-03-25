from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import FakeLessonExtractionClient, OllamaLessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader
from englishbot.importing.enrichment import OllamaImagePromptEnricher
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
            assert json["model"] == "llama3.2:3b"
            assert timeout == 120
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", FakeRequestsModule)
    client = OllamaLessonExtractionClient(model="llama3.2:3b", base_url="http://127.0.0.1:11434")
    draft = client.extract(
        "Fairy Tales\n\nPrincess / Prince — принцесса / принц\nCastle — замок"
    )
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
    draft = client.extract("Fairy Tales\n\nCastle — замок\nDragon — дракон")
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
