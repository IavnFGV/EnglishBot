from englishbot.domain.models import Lesson, Topic, VocabularyItem

TOPICS = [
    Topic(id="weather", title="Weather"),
    Topic(id="school", title="School"),
    Topic(id="seasons", title="Seasons"),
]

LESSONS = [
    Lesson(id="weather-1", title="Weather Lesson 1", topic_id="weather"),
    Lesson(id="school-1", title="School Lesson 1", topic_id="school"),
    Lesson(id="seasons-1", title="Seasons Lesson 1", topic_id="seasons"),
]

VOCABULARY_ITEMS = [
    VocabularyItem(
        id="weather-sun",
        english_word="sun",
        translation="солнце",
        topic_id="weather",
        lesson_id="weather-1",
        image_ref="bright yellow sun",
    ),
    VocabularyItem(
        id="weather-rain",
        english_word="rain",
        translation="дождь",
        topic_id="weather",
        lesson_id="weather-1",
        image_ref="cloud with rain drops",
    ),
    VocabularyItem(
        id="weather-cloud",
        english_word="cloud",
        translation="облако",
        topic_id="weather",
        lesson_id="weather-1",
        image_ref="white cloud",
    ),
    VocabularyItem(
        id="weather-wind",
        english_word="wind",
        translation="ветер",
        topic_id="weather",
        lesson_id="weather-1",
        image_ref="windy sky",
    ),
    VocabularyItem(
        id="school-book",
        english_word="book",
        translation="книга",
        topic_id="school",
        lesson_id="school-1",
        image_ref="open school book",
    ),
    VocabularyItem(
        id="school-pencil",
        english_word="pencil",
        translation="карандаш",
        topic_id="school",
        lesson_id="school-1",
        image_ref="yellow pencil",
    ),
    VocabularyItem(
        id="school-desk",
        english_word="desk",
        translation="парта",
        topic_id="school",
        lesson_id="school-1",
        image_ref="classroom desk",
    ),
    VocabularyItem(
        id="school-bag",
        english_word="bag",
        translation="рюкзак",
        topic_id="school",
        lesson_id="school-1",
        image_ref="school bag",
    ),
    VocabularyItem(
        id="seasons-spring",
        english_word="spring",
        translation="весна",
        topic_id="seasons",
        lesson_id="seasons-1",
        image_ref="flowers in spring",
    ),
    VocabularyItem(
        id="seasons-summer",
        english_word="summer",
        translation="лето",
        topic_id="seasons",
        lesson_id="seasons-1",
        image_ref="bright summer day",
    ),
    VocabularyItem(
        id="seasons-autumn",
        english_word="autumn",
        translation="осень",
        topic_id="seasons",
        lesson_id="seasons-1",
        image_ref="orange autumn leaves",
    ),
    VocabularyItem(
        id="seasons-winter",
        english_word="winter",
        translation="зима",
        topic_id="seasons",
        lesson_id="seasons-1",
        image_ref="snowy winter scene",
    ),
]
