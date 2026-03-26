from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from englishbot.domain.models import Lesson, SessionAnswer, SessionItem, Topic, TrainingMode, TrainingSession, UserProgress, VocabularyItem
from englishbot.infrastructure.content_loader import JsonContentPackLoader

logger = logging.getLogger(__name__)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class SQLiteContentStore:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        with _connect(self._db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS topics (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS vocabulary_items (
                    id TEXT PRIMARY KEY,
                    english_word TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                    lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL,
                    image_ref TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS user_progress (
                    user_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL REFERENCES vocabulary_items(id) ON DELETE CASCADE,
                    times_seen INTEGER NOT NULL DEFAULT 0,
                    correct_answers INTEGER NOT NULL DEFAULT 0,
                    incorrect_answers INTEGER NOT NULL DEFAULT 0,
                    last_result INTEGER,
                    last_seen_at TEXT,
                    PRIMARY KEY (user_id, item_id)
                );

                CREATE TABLE IF NOT EXISTS training_sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                    lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL,
                    mode TEXT NOT NULL,
                    current_index INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS training_session_items (
                    session_id TEXT NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL,
                    vocabulary_item_id TEXT NOT NULL REFERENCES vocabulary_items(id) ON DELETE CASCADE,
                    PRIMARY KEY (session_id, sort_order)
                );

                CREATE TABLE IF NOT EXISTS training_session_answers (
                    session_id TEXT NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL,
                    item_id TEXT NOT NULL REFERENCES vocabulary_items(id) ON DELETE CASCADE,
                    submitted_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    PRIMARY KEY (session_id, sort_order)
                );
                """
            )

    def has_runtime_content(self) -> bool:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM topics").fetchone()
        return bool(row["count"])

    def import_json_directories(self, directories: list[Path], *, replace: bool = False) -> None:
        self.initialize()
        loader = JsonContentPackLoader()
        topic_map: dict[str, Topic] = {}
        lesson_map: dict[str, Lesson] = {}
        item_map: dict[str, VocabularyItem] = {}
        for directory in directories:
            if not directory.exists():
                logger.info("Skipping missing content directory %s", directory)
                continue
            loaded = loader.load_directory(directory)
            for topic in loaded.topics:
                topic_map[topic.id] = topic
            for lesson in loaded.lessons:
                lesson_map[lesson.id] = lesson
            for item in loaded.vocabulary_items:
                item_map[item.id] = item
        with _connect(self._db_path) as connection:
            if replace:
                connection.execute("DELETE FROM training_session_answers")
                connection.execute("DELETE FROM training_session_items")
                connection.execute("DELETE FROM training_sessions")
                connection.execute("DELETE FROM user_progress")
                connection.execute("DELETE FROM vocabulary_items")
                connection.execute("DELETE FROM lessons")
                connection.execute("DELETE FROM topics")
            for topic in topic_map.values():
                connection.execute(
                    """
                    INSERT INTO topics (id, title) VALUES (?, ?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title
                    """,
                    (topic.id, topic.title),
                )
            for lesson in lesson_map.values():
                connection.execute(
                    """
                    INSERT INTO lessons (id, title, topic_id) VALUES (?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title, topic_id=excluded.topic_id
                    """,
                    (lesson.id, lesson.title, lesson.topic_id),
                )
            for sort_order, item in enumerate(item_map.values()):
                connection.execute(
                    """
                    INSERT INTO vocabulary_items (
                        id, english_word, translation, topic_id, lesson_id, image_ref, is_active, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        english_word=excluded.english_word,
                        translation=excluded.translation,
                        topic_id=excluded.topic_id,
                        lesson_id=excluded.lesson_id,
                        image_ref=excluded.image_ref,
                        is_active=excluded.is_active,
                        sort_order=excluded.sort_order
                    """,
                    (
                        item.id,
                        item.english_word,
                        item.translation,
                        item.topic_id,
                        item.lesson_id,
                        item.image_ref,
                        1 if item.is_active else 0,
                        sort_order,
                    ),
                )

    def list_topics(self) -> list[Topic]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT id, title FROM topics ORDER BY title, id"
            ).fetchall()
        return [Topic(id=row["id"], title=row["title"]) for row in rows]

    def get_topic(self, topic_id: str) -> Topic | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT id, title FROM topics WHERE id = ?",
                (topic_id,),
            ).fetchone()
        return Topic(id=row["id"], title=row["title"]) if row is not None else None

    def list_lessons_by_topic(self, topic_id: str) -> list[Lesson]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT id, title, topic_id FROM lessons WHERE topic_id = ? ORDER BY title, id",
                (topic_id,),
            ).fetchall()
        return [Lesson(id=row["id"], title=row["title"], topic_id=row["topic_id"]) for row in rows]

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT id, title, topic_id FROM lessons WHERE id = ?",
                (lesson_id,),
            ).fetchone()
        return (
            Lesson(id=row["id"], title=row["title"], topic_id=row["topic_id"])
            if row is not None
            else None
        )

    def list_vocabulary_by_topic(self, topic_id: str, lesson_id: str | None = None) -> list[VocabularyItem]:
        self.initialize()
        query = (
            "SELECT id, english_word, translation, topic_id, lesson_id, image_ref, is_active "
            "FROM vocabulary_items WHERE topic_id = ? AND is_active = 1"
        )
        params: list[object] = [topic_id]
        if lesson_id is not None:
            query += " AND lesson_id = ?"
            params.append(lesson_id)
        query += " ORDER BY english_word, id"
        with _connect(self._db_path) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_vocabulary_item(row) for row in rows]

    def list_all_vocabulary(self) -> list[VocabularyItem]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, english_word, translation, topic_id, lesson_id, image_ref, is_active
                FROM vocabulary_items
                ORDER BY english_word, id
                """
            ).fetchall()
        return [self._row_to_vocabulary_item(row) for row in rows]

    def get_vocabulary_item(self, item_id: str) -> VocabularyItem | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT id, english_word, translation, topic_id, lesson_id, image_ref, is_active
                FROM vocabulary_items
                WHERE id = ?
                """,
                (item_id,),
            ).fetchone()
        return self._row_to_vocabulary_item(row) if row is not None else None

    def list_editable_words(self, topic_id: str) -> list[tuple[str, str, str]]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, english_word, translation
                FROM vocabulary_items
                WHERE topic_id = ?
                ORDER BY sort_order, english_word, id
                """,
                (topic_id,),
            ).fetchall()
        return [(row["id"], row["english_word"], row["translation"]) for row in rows]

    def update_word(self, *, topic_id: str, item_id: str, english_word: str, translation: str) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE vocabulary_items
                SET english_word = ?, translation = ?
                WHERE id = ? AND topic_id = ?
                """,
                (english_word, translation, item_id, topic_id),
            )
        if cursor.rowcount == 0:
            raise ValueError("Vocabulary item was not found.")

    def get_content_pack(self, topic_id: str) -> dict[str, object]:
        self.initialize()
        topic = self.get_topic(topic_id)
        if topic is None:
            raise ValueError(f"Unknown topic: {topic_id}")
        lessons = self.list_lessons_by_topic(topic_id)
        items = self.list_vocabulary_by_topic(topic_id)
        return {
            "topic": {"id": topic.id, "title": topic.title},
            "lessons": [
                {"id": lesson.id, "title": lesson.title}
                for lesson in lessons
            ],
            "vocabulary_items": [
                {
                    "id": item.id,
                    "english_word": item.english_word,
                    "translation": item.translation,
                    **({"lesson_id": item.lesson_id} if item.lesson_id is not None else {}),
                    **({"image_ref": item.image_ref} if item.image_ref is not None else {}),
                }
                for item in items
            ],
        }

    def upsert_content_pack(self, content_pack: dict[str, object]) -> str:
        self.initialize()
        topic_raw = content_pack.get("topic", {})
        if not isinstance(topic_raw, dict):
            raise ValueError("Content pack topic must be an object.")
        topic_id = str(topic_raw.get("id", "")).strip()
        title = str(topic_raw.get("title", "")).strip()
        if not topic_id or not title:
            raise ValueError("Content pack topic.id and topic.title are required.")
        lessons_raw = content_pack.get("lessons", [])
        items_raw = content_pack.get("vocabulary_items", [])
        if not isinstance(lessons_raw, list) or not isinstance(items_raw, list):
            raise ValueError("Content pack lessons and vocabulary_items must be lists.")
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO topics (id, title) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title
                """,
                (topic_id, title),
            )
            connection.execute("DELETE FROM vocabulary_items WHERE topic_id = ?", (topic_id,))
            connection.execute("DELETE FROM lessons WHERE topic_id = ?", (topic_id,))
            for lesson_raw in lessons_raw:
                if not isinstance(lesson_raw, dict):
                    continue
                lesson_id = str(lesson_raw.get("id", "")).strip()
                lesson_title = str(lesson_raw.get("title", "")).strip()
                if not lesson_id or not lesson_title:
                    continue
                connection.execute(
                    "INSERT INTO lessons (id, title, topic_id) VALUES (?, ?, ?)",
                    (lesson_id, lesson_title, topic_id),
                )
            for sort_order, item_raw in enumerate(items_raw):
                if not isinstance(item_raw, dict):
                    continue
                item_id = str(item_raw.get("id", "")).strip()
                english_word = str(item_raw.get("english_word", "")).strip()
                translation = str(item_raw.get("translation", "")).strip()
                if not item_id or not english_word or not translation:
                    continue
                lesson_id = item_raw.get("lesson_id")
                if lesson_id is not None:
                    lesson_id = str(lesson_id).strip() or None
                image_ref = item_raw.get("image_ref")
                if image_ref is not None:
                    image_ref = str(image_ref).strip() or None
                connection.execute(
                    """
                    INSERT INTO vocabulary_items (
                        id, english_word, translation, topic_id, lesson_id, image_ref, is_active, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (item_id, english_word, translation, topic_id, lesson_id, image_ref, 1, sort_order),
                )
        return topic_id

    def get_progress(self, user_id: int, item_id: str) -> UserProgress | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT user_id, item_id, times_seen, correct_answers, incorrect_answers, last_result, last_seen_at
                FROM user_progress
                WHERE user_id = ? AND item_id = ?
                """,
                (user_id, item_id),
            ).fetchone()
        return self._row_to_progress(row) if row is not None else None

    def save_progress(self, progress: UserProgress) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_progress (
                    user_id, item_id, times_seen, correct_answers, incorrect_answers, last_result, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET
                    times_seen=excluded.times_seen,
                    correct_answers=excluded.correct_answers,
                    incorrect_answers=excluded.incorrect_answers,
                    last_result=excluded.last_result,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    progress.user_id,
                    progress.item_id,
                    progress.times_seen,
                    progress.correct_answers,
                    progress.incorrect_answers,
                    None if progress.last_result is None else (1 if progress.last_result else 0),
                    progress.last_seen_at.isoformat() if progress.last_seen_at is not None else None,
                ),
            )

    def list_progress_by_user(self, user_id: int) -> list[UserProgress]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id, item_id, times_seen, correct_answers, incorrect_answers, last_result, last_seen_at
                FROM user_progress
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_progress(row) for row in rows]

    def save_session(self, session: TrainingSession) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO training_sessions (
                    id, user_id, topic_id, lesson_id, mode, current_index, completed
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    topic_id=excluded.topic_id,
                    lesson_id=excluded.lesson_id,
                    mode=excluded.mode,
                    current_index=excluded.current_index,
                    completed=excluded.completed
                """,
                (
                    session.id,
                    session.user_id,
                    session.topic_id,
                    session.lesson_id,
                    session.mode.value,
                    session.current_index,
                    1 if session.completed else 0,
                ),
            )
            connection.execute("DELETE FROM training_session_items WHERE session_id = ?", (session.id,))
            connection.execute("DELETE FROM training_session_answers WHERE session_id = ?", (session.id,))
            for item in session.items:
                connection.execute(
                    """
                    INSERT INTO training_session_items (session_id, sort_order, vocabulary_item_id)
                    VALUES (?, ?, ?)
                    """,
                    (session.id, item.order, item.vocabulary_item_id),
                )
            for sort_order, answer in enumerate(session.answer_history):
                connection.execute(
                    """
                    INSERT INTO training_session_answers (session_id, sort_order, item_id, submitted_answer, is_correct)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session.id, sort_order, answer.item_id, answer.submitted_answer, 1 if answer.is_correct else 0),
                )
            if not session.completed:
                connection.execute(
                    "DELETE FROM training_sessions WHERE user_id = ? AND id != ? AND completed = 0",
                    (session.user_id, session.id),
                )

    def get_active_session_by_user(self, user_id: int) -> TrainingSession | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT id
                FROM training_sessions
                WHERE user_id = ? AND completed = 0
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self.get_session_by_id(row["id"])

    def get_session_by_id(self, session_id: str) -> TrainingSession | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            session_row = connection.execute(
                """
                SELECT id, user_id, topic_id, lesson_id, mode, current_index, completed
                FROM training_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if session_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT sort_order, vocabulary_item_id
                FROM training_session_items
                WHERE session_id = ?
                ORDER BY sort_order
                """,
                (session_id,),
            ).fetchall()
            answer_rows = connection.execute(
                """
                SELECT sort_order, item_id, submitted_answer, is_correct
                FROM training_session_answers
                WHERE session_id = ?
                ORDER BY sort_order
                """,
                (session_id,),
            ).fetchall()
        return TrainingSession(
            id=session_row["id"],
            user_id=session_row["user_id"],
            topic_id=session_row["topic_id"],
            lesson_id=session_row["lesson_id"],
            mode=TrainingMode(session_row["mode"]),
            current_index=session_row["current_index"],
            completed=bool(session_row["completed"]),
            items=[
                SessionItem(order=row["sort_order"], vocabulary_item_id=row["vocabulary_item_id"])
                for row in item_rows
            ],
            answer_history=[
                SessionAnswer(
                    item_id=row["item_id"],
                    submitted_answer=row["submitted_answer"],
                    is_correct=bool(row["is_correct"]),
                )
                for row in answer_rows
            ],
        )

    def discard_active_session_by_user(self, user_id: int) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT id FROM training_sessions WHERE user_id = ? AND completed = 0",
                (user_id,),
            ).fetchall()
            for row in rows:
                connection.execute("DELETE FROM training_sessions WHERE id = ?", (row["id"],))

    def _row_to_vocabulary_item(self, row: sqlite3.Row) -> VocabularyItem:
        return VocabularyItem(
            id=row["id"],
            english_word=row["english_word"],
            translation=row["translation"],
            topic_id=row["topic_id"],
            lesson_id=row["lesson_id"],
            image_ref=row["image_ref"],
            is_active=bool(row["is_active"]),
        )

    def _row_to_progress(self, row: sqlite3.Row) -> UserProgress:
        last_seen_at = row["last_seen_at"]
        return UserProgress(
            user_id=row["user_id"],
            item_id=row["item_id"],
            times_seen=row["times_seen"],
            correct_answers=row["correct_answers"],
            incorrect_answers=row["incorrect_answers"],
            last_result=None if row["last_result"] is None else bool(row["last_result"]),
            last_seen_at=datetime.fromisoformat(last_seen_at) if last_seen_at else None,
        )


class SQLiteTopicRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def list_topics(self) -> list[Topic]:
        return self._store.list_topics()

    def get_by_id(self, topic_id: str) -> Topic | None:
        return self._store.get_topic(topic_id)


class SQLiteLessonRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def list_by_topic(self, topic_id: str) -> list[Lesson]:
        return self._store.list_lessons_by_topic(topic_id)

    def get_by_id(self, lesson_id: str) -> Lesson | None:
        return self._store.get_lesson(lesson_id)


class SQLiteVocabularyRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def list_by_topic(self, topic_id: str, lesson_id: str | None = None) -> list[VocabularyItem]:
        return self._store.list_vocabulary_by_topic(topic_id, lesson_id)

    def list_all(self) -> list[VocabularyItem]:
        return self._store.list_all_vocabulary()

    def get_by_id(self, item_id: str) -> VocabularyItem | None:
        return self._store.get_vocabulary_item(item_id)


class SQLiteUserProgressRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def get(self, user_id: int, item_id: str) -> UserProgress | None:
        return self._store.get_progress(user_id, item_id)

    def save(self, progress: UserProgress) -> None:
        self._store.save_progress(progress)

    def list_by_user(self, user_id: int) -> list[UserProgress]:
        return self._store.list_progress_by_user(user_id)


class SQLiteSessionRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def save(self, session: TrainingSession) -> None:
        self._store.save_session(session)

    def get_active_by_user(self, user_id: int) -> TrainingSession | None:
        return self._store.get_active_session_by_user(user_id)

    def get_by_id(self, session_id: str) -> TrainingSession | None:
        return self._store.get_session_by_id(session_id)

    def discard_active_by_user(self, user_id: int) -> None:
        self._store.discard_active_session_by_user(user_id)
