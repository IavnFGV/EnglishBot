import os
from pathlib import Path

import pytest

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import StartAddWordsFlowUseCase
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository
from tests.support.add_words_scenarios import FAIRY_TALES_ITEMS, FAIRY_TALES_LESSON_TEXT
from tests.support.app_harness import AppHarness, build_import_draft

_BIRTHDAY_CELEBRATION_TEXT = """Birtday celebration

Birthday boy / Birthday girl — именинник / именинница.

Birthday cake — торт ко дню рождения.
Candles — свечи.

Balloons — воздушные шары.
Presents / Gifts — подарки.

Card — открытка.

To celebrate — праздновать.
"""


def test_beta_reproduction_editor_imports_reviews_publishes_and_learns_fairy_tales(
    tmp_path: Path,
) -> None:
    app = AppHarness(
        content_dir=tmp_path,
        import_drafts=[
            build_import_draft(
                topic_title="Fairy Tales",
                items=FAIRY_TALES_ITEMS,
            )
        ],
    )

    app.when_editor_imports_teacher_text(raw_text=FAIRY_TALES_LESSON_TEXT)

    assert app.flow is not None
    assert app.flow.raw_text == FAIRY_TALES_LESSON_TEXT
    assert app.flow.draft_result.validation.is_valid is True
    assert len(app.flow.draft_result.draft.vocabulary_items) == 20
    assert app.last_import_preview == (
        "Draft preview\n"
        "Topic: Fairy Tales\n"
        "Lesson: -\n"
        "Items: 20\n"
        "1. Princess — принцесса\n"
        "2. Prince — принц\n"
        "3. Castle — замок\n"
        "4. King — король\n"
        "5. Queen — королева\n"
        "6. Dragon — дракон\n"
        "7. Fairy — фея\n"
        "8. Wizard — волшебник\n"
        "9. Mermaid — русалка\n"
        "10. Giant — великан\n"
        "11. Magic lamp — магическая лампа\n"
        "12. Jinn — джинн\n"
        "13. Ghost — привидение\n"
        "14. Dwarf — гномик\n"
        "15. Troll — тролль\n"
        "16. Ogre — огр (великан)\n"
        "17. Werewolf — оборотень\n"
        "18. Magic potion — волшебный эликсир\n"
        "19. Monster — чудовище\n"
        "20. Elf — эльф"
    )

    app.when_editor_edits_import_draft(
        edited_text=(
            "Topic: Fairy Tales\n"
            "Lesson: Story Creatures\n\n"
            "Princess: принцесса\n"
            "Prince: принц\n"
            "Castle: замок\n"
            "King: король\n"
            "Queen: королева\n"
            "Dragon: дракон\n"
            "Fairy: фея\n"
            "Wizard: волшебник\n"
            "Mermaid: русалка\n"
            "Giant: великан\n"
            "Magic lamp: магическая лампа\n"
            "Jinn: джинн\n"
            "Ghost: привидение\n"
            "Dwarf: гномик\n"
            "Troll: тролль\n"
            "Ogre: огр\n"
            "Werewolf: оборотень\n"
            "Magic potion: волшебный эликсир\n"
            "Monster: чудовище\n"
            "Elf: эльф\n"
        )
    )

    assert app.flow is not None
    assert app.flow.draft_result.validation.is_valid is True
    assert app.flow.draft_result.draft.lesson_title == "Story Creatures"
    assert app.flow.draft_result.draft.vocabulary_items[15].translation == "огр"

    output_path = tmp_path / "fairy-tales.json"
    app.when_editor_approves_import(output_path=output_path)

    assert app.approval is not None
    assert output_path.exists()
    assert app.approval.output_path == output_path

    app.when_learning_content_is_reloaded(include_default_content=True)
    app.when_user_starts_learning().when_user_selects_topic("fairy-tales")

    assert app.screen is not None
    assert app.screen.kind == "lesson_menu"
    assert app.screen.text == "Choose a lesson or train all words from the topic."
    assert [action.label for action in app.screen.actions] == [
        "All Topic Words",
        "Story Creatures",
    ]


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes"},
    reason="Set RUN_OLLAMA_INTEGRATION_TESTS=1 to run against a live Ollama instance.",
)
def test_beta_reproduction_real_ollama_extracts_fairy_tales_input_without_validation_errors(
    tmp_path: Path,
) -> None:
    '''
    sh command
    RUN_OLLAMA_INTEGRATION_TESTS=1 python -m pytest -q tests/test_beta_reproduction_scenarios.py -k real_ollama -s -o log_cli=true --log-cli-level=DEBUG

    '''
    
    pipeline = LessonImportPipeline(
        extraction_client=OllamaLessonExtractionClient(
            model=os.getenv("OLLAMA_MODEL") or None,
            base_url=os.getenv("OLLAMA_BASE_URL") or None,
            timeout=int(os.getenv("OLLAMA_TIMEOUT_SEC", "120")),
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )
    harness = AddWordsFlowHarness(
        pipeline=pipeline,
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
        custom_content_dir=tmp_path,
    )
    start_use_case = StartAddWordsFlowUseCase(
        harness=harness,
        flow_repository=InMemoryAddWordsFlowRepository(),
    )

    flow = start_use_case.execute(user_id=100, raw_text=FAIRY_TALES_LESSON_TEXT)

    assert flow.raw_text == FAIRY_TALES_LESSON_TEXT
    assert flow.draft_result.validation.is_valid is True
    assert len(flow.draft_result.validation.errors) == 0
    assert len(flow.draft_result.draft.vocabulary_items) == 20
    assert [item.english_word for item in flow.draft_result.draft.vocabulary_items[:5]] == [
        "Princess",
        "Prince",
        "Castle",
        "King",
        "Queen",
    ]


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes"},
    reason="Set RUN_OLLAMA_INTEGRATION_TESTS=1 to run against a live Ollama instance.",
)
def test_beta_reproduction_real_ollama_keeps_birthday_import_flow_working(
    tmp_path: Path,
) -> None:
    """
    sh command
    RUN_OLLAMA_INTEGRATION_TESTS=1 python -m pytest -q tests/test_beta_reproduction_scenarios.py -k birthday_import_flow -s -o log_cli=true --log-cli-level=DEBUG

    """

    pipeline = LessonImportPipeline(
        extraction_client=OllamaLessonExtractionClient(
            model=os.getenv("OLLAMA_MODEL") or None,
            base_url=os.getenv("OLLAMA_BASE_URL") or None,
            timeout=int(os.getenv("OLLAMA_TIMEOUT_SEC", "120")),
        ),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
    )

    output_path = tmp_path / "birthday-celebration.json"
    result = pipeline.run(raw_text=_BIRTHDAY_CELEBRATION_TEXT, output_path=output_path)

    assert result.validation.is_valid is True
    assert len(result.validation.errors) == 0
    assert result.canonicalization is not None
    assert output_path.exists()
    assert result.draft.unparsed_lines == []

    words = [item.english_word.strip() for item in result.draft.vocabulary_items]
    normalized_words = {word.lower() for word in words}

    assert "birthday boy" in normalized_words
    assert "birthday girl" in normalized_words
    assert "birthday cake" in normalized_words
    assert "candles" in normalized_words
    assert "balloons" in normalized_words
    assert "card" in normalized_words
    assert "to celebrate" in normalized_words

    assert len(words) >= 8

    items_by_word = {
        item.english_word.strip().lower(): item.translation.strip()
        for item in result.draft.vocabulary_items
    }
    assert items_by_word["birthday cake"] == "торт ко дню рождения"
    assert items_by_word["candles"] == "свечи"
    assert items_by_word["balloons"] == "воздушные шары"
    assert items_by_word["card"] == "открытка"
    assert items_by_word["to celebrate"] == "праздновать"
