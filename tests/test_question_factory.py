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
