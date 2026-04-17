from __future__ import annotations

import random

from englishbot.application.question_factory import QuestionFactory
from englishbot.domain.models import SessionItem, TrainingMode, TrainingSession, VocabularyItem


def test_question_factory_does_not_expose_image_filename_in_prompt() -> None:
    factory = QuestionFactory(random.Random(42))
    session = TrainingSession(
        id="session-1",
        user_id=1,
        topic_id="school",
        mode=TrainingMode.EASY,
        items=[SessionItem(order=0, vocabulary_item_id="scissors")],
    )
    item = VocabularyItem(
        id="scissors",
        english_word="Scissors",
        translation="ножницы",
        topic_id="school",
        image_ref="assets/school/scissors.png",
    )
    all_topic_items = [
        item,
        VocabularyItem(
            id="glue",
            english_word="Glue",
            translation="клей",
            topic_id="school",
        ),
        VocabularyItem(
            id="chalk",
            english_word="Chalk",
            translation="мел",
            topic_id="school",
        ),
    ]

    question = factory.create_question(
        session=session,
        item=item,
        all_topic_items=all_topic_items,
    )

    assert "assets/school/scissors.png" not in question.prompt
    assert "scissors.png" not in question.prompt
    assert "Visual clue: Image is shown above." in question.prompt


def test_question_factory_scramble_keeps_spaces_in_multiword_answer() -> None:
    factory = QuestionFactory(random.Random(7))

    scrambled = factory._scramble_word("ice cream")

    assert scrambled != "ice cream"
    assert len(scrambled) == len("ice cream")
    assert scrambled[3] == " "
    assert sorted(scrambled[:3].lower()) == sorted("ice".lower())
    assert sorted(scrambled[4:].lower()) == sorted("cream".lower())


def test_question_factory_hard_prompt_includes_first_letter_hint() -> None:
    factory = QuestionFactory(random.Random(11))
    session = TrainingSession(
        id="session-hard-1",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        ui_language="en",
        items=[SessionItem(order=0, vocabulary_item_id="sun")],
    )
    item = VocabularyItem(
        id="sun",
        english_word="Sun",
        translation="солнце",
        topic_id="weather",
        image_ref="assets/weather/sun.png",
    )

    question = factory.create_question(
        session=session,
        item=item,
        all_topic_items=[item],
    )

    assert question.mode is TrainingMode.HARD
    assert "First letter: S" in question.prompt
    assert question.letter_hint == "S"
    assert question.input_hint == "Use the first letter as a hint and type the word in English."


def test_question_factory_hard_prompt_uses_session_language() -> None:
    factory = QuestionFactory(random.Random(13))
    session = TrainingSession(
        id="session-hard-ru",
        user_id=1,
        topic_id="weather",
        mode=TrainingMode.HARD,
        ui_language="ru",
        items=[SessionItem(order=0, vocabulary_item_id="sun")],
    )
    item = VocabularyItem(
        id="sun",
        english_word="Sun",
        translation="солнце",
        topic_id="weather",
    )

    question = factory.create_question(
        session=session,
        item=item,
        all_topic_items=[item],
    )

    assert "Перевод: солнце" in question.prompt
    assert "Первая буква: S" in question.prompt
    assert question.input_hint == "Используй первую букву как подсказку и напиши слово по-английски."


def test_question_factory_masks_answer_inside_context_hint() -> None:
    factory = QuestionFactory(random.Random(17))
    session = TrainingSession(
        id="session-context-1",
        user_id=1,
        topic_id="week",
        mode=TrainingMode.HARD,
        ui_language="en",
        items=[SessionItem(order=0, vocabulary_item_id="monday")],
    )
    item = VocabularyItem(
        id="monday",
        english_word="Monday",
        translation="понедельник",
        topic_id="week",
        meaning_hint="On Monday I go to school.",
    )

    question = factory.create_question(
        session=session,
        item=item,
        all_topic_items=[item],
    )

    assert "Context hint: On ****** I go to school." in question.prompt
    assert "Context hint: On Monday I go to school." not in question.prompt
