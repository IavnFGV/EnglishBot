from __future__ import annotations

import json
import logging
import uuid
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from englishbot.domain.add_words_models import AddWordsFlowState
from englishbot.domain.image_review_models import (
    ImageCandidate,
    ImageReviewFlowState,
    ImageReviewItem,
)
from englishbot.domain.models import (
    Goal,
    GoalPeriod,
    GoalStatus,
    GoalType,
    HomeworkWordProgress,
    Lesson,
    Lexeme,
    SessionAnswer,
    SessionItem,
    Topic,
    TrainingMode,
    TrainingSession,
    UserProgress,
    VocabularyItem,
    WordStats,
)
from englishbot.infrastructure.content_loader import JsonContentPackLoader
from englishbot.importing.draft_io import JsonDraftReader, draft_to_data
from englishbot.importing.models import ImportLessonResult, ValidationError, ValidationResult
from englishbot.text_variants import split_slash_variants

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class TrackedTelegramMessage:
    flow_id: str
    chat_id: int
    message_id: int
    tag: str


@dataclass(slots=True, frozen=True)
class UserGameProfile:
    user_id: int
    total_stars: int
    current_streak_days: int
    last_played_on: str | None


@dataclass(slots=True, frozen=True)
class TelegramUserLogin:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    first_seen_at: str
    last_seen_at: str


@dataclass(slots=True, frozen=True)
class TelegramUserRoleAssignment:
    user_id: int
    role: str
    assigned_at: str


@dataclass(slots=True, frozen=True)
class TelegramAdminUser:
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    roles: tuple[str, ...]
    first_seen_at: str | None
    last_seen_at: str | None


@dataclass(slots=True, frozen=True)
class PendingTelegramNotification:
    key: str
    recipient_user_id: int
    text: str
    not_before_at: datetime
    created_at: datetime


def _optional_json_str(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"none", "null"}:
        return None
    return normalized


def _required_json_str(value: object) -> str:
    return "" if value is None else str(value)


def _normalize_headword(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    collapsed = " ".join(normalized.lower().split()).strip()
    return collapsed


def _expand_slash_synonym_items(  # noqa: PLR0913
    *,
    item_id: str,
    english_word: str,
    translation: str,
    topic_id: str | None,
    lesson_id: str | None,
    meaning_hint: str | None,
    image_ref: str | None,
    image_source: str | None,
    image_prompt: str | None,
    pixabay_search_query: str | None,
    source_fragment: str | None,
    is_active: bool,
) -> list[VocabularyItem]:
    english_variants = (
        split_slash_variants(english_word)
        if "/" in english_word and "/" not in translation
        else [english_word]
    )
    if len(english_variants) <= 1:
        return [
            VocabularyItem(
                id=item_id,
                english_word=english_word,
                translation=translation,
                lexeme_id=None,
                topic_id=topic_id,
                lesson_id=lesson_id,
                meaning_hint=meaning_hint,
                image_ref=image_ref,
                image_source=image_source,
                image_prompt=image_prompt,
                pixabay_search_query=pixabay_search_query,
                source_fragment=source_fragment,
                is_active=is_active,
            )
        ]
    return [
        VocabularyItem(
            id=f"{item_id}-{_normalize_headword(variant).replace(' ', '-')}",
            english_word=variant,
            translation=translation,
            lexeme_id=None,
            topic_id=topic_id,
            lesson_id=lesson_id,
            meaning_hint=meaning_hint,
            image_ref=image_ref,
            image_source=image_source,
            image_prompt=image_prompt,
            pixabay_search_query=pixabay_search_query,
            source_fragment=source_fragment,
            is_active=is_active,
        )
        for variant in english_variants
    ]


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


class SQLiteContentStore:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        with _connect(self._db_path) as connection:
            existing_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "learning_items" not in existing_tables and "vocabulary_items" in existing_tables:
                logger.warning(
                    "Resetting legacy SQLite runtime schema at %s to initialize learning_items storage.",
                    self._db_path,
                )
                connection.executescript(
                    """
                    DROP TABLE IF EXISTS training_session_answers;
                    DROP TABLE IF EXISTS training_session_items;
                    DROP TABLE IF EXISTS training_sessions;
                    DROP TABLE IF EXISTS user_progress;
                    DROP TABLE IF EXISTS vocabulary_items;
                    DROP TABLE IF EXISTS lessons;
                    DROP TABLE IF EXISTS topics;
                    DROP TABLE IF EXISTS add_words_flows;
                    DROP TABLE IF EXISTS image_review_flows;
                    DROP TABLE IF EXISTS telegram_flow_messages;
                    """
                )
            elif "learning_items" in existing_tables and "vocabulary_items" in existing_tables:
                logger.info(
                    "Dropping legacy SQLite table vocabulary_items from %s after learning_items migration.",
                    self._db_path,
                )
                connection.execute("DROP TABLE IF EXISTS vocabulary_items")
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

                CREATE TABLE IF NOT EXISTS lexemes (
                    id TEXT PRIMARY KEY,
                    headword TEXT NOT NULL,
                    normalized_headword TEXT NOT NULL UNIQUE,
                    part_of_speech TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS learning_items (
                    id TEXT PRIMARY KEY,
                    lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
                    display_word TEXT NOT NULL,
                    display_translation TEXT NOT NULL,
                    meaning_hint TEXT,
                    image_ref TEXT,
                    image_source TEXT,
                    image_prompt TEXT,
                    pixabay_search_query TEXT,
                    source_fragment TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS topic_learning_items (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                    learning_item_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(topic_id, learning_item_id)
                );

                CREATE TABLE IF NOT EXISTS lesson_learning_items (
                    id TEXT PRIMARY KEY,
                    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    learning_item_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(lesson_id, learning_item_id)
                );

                CREATE TABLE IF NOT EXISTS user_progress (
                    user_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
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
                    source_tag TEXT,
                    mode TEXT NOT NULL,
                    current_index INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS training_session_items (
                    session_id TEXT NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL,
                    vocabulary_item_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    mode TEXT,
                    PRIMARY KEY (session_id, sort_order)
                );

                CREATE TABLE IF NOT EXISTS training_session_answers (
                    session_id TEXT NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL,
                    item_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    submitted_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    PRIMARY KEY (session_id, sort_order)
                );

                CREATE TABLE IF NOT EXISTS add_words_flows (
                    flow_id TEXT PRIMARY KEY,
                    editor_user_id INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    stage TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    validation_errors_json TEXT NOT NULL,
                    draft_output_path TEXT,
                    final_output_path TEXT,
                    image_review_flow_id TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS image_review_flows (
                    flow_id TEXT PRIMARY KEY,
                    editor_user_id INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    content_pack_json TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    current_index INTEGER NOT NULL DEFAULT 0,
                    output_path TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telegram_flow_messages (
                    flow_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (flow_id, chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS telegram_user_logins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telegram_user_roles (
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, role)
                );

                CREATE TABLE IF NOT EXISTS pending_telegram_notifications (
                    notification_key TEXT PRIMARY KEY,
                    recipient_user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    not_before_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_game_profile (
                    user_id INTEGER PRIMARY KEY,
                    total_stars INTEGER NOT NULL DEFAULT 0,
                    current_streak_days INTEGER NOT NULL DEFAULT 0,
                    last_played_on TEXT
                );

                CREATE TABLE IF NOT EXISTS user_word_stats (
                    user_id INTEGER NOT NULL,
                    word_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    attempt_easy INTEGER NOT NULL DEFAULT 0,
                    attempt_medium INTEGER NOT NULL DEFAULT 0,
                    attempt_hard INTEGER NOT NULL DEFAULT 0,
                    success_easy INTEGER NOT NULL DEFAULT 0,
                    success_medium INTEGER NOT NULL DEFAULT 0,
                    success_hard INTEGER NOT NULL DEFAULT 0,
                    last_seen_at TEXT,
                    last_correct_at TEXT,
                    current_level INTEGER NOT NULL DEFAULT 0,
                    current_streak_success INTEGER NOT NULL DEFAULT 0,
                    current_streak_fail INTEGER NOT NULL DEFAULT 0,
                    review_interval_days INTEGER NOT NULL DEFAULT 0,
                    next_review_at TEXT,
                    PRIMARY KEY (user_id, word_id)
                );

                CREATE TABLE IF NOT EXISTS user_weekly_points (
                    user_id INTEGER NOT NULL,
                    week_start_date TEXT NOT NULL,
                    points INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, week_start_date)
                );

                CREATE TABLE IF NOT EXISTS user_weekly_word_awards (
                    user_id INTEGER NOT NULL,
                    week_start_date TEXT NOT NULL,
                    word_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, week_start_date, word_id)
                );

                CREATE TABLE IF NOT EXISTS user_goals (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    goal_period TEXT NOT NULL,
                    goal_type TEXT NOT NULL,
                    target_count INTEGER NOT NULL,
                    progress_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    deadline_date TEXT,
                    reward_points INTEGER,
                    required_level INTEGER,
                    target_topic_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_goal_words (
                    goal_id TEXT NOT NULL REFERENCES user_goals(id) ON DELETE CASCADE,
                    word_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    PRIMARY KEY (goal_id, word_id)
                );

                CREATE TABLE IF NOT EXISTS user_session_word_history (
                    session_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    word_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, word_id)
                );

                CREATE TABLE IF NOT EXISTS user_homework_word_progress (
                    goal_id TEXT NOT NULL REFERENCES user_goals(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL,
                    word_id TEXT NOT NULL REFERENCES learning_items(id) ON DELETE CASCADE,
                    easy_success_count INTEGER NOT NULL DEFAULT 0,
                    medium_success_count INTEGER NOT NULL DEFAULT 0,
                    hard_success_count INTEGER NOT NULL DEFAULT 0,
                    easy_mastered INTEGER NOT NULL DEFAULT 0,
                    medium_mastered INTEGER NOT NULL DEFAULT 0,
                    hard_mastered INTEGER NOT NULL DEFAULT 0,
                    hard_skipped INTEGER NOT NULL DEFAULT 0,
                    hard_failed_streak INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (goal_id, word_id)
                );
                """
            )
            word_stats_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(user_word_stats)").fetchall()
            }
            if "review_interval_days" not in word_stats_columns:
                connection.execute("ALTER TABLE user_word_stats ADD COLUMN review_interval_days INTEGER NOT NULL DEFAULT 0")
            if "next_review_at" not in word_stats_columns:
                connection.execute("ALTER TABLE user_word_stats ADD COLUMN next_review_at TEXT")
            item_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(training_session_items)"
                ).fetchall()
            }
            if "mode" not in item_columns:
                connection.execute("ALTER TABLE training_session_items ADD COLUMN mode TEXT")
            session_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(training_sessions)").fetchall()
            }
            if "source_tag" not in session_columns:
                connection.execute("ALTER TABLE training_sessions ADD COLUMN source_tag TEXT")
            telegram_login_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(telegram_user_logins)").fetchall()
            }
            if "first_name" not in telegram_login_columns:
                connection.execute("ALTER TABLE telegram_user_logins ADD COLUMN first_name TEXT")
            if "last_name" not in telegram_login_columns:
                connection.execute("ALTER TABLE telegram_user_logins ADD COLUMN last_name TEXT")
            if "language_code" not in telegram_login_columns:
                connection.execute("ALTER TABLE telegram_user_logins ADD COLUMN language_code TEXT")

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
                for expanded_item in _expand_slash_synonym_items(
                    item_id=item.id,
                    english_word=item.english_word,
                    translation=item.translation,
                    topic_id=item.topic_id,
                    lesson_id=item.lesson_id,
                    meaning_hint=item.meaning_hint,
                    image_ref=item.image_ref,
                    image_source=item.image_source,
                    image_prompt=item.image_prompt,
                    pixabay_search_query=item.pixabay_search_query,
                    source_fragment=item.source_fragment,
                    is_active=item.is_active,
                ):
                    item_map[expanded_item.id] = expanded_item
        with _connect(self._db_path) as connection:
            if replace:
                connection.execute("DELETE FROM training_session_answers")
                connection.execute("DELETE FROM training_session_items")
                connection.execute("DELETE FROM training_sessions")
                connection.execute("DELETE FROM user_progress")
                connection.execute("DELETE FROM lesson_learning_items")
                connection.execute("DELETE FROM topic_learning_items")
                connection.execute("DELETE FROM learning_items")
                connection.execute("DELETE FROM lexemes")
                connection.execute("DELETE FROM lessons")
                connection.execute("DELETE FROM topics")
                connection.execute("DELETE FROM add_words_flows")
                connection.execute("DELETE FROM image_review_flows")
                connection.execute("DELETE FROM user_word_stats")
                connection.execute("DELETE FROM user_weekly_points")
                connection.execute("DELETE FROM user_weekly_word_awards")
                connection.execute("DELETE FROM user_goals")
                connection.execute("DELETE FROM user_goal_words")
                connection.execute("DELETE FROM user_session_word_history")
                connection.execute("DELETE FROM user_homework_word_progress")
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
                lexeme_id = self._upsert_lexeme(
                    connection,
                    headword=item.english_word,
                )
                self._upsert_learning_item(
                    connection,
                    item=item,
                    lexeme_id=lexeme_id,
                )
                if item.topic_id:
                    connection.execute(
                        """
                        INSERT INTO topic_learning_items (id, topic_id, learning_item_id, sort_order)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(topic_id, learning_item_id) DO UPDATE SET
                            sort_order=excluded.sort_order
                        """,
                        (f"{item.topic_id}:{item.id}", item.topic_id, item.id, sort_order),
                    )
                if item.lesson_id:
                    connection.execute(
                        """
                        INSERT INTO lesson_learning_items (id, lesson_id, learning_item_id, sort_order)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(lesson_id, learning_item_id) DO UPDATE SET
                            sort_order=excluded.sort_order
                        """,
                        (f"{item.lesson_id}:{item.id}", item.lesson_id, item.id, sort_order),
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

    def list_lexemes(self) -> list[Lexeme]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, headword, normalized_headword, part_of_speech, notes
                FROM lexemes
                ORDER BY headword, id
                """
            ).fetchall()
        return [
            Lexeme(
                id=row["id"],
                headword=row["headword"],
                normalized_headword=row["normalized_headword"],
                part_of_speech=row["part_of_speech"],
                notes=row["notes"],
            )
            for row in rows
        ]

    def get_lexeme_by_normalized_headword(self, normalized_headword: str) -> Lexeme | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT id, headword, normalized_headword, part_of_speech, notes
                FROM lexemes
                WHERE normalized_headword = ?
                """,
                (normalized_headword,),
            ).fetchone()
        if row is None:
            return None
        return Lexeme(
            id=row["id"],
            headword=row["headword"],
            normalized_headword=row["normalized_headword"],
            part_of_speech=row["part_of_speech"],
            notes=row["notes"],
        )

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
        query = """
            SELECT
                li.id,
                li.lexeme_id,
                li.display_word AS english_word,
                li.display_translation AS translation,
                ? AS topic_id,
                CASE
                    WHEN ? IS NOT NULL THEN lli.lesson_id
                    ELSE (
                        SELECT lli2.lesson_id
                        FROM lesson_learning_items AS lli2
                        JOIN lessons AS l2 ON l2.id = lli2.lesson_id
                        WHERE lli2.learning_item_id = li.id AND l2.topic_id = ?
                        ORDER BY lli2.sort_order, lli2.lesson_id
                        LIMIT 1
                    )
                END AS lesson_id,
                li.meaning_hint,
                li.image_ref,
                li.image_source,
                li.image_prompt,
                li.pixabay_search_query,
                li.source_fragment,
                li.is_active
            FROM topic_learning_items AS tli
            JOIN learning_items AS li ON li.id = tli.learning_item_id
            LEFT JOIN lesson_learning_items AS lli
                ON lli.learning_item_id = li.id AND lli.lesson_id = ?
            WHERE tli.topic_id = ? AND li.is_active = 1
        """
        params: list[object] = [topic_id, lesson_id, topic_id, lesson_id, topic_id]
        if lesson_id is not None:
            query += " AND EXISTS (SELECT 1 FROM lesson_learning_items WHERE lesson_id = ? AND learning_item_id = li.id)"
            params.append(lesson_id)
        query += " ORDER BY tli.sort_order, li.display_word, li.id"
        with _connect(self._db_path) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_vocabulary_item(row) for row in rows]

    def list_all_vocabulary(self) -> list[VocabularyItem]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    li.id,
                    li.lexeme_id,
                    li.display_word AS english_word,
                    li.display_translation AS translation,
                    (
                        SELECT tli.topic_id
                        FROM topic_learning_items AS tli
                        WHERE tli.learning_item_id = li.id
                        ORDER BY tli.sort_order, tli.topic_id
                        LIMIT 1
                    ) AS topic_id,
                    (
                        SELECT lli.lesson_id
                        FROM lesson_learning_items AS lli
                        WHERE lli.learning_item_id = li.id
                        ORDER BY lli.sort_order, lli.lesson_id
                        LIMIT 1
                    ) AS lesson_id,
                    li.meaning_hint,
                    li.image_ref,
                    li.image_source,
                    li.image_prompt,
                    li.pixabay_search_query,
                    li.source_fragment,
                    li.is_active
                FROM learning_items AS li
                ORDER BY li.display_word, li.id
                """
            ).fetchall()
        return [self._row_to_vocabulary_item(row) for row in rows]

    def get_vocabulary_item(self, item_id: str) -> VocabularyItem | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    li.id,
                    li.lexeme_id,
                    li.display_word AS english_word,
                    li.display_translation AS translation,
                    (
                        SELECT tli.topic_id
                        FROM topic_learning_items AS tli
                        WHERE tli.learning_item_id = li.id
                        ORDER BY tli.sort_order, tli.topic_id
                        LIMIT 1
                    ) AS topic_id,
                    (
                        SELECT lli.lesson_id
                        FROM lesson_learning_items AS lli
                        WHERE lli.learning_item_id = li.id
                        ORDER BY lli.sort_order, lli.lesson_id
                        LIMIT 1
                    ) AS lesson_id,
                    li.meaning_hint,
                    li.image_ref,
                    li.image_source,
                    li.image_prompt,
                    li.pixabay_search_query,
                    li.source_fragment,
                    li.is_active
                FROM learning_items AS li
                WHERE li.id = ?
                """,
                (item_id,),
            ).fetchone()
        return self._row_to_vocabulary_item(row) if row is not None else None

    def list_editable_words(self, topic_id: str) -> list[tuple[str, str, str, bool]]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    li.id,
                    li.display_word AS english_word,
                    li.display_translation AS translation,
                    li.image_ref AS image_ref
                FROM topic_learning_items AS tli
                JOIN learning_items AS li ON li.id = tli.learning_item_id
                WHERE tli.topic_id = ?
                ORDER BY tli.sort_order, li.display_word, li.id
                """,
                (topic_id,),
            ).fetchall()
        return [
            (
                row["id"],
                row["english_word"],
                row["translation"],
                bool(str(row["image_ref"] or "").strip()),
            )
            for row in rows
        ]

    def list_topic_ids_for_item(self, item_id: str) -> list[str]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT topic_id
                FROM topic_learning_items
                WHERE learning_item_id = ?
                ORDER BY sort_order, topic_id
                """,
                (item_id,),
            ).fetchall()
        return [row["topic_id"] for row in rows]

    def list_lesson_ids_for_item(self, item_id: str) -> list[str]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT lesson_id
                FROM lesson_learning_items
                WHERE learning_item_id = ?
                ORDER BY sort_order, lesson_id
                """,
                (item_id,),
            ).fetchall()
        return [row["lesson_id"] for row in rows]

    def update_word(self, *, topic_id: str, item_id: str, english_word: str, translation: str) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            lexeme_id = self._upsert_lexeme(connection, headword=english_word)
            cursor = connection.execute(
                """
                UPDATE learning_items
                SET display_word = ?, display_translation = ?, lexeme_id = ?
                WHERE id = ? AND EXISTS (
                    SELECT 1
                    FROM topic_learning_items
                    WHERE topic_id = ? AND learning_item_id = learning_items.id
                )
                """,
                (english_word, translation, lexeme_id, item_id, topic_id),
            )
        if cursor.rowcount == 0:
            raise ValueError("Vocabulary item was not found.")

    def update_word_image(
        self,
        *,
        item_id: str,
        image_ref: str,
        image_source: str | None,
        pixabay_search_query: str | None,
        source_fragment: str | None,
    ) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE learning_items
                SET image_ref = ?, image_source = ?, pixabay_search_query = ?, source_fragment = ?
                WHERE id = ?
                """,
                (
                    image_ref,
                    image_source,
                    pixabay_search_query,
                    source_fragment,
                    item_id,
                ),
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
                    **({"meaning_hint": item.meaning_hint} if item.meaning_hint is not None else {}),
                    **({"image_ref": item.image_ref} if item.image_ref is not None else {}),
                    **({"image_source": item.image_source} if item.image_source is not None else {}),
                    **({"image_prompt": item.image_prompt} if item.image_prompt is not None else {}),
                    **(
                        {"pixabay_search_query": item.pixabay_search_query}
                        if item.pixabay_search_query is not None
                        else {}
                    ),
                    **(
                        {"source_fragment": item.source_fragment}
                        if item.source_fragment is not None
                        else {}
                    ),
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
            existing_lesson_rows = connection.execute(
                "SELECT id FROM lessons WHERE topic_id = ?",
                (topic_id,),
            ).fetchall()
            existing_lesson_ids = [row["id"] for row in existing_lesson_rows]
            for lesson_id in existing_lesson_ids:
                connection.execute(
                    "DELETE FROM lesson_learning_items WHERE lesson_id = ?",
                    (lesson_id,),
                )
            connection.execute("DELETE FROM topic_learning_items WHERE topic_id = ?", (topic_id,))
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
            sort_order = 0
            for item_raw in items_raw:
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
                expanded_items = _expand_slash_synonym_items(
                    item_id=item_id,
                    english_word=english_word,
                    translation=translation,
                    topic_id=topic_id,
                    lesson_id=lesson_id,
                    meaning_hint=_optional_json_str(item_raw.get("meaning_hint")),
                    image_ref=_optional_json_str(item_raw.get("image_ref")),
                    image_source=_optional_json_str(item_raw.get("image_source")),
                    image_prompt=_optional_json_str(item_raw.get("image_prompt")),
                    pixabay_search_query=_optional_json_str(item_raw.get("pixabay_search_query")),
                    source_fragment=_optional_json_str(item_raw.get("source_fragment")),
                    is_active=bool(item_raw.get("is_active", True)),
                )
                for expanded_item in expanded_items:
                    lexeme_id = self._upsert_lexeme(connection, headword=expanded_item.english_word)
                    self._upsert_learning_item(connection, item=expanded_item, lexeme_id=lexeme_id)
                    connection.execute(
                        """
                        INSERT INTO topic_learning_items (id, topic_id, learning_item_id, sort_order)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(topic_id, learning_item_id) DO UPDATE SET
                            sort_order=excluded.sort_order
                        """,
                        (
                            f"{topic_id}:{expanded_item.id}",
                            topic_id,
                            expanded_item.id,
                            sort_order,
                        ),
                    )
                    if lesson_id is not None:
                        connection.execute(
                            """
                            INSERT INTO lesson_learning_items (id, lesson_id, learning_item_id, sort_order)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(lesson_id, learning_item_id) DO UPDATE SET
                                sort_order=excluded.sort_order
                            """,
                            (
                                f"{lesson_id}:{expanded_item.id}",
                                lesson_id,
                                expanded_item.id,
                                sort_order,
                            ),
                        )
                    sort_order += 1
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

    def get_word_stats(self, user_id: int, word_id: str) -> WordStats | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM user_word_stats
                WHERE user_id = ? AND word_id = ?
                """,
                (user_id, word_id),
            ).fetchone()
        if row is None:
            return None
        return WordStats(
            user_id=row["user_id"],
            word_id=row["word_id"],
            attempt_easy=row["attempt_easy"],
            attempt_medium=row["attempt_medium"],
            attempt_hard=row["attempt_hard"],
            success_easy=row["success_easy"],
            success_medium=row["success_medium"],
            success_hard=row["success_hard"],
            last_seen_at=(
                datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None
            ),
            last_correct_at=(
                datetime.fromisoformat(row["last_correct_at"]) if row["last_correct_at"] else None
            ),
            current_level=row["current_level"],
            current_streak_success=row["current_streak_success"],
            current_streak_fail=row["current_streak_fail"],
            review_interval_days=int(row["review_interval_days"] or 0),
            next_review_at=(
                datetime.fromisoformat(row["next_review_at"]) if row["next_review_at"] else None
            ),
        )

    def save_word_stats(self, stats: WordStats) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_word_stats (
                    user_id, word_id, attempt_easy, attempt_medium, attempt_hard,
                    success_easy, success_medium, success_hard, last_seen_at, last_correct_at,
                    current_level, current_streak_success, current_streak_fail,
                    review_interval_days, next_review_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, word_id) DO UPDATE SET
                    attempt_easy=excluded.attempt_easy,
                    attempt_medium=excluded.attempt_medium,
                    attempt_hard=excluded.attempt_hard,
                    success_easy=excluded.success_easy,
                    success_medium=excluded.success_medium,
                    success_hard=excluded.success_hard,
                    last_seen_at=excluded.last_seen_at,
                    last_correct_at=excluded.last_correct_at,
                    current_level=excluded.current_level,
                    current_streak_success=excluded.current_streak_success,
                    current_streak_fail=excluded.current_streak_fail,
                    review_interval_days=excluded.review_interval_days,
                    next_review_at=excluded.next_review_at
                """,
                (
                    stats.user_id,
                    stats.word_id,
                    stats.attempt_easy,
                    stats.attempt_medium,
                    stats.attempt_hard,
                    stats.success_easy,
                    stats.success_medium,
                    stats.success_hard,
                    stats.last_seen_at.isoformat() if stats.last_seen_at else None,
                    stats.last_correct_at.isoformat() if stats.last_correct_at else None,
                    stats.current_level,
                    stats.current_streak_success,
                    stats.current_streak_fail,
                    stats.review_interval_days,
                    stats.next_review_at.isoformat() if stats.next_review_at else None,
                ),
            )

    def award_weekly_points(
        self,
        *,
        user_id: int,
        word_id: str,
        mode: TrainingMode,
        level_up_delta: int,
        awarded_at: datetime,
    ) -> int:
        self.initialize()
        from englishbot.application.learning_progress import week_start

        week_start_date = week_start(awarded_at).date().isoformat()
        difficulty_bonus = {TrainingMode.EASY: 0, TrainingMode.MEDIUM: 1, TrainingMode.HARD: 2}[mode]
        level_bonus = {0: 0, 1: 5, 2: 10, 3: 20}.get(level_up_delta, 20 if level_up_delta > 3 else 0)
        with _connect(self._db_path) as connection:
            already_awarded = connection.execute(
                """
                SELECT 1
                FROM user_weekly_word_awards
                WHERE user_id = ? AND week_start_date = ? AND word_id = ?
                """,
                (user_id, week_start_date, word_id),
            ).fetchone()
            base_points = 0 if already_awarded else 10
            total_delta = base_points + difficulty_bonus + level_bonus
            connection.execute(
                """
                INSERT INTO user_weekly_points (user_id, week_start_date, points)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, week_start_date) DO UPDATE SET
                    points = user_weekly_points.points + excluded.points
                """,
                (user_id, week_start_date, total_delta),
            )
            if already_awarded is None:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO user_weekly_word_awards (user_id, week_start_date, word_id)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, week_start_date, word_id),
                )
            row = connection.execute(
                """
                SELECT points
                FROM user_weekly_points
                WHERE user_id = ? AND week_start_date = ?
                """,
                (user_id, week_start_date),
            ).fetchone()
        return int(row["points"]) if row else 0

    def assign_goal(
        self,
        *,
        user_id: int,
        goal_period: GoalPeriod,
        goal_type: GoalType,
        target_count: int,
        deadline_date: str | None = None,
        reward_points: int | None = None,
        required_level: int | None = None,
        target_topic_id: str | None = None,
        target_word_ids: list[str] | None = None,
    ) -> Goal:
        self.initialize()
        goal_id = str(uuid.uuid4())
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_goals (
                    id, user_id, goal_period, goal_type, target_count, progress_count, status,
                    deadline_date, reward_points, required_level, target_topic_id
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    goal_id,
                    user_id,
                    goal_period.value,
                    goal_type.value,
                    target_count,
                    GoalStatus.ACTIVE.value,
                    deadline_date,
                    reward_points,
                    required_level,
                    target_topic_id,
                ),
            )
            for word_id in target_word_ids or []:
                connection.execute(
                    "INSERT OR IGNORE INTO user_goal_words (goal_id, word_id) VALUES (?, ?)",
                    (goal_id, word_id),
                )
                if (
                    goal_period is GoalPeriod.HOMEWORK
                    and goal_type is GoalType.WORD_LEVEL_HOMEWORK
                ):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO user_homework_word_progress (
                            goal_id, user_id, word_id
                        ) VALUES (?, ?, ?)
                        """,
                        (goal_id, user_id, word_id),
                    )
        return Goal(
            id=goal_id,
            user_id=user_id,
            goal_period=goal_period,
            goal_type=goal_type,
            target_count=target_count,
            progress_count=0,
            status=GoalStatus.ACTIVE,
            deadline_date=deadline_date,
            reward_points=reward_points,
            required_level=required_level,
            target_topic_id=target_topic_id,
        )

    def list_user_goals(
        self,
        *,
        user_id: int,
        statuses: tuple[GoalStatus, ...] = (GoalStatus.ACTIVE,),
    ) -> list[Goal]:
        self.initialize()
        status_values = tuple(status.value for status in statuses)
        placeholders = ",".join("?" for _ in status_values)
        with _connect(self._db_path) as connection:
            self._refresh_goal_progress(connection, user_id=user_id)
            rows = connection.execute(
                f"""
                SELECT *
                FROM user_goals
                WHERE user_id = ? AND status IN ({placeholders})
                ORDER BY created_at DESC
                """,
                (user_id, *status_values),
            ).fetchall()
        return [
            Goal(
                id=str(row["id"]),
                user_id=int(row["user_id"]),
                goal_period=GoalPeriod(row["goal_period"]),
                goal_type=GoalType(row["goal_type"]),
                target_count=int(row["target_count"]),
                progress_count=int(row["progress_count"]),
                status=GoalStatus(row["status"]),
                deadline_date=row["deadline_date"],
                reward_points=row["reward_points"],
                required_level=row["required_level"],
                target_topic_id=row["target_topic_id"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

    def _refresh_goal_progress(self, connection: sqlite3.Connection, *, user_id: int) -> None:
        active_goals = connection.execute(
            """
            SELECT id, user_id, goal_type, target_count, progress_count, status
            FROM user_goals
            WHERE user_id = ? AND status = ?
            """,
            (user_id, GoalStatus.ACTIVE.value),
        ).fetchall()
        for goal in active_goals:
            goal_type = GoalType(str(goal["goal_type"]))
            if goal_type is GoalType.NEW_WORDS:
                progress_count = self._count_completed_goal_words(
                    connection,
                    goal_id=str(goal["id"]),
                    user_id=int(goal["user_id"]),
                )
            elif goal_type is GoalType.WORD_LEVEL_HOMEWORK:
                progress_count = self._count_mastered_homework_words(
                    connection,
                    goal_id=str(goal["id"]),
                    user_id=int(goal["user_id"]),
                )
            else:
                continue
            target_count = int(goal["target_count"])
            status = (
                GoalStatus.COMPLETED.value
                if target_count > 0 and progress_count >= target_count
                else GoalStatus.ACTIVE.value
            )
            if progress_count == int(goal["progress_count"]) and status == str(goal["status"]):
                continue
            connection.execute(
                """
                UPDATE user_goals
                SET progress_count = ?, status = ?
                WHERE id = ?
                """,
                (progress_count, status, goal["id"]),
            )

    def _count_completed_goal_words(
        self,
        connection: sqlite3.Connection,
        *,
        goal_id: str,
        user_id: int,
    ) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS completed_count
            FROM user_goal_words goal_words
            JOIN user_goals goals
              ON goals.id = goal_words.goal_id
            JOIN user_word_stats stats
              ON stats.user_id = ?
             AND stats.word_id = goal_words.word_id
            WHERE goal_words.goal_id = ?
              AND stats.last_correct_at IS NOT NULL
              AND stats.last_correct_at >= goals.created_at
            """,
            (user_id, goal_id),
        ).fetchone()
        return int(row["completed_count"] or 0) if row else 0

    def _count_mastered_homework_words(
        self,
        connection: sqlite3.Connection,
        *,
        goal_id: str,
        user_id: int,
    ) -> int:
        row = connection.execute(
            """
            SELECT SUM(CASE WHEN progress.medium_mastered = 1 THEN 1 ELSE 0 END) AS mastered_count
            FROM user_goal_words goal_words
            LEFT JOIN user_homework_word_progress progress
              ON progress.goal_id = goal_words.goal_id
             AND progress.user_id = ?
             AND progress.word_id = goal_words.word_id
            WHERE goal_words.goal_id = ?
            """,
            (user_id, goal_id),
        ).fetchone()
        return int(row["mastered_count"] or 0) if row else 0

    def list_goal_word_details(self, *, goal_id: str, user_id: int) -> list[dict[str, object]]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    w.word_id AS word_id,
                    li.display_word AS english_word,
                    li.display_translation AS translation,
                    CASE
                        WHEN p.word_id IS NULL THEN NULL
                        WHEN p.easy_mastered = 0 THEN ?
                        WHEN p.medium_mastered = 0 THEN ?
                        WHEN p.hard_skipped = 1 OR p.hard_mastered = 1 THEN ?
                        ELSE ?
                    END AS homework_mode,
                    p.easy_mastered AS easy_mastered,
                    p.medium_mastered AS medium_mastered,
                    p.hard_mastered AS hard_mastered,
                    p.hard_skipped AS hard_skipped
                FROM user_goal_words w
                LEFT JOIN learning_items li ON li.id = w.word_id
                LEFT JOIN user_homework_word_progress p
                    ON p.goal_id = w.goal_id
                    AND p.user_id = ?
                    AND p.word_id = w.word_id
                WHERE w.goal_id = ?
                ORDER BY li.display_word COLLATE NOCASE ASC, w.word_id ASC
                """,
                (
                    TrainingMode.EASY.value,
                    TrainingMode.MEDIUM.value,
                    TrainingMode.MEDIUM.value,
                    TrainingMode.HARD.value,
                    user_id,
                    goal_id,
                ),
            ).fetchall()
        return [
            {
                "word_id": str(row["word_id"]),
                "english_word": str(row["english_word"] or row["word_id"]),
                "translation": str(row["translation"] or ""),
                "homework_mode": row["homework_mode"],
                "easy_mastered": bool(row["easy_mastered"]) if row["easy_mastered"] is not None else False,
                "medium_mastered": bool(row["medium_mastered"]) if row["medium_mastered"] is not None else False,
                "hard_mastered": bool(row["hard_mastered"]) if row["hard_mastered"] is not None else False,
                "hard_skipped": bool(row["hard_skipped"]) if row["hard_skipped"] is not None else False,
            }
            for row in rows
        ]

    def update_goal_status(
        self,
        *,
        user_id: int,
        goal_id: str,
        status: GoalStatus,
    ) -> bool:
        self.initialize()
        with _connect(self._db_path) as connection:
            result = connection.execute(
                """
                UPDATE user_goals
                SET status = ?
                WHERE id = ? AND user_id = ? AND status = ?
                """,
                (status.value, goal_id, user_id, GoalStatus.ACTIVE.value),
            )
        return bool(result.rowcount)

    def list_users_goal_overview(self) -> list[dict[str, object]]:
        self.initialize()
        with _connect(self._db_path) as connection:
            user_rows = connection.execute(
                """
                SELECT DISTINCT user_id
                FROM user_goals
                WHERE status = ?
                """,
                (GoalStatus.ACTIVE.value,),
            ).fetchall()
            for user_row in user_rows:
                self._refresh_goal_progress(connection, user_id=int(user_row["user_id"]))
            rows = connection.execute(
                """
                SELECT
                    g.user_id AS user_id,
                    SUM(CASE WHEN g.status = ? THEN 1 ELSE 0 END) AS active_goals_count,
                    SUM(CASE WHEN g.status = ? THEN 1 ELSE 0 END) AS completed_goals_count,
                    COALESCE(SUM(g.progress_count), 0) AS progress_total,
                    COALESCE(SUM(g.target_count), 0) AS target_total,
                    MAX(p.last_seen_at) AS last_activity_at
                FROM user_goals g
                LEFT JOIN user_progress p ON p.user_id = g.user_id
                GROUP BY g.user_id
                ORDER BY g.user_id ASC
                """,
                (GoalStatus.ACTIVE.value, GoalStatus.COMPLETED.value),
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            target_total = int(row["target_total"])
            progress_total = int(row["progress_total"])
            aggregate_percent = min(100, int((progress_total / target_total) * 100)) if target_total > 0 else 0
            result.append(
                {
                    "user_id": int(row["user_id"]),
                    "active_goals_count": int(row["active_goals_count"]),
                    "completed_goals_count": int(row["completed_goals_count"]),
                    "aggregate_percent": aggregate_percent,
                    "last_activity_at": (
                        datetime.fromisoformat(str(row["last_activity_at"]))
                        if row["last_activity_at"]
                        else None
                    ),
                }
            )
        return result

    def list_active_homework_words(self, *, user_id: int) -> dict[str, int]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT w.word_id, COALESCE(g.required_level, 1) AS required_level
                FROM user_goals g
                JOIN user_goal_words w ON w.goal_id = g.id
                WHERE g.user_id = ?
                  AND g.status = ?
                  AND g.goal_period = ?
                  AND g.goal_type = ?
                """,
                (
                    user_id,
                    GoalStatus.ACTIVE.value,
                    GoalPeriod.HOMEWORK.value,
                    GoalType.WORD_LEVEL_HOMEWORK.value,
                ),
            ).fetchall()
        return {row["word_id"]: int(row["required_level"]) for row in rows}

    def required_homework_level(self, *, user_id: int, item_id: str) -> int | None:
        return self.list_active_homework_words(user_id=user_id).get(item_id)

    def list_active_goal_words(self, *, user_id: int) -> set[str]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT w.word_id
                FROM user_goals g
                JOIN user_goal_words w ON w.goal_id = g.id
                WHERE g.user_id = ? AND g.status = ? AND g.goal_period IN (?, ?)
                """,
                (
                    user_id,
                    GoalStatus.ACTIVE.value,
                    GoalPeriod.DAILY.value,
                    GoalPeriod.WEEKLY.value,
                ),
            ).fetchall()
        return {str(row["word_id"]) for row in rows}

    def list_recent_session_words(self, *, user_id: int, limit_sessions: int = 3) -> set[str]:
        self.initialize()
        with _connect(self._db_path) as connection:
            session_rows = connection.execute(
                """
                SELECT session_id, MAX(rowid) AS max_rowid
                FROM user_session_word_history
                WHERE user_id = ?
                GROUP BY session_id
                ORDER BY max_rowid DESC
                LIMIT ?
                """,
                (user_id, limit_sessions),
            ).fetchall()
            session_ids = [str(row["session_id"]) for row in session_rows]
            if not session_ids:
                return set()
            placeholders = ",".join("?" for _ in session_ids)
            rows = connection.execute(
                f"SELECT DISTINCT word_id FROM user_session_word_history WHERE session_id IN ({placeholders})",
                tuple(session_ids),
            ).fetchall()
        return {str(row["word_id"]) for row in rows}

    def list_due_review_words(self, *, user_id: int) -> set[str]:
        self.initialize()
        now_iso = datetime.now(UTC).isoformat()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT word_id
                FROM user_word_stats
                WHERE user_id = ?
                  AND next_review_at IS NOT NULL
                  AND next_review_at <= ?
                """,
                (user_id, now_iso),
            ).fetchall()
        return {str(row["word_id"]) for row in rows}

    def get_homework_stage_mode(self, *, user_id: int, item_id: str) -> TrainingMode | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT p.*
                FROM user_homework_word_progress p
                JOIN user_goals g ON g.id = p.goal_id
                WHERE p.user_id = ?
                  AND p.word_id = ?
                  AND g.status = ?
                  AND g.goal_period = ?
                ORDER BY g.created_at DESC
                LIMIT 1
                """,
                (user_id, item_id, GoalStatus.ACTIVE.value, GoalPeriod.HOMEWORK.value),
            ).fetchone()
        if row is None:
            return None
        if not bool(row["easy_mastered"]):
            return TrainingMode.EASY
        if not bool(row["medium_mastered"]):
            return TrainingMode.MEDIUM
        if bool(row["hard_skipped"]) or bool(row["hard_mastered"]):
            return TrainingMode.MEDIUM
        return TrainingMode.HARD

    def update_homework_word_progress(
        self,
        *,
        user_id: int,
        word_id: str,
        mode: TrainingMode,
        is_correct: bool,
        current_level: int,
    ) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT p.goal_id, p.easy_success_count, p.medium_success_count, p.hard_success_count,
                       p.easy_mastered, p.medium_mastered, p.hard_mastered, p.hard_skipped, p.hard_failed_streak
                FROM user_homework_word_progress p
                JOIN user_goals g ON g.id = p.goal_id
                WHERE p.user_id = ?
                  AND p.word_id = ?
                  AND g.status = ?
                  AND g.goal_period = ?
                """,
                (user_id, word_id, GoalStatus.ACTIVE.value, GoalPeriod.HOMEWORK.value),
            ).fetchall()
            for row in rows:
                easy_success_count = int(row["easy_success_count"])
                medium_success_count = int(row["medium_success_count"])
                hard_success_count = int(row["hard_success_count"])
                easy_mastered = bool(row["easy_mastered"])
                medium_mastered = bool(row["medium_mastered"])
                hard_mastered = bool(row["hard_mastered"])
                hard_skipped = bool(row["hard_skipped"])
                hard_failed_streak = int(row["hard_failed_streak"])

                if is_correct and mode is TrainingMode.EASY:
                    easy_success_count += 1
                if is_correct and mode is TrainingMode.MEDIUM:
                    medium_success_count += 1
                    easy_mastered = True
                if is_correct and mode is TrainingMode.HARD:
                    hard_success_count += 1
                    easy_mastered = True
                    medium_mastered = True
                    hard_mastered = hard_success_count >= 2
                    hard_failed_streak = 0
                elif mode is TrainingMode.HARD and not is_correct:
                    hard_failed_streak += 1
                    if hard_failed_streak >= 2:
                        hard_skipped = True

                if easy_success_count >= 2:
                    easy_mastered = True
                if medium_success_count >= 2:
                    medium_mastered = True
                if current_level >= 2:
                    easy_mastered = True
                    medium_mastered = True
                if hard_mastered:
                    hard_skipped = False

                connection.execute(
                    """
                    UPDATE user_homework_word_progress
                    SET easy_success_count = ?,
                        medium_success_count = ?,
                        hard_success_count = ?,
                        easy_mastered = ?,
                        medium_mastered = ?,
                        hard_mastered = ?,
                        hard_skipped = ?,
                        hard_failed_streak = ?
                    WHERE goal_id = ? AND word_id = ?
                    """,
                    (
                        easy_success_count,
                        medium_success_count,
                        hard_success_count,
                        1 if easy_mastered else 0,
                        1 if medium_mastered else 0,
                        1 if hard_mastered else 0,
                        1 if hard_skipped else 0,
                        hard_failed_streak,
                        row["goal_id"],
                        word_id,
                    ),
                )
                goal_row = connection.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN medium_mastered = 1 THEN 1 ELSE 0 END) AS mastered
                    FROM user_homework_word_progress
                    WHERE goal_id = ?
                    """,
                    (row["goal_id"],),
                ).fetchone()
                total = int(goal_row["total"] or 0) if goal_row else 0
                mastered = int(goal_row["mastered"] or 0) if goal_row else 0
                status = (
                    GoalStatus.COMPLETED.value
                    if total > 0 and mastered >= total
                    else GoalStatus.ACTIVE.value
                )
                connection.execute(
                    """
                    UPDATE user_goals
                    SET progress_count = ?, status = ?
                    WHERE id = ?
                    """,
                    (mastered, status, row["goal_id"]),
                )

    def update_goals_progress(
        self,
        *,
        user_id: int,
        word_id: str,
        topic_id: str,
        is_correct: bool,
        current_level: int,
    ) -> None:
        self.initialize()
        if not is_correct:
            return
        with _connect(self._db_path) as connection:
            goals = connection.execute(
                """
                SELECT * FROM user_goals WHERE user_id = ? AND status = ?
                """,
                (user_id, GoalStatus.ACTIVE.value),
            ).fetchall()
            for goal in goals:
                increment = 0
                if goal["goal_type"] == GoalType.NEW_WORDS.value:
                    word_match = connection.execute(
                        "SELECT 1 FROM user_goal_words WHERE goal_id = ? AND word_id = ?",
                        (goal["id"], word_id),
                    ).fetchone()
                    if word_match:
                        increment = 1
                elif goal["goal_type"] == GoalType.TOPICS.value:
                    increment = 1 if goal["target_topic_id"] == topic_id else 0
                if increment <= 0:
                    continue
                progress_count = (
                    self._count_completed_goal_words(
                        connection,
                        goal_id=str(goal["id"]),
                        user_id=user_id,
                    )
                    if goal["goal_type"] == GoalType.NEW_WORDS.value
                    else int(goal["progress_count"]) + increment
                )
                status = (
                    GoalStatus.COMPLETED.value
                    if progress_count >= int(goal["target_count"])
                    else GoalStatus.ACTIVE.value
                )
                connection.execute(
                    """
                    UPDATE user_goals
                    SET progress_count = ?, status = ?
                    WHERE id = ?
                    """,
                    (progress_count, status, goal["id"]),
                )

    def get_weekly_points(self, *, user_id: int, now: datetime | None = None) -> int:
        self.initialize()
        from englishbot.application.learning_progress import week_start

        current = now or datetime.now(UTC)
        week_start_date = week_start(current).date().isoformat()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT points
                FROM user_weekly_points
                WHERE user_id = ? AND week_start_date = ?
                """,
                (user_id, week_start_date),
            ).fetchone()
        return int(row["points"]) if row else 0

    def get_game_profile(self, *, user_id: int) -> UserGameProfile:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT user_id, total_stars, current_streak_days, last_played_on
                FROM user_game_profile
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return UserGameProfile(
                user_id=user_id,
                total_stars=0,
                current_streak_days=0,
                last_played_on=None,
            )
        return UserGameProfile(
            user_id=int(row["user_id"]),
            total_stars=int(row["total_stars"]),
            current_streak_days=int(row["current_streak_days"]),
            last_played_on=row["last_played_on"],
        )

    def add_game_stars(self, *, user_id: int, stars: int) -> int:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_game_profile (user_id, total_stars, current_streak_days, last_played_on)
                VALUES (?, ?, 0, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_stars = user_game_profile.total_stars + excluded.total_stars
                """,
                (user_id, stars),
            )
            row = connection.execute(
                "SELECT total_stars FROM user_game_profile WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["total_stars"]) if row is not None else 0

    def update_game_streak(self, *, user_id: int, played_at: datetime) -> int:
        self.initialize()
        played_on = played_at.date()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT current_streak_days, last_played_on
                FROM user_game_profile
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                streak_days = 1
                connection.execute(
                    """
                    INSERT INTO user_game_profile (user_id, total_stars, current_streak_days, last_played_on)
                    VALUES (?, 0, ?, ?)
                    """,
                    (user_id, streak_days, played_on.isoformat()),
                )
                return streak_days
            last_played_on_raw = row["last_played_on"]
            current_streak_days = int(row["current_streak_days"] or 0)
            if not last_played_on_raw:
                streak_days = 1
            else:
                last_played_on = datetime.fromisoformat(str(last_played_on_raw)).date()
                delta_days = (played_on - last_played_on).days
                if delta_days <= 0:
                    streak_days = current_streak_days or 1
                elif delta_days == 1:
                    streak_days = current_streak_days + 1
                else:
                    streak_days = 1
            connection.execute(
                """
                UPDATE user_game_profile
                SET current_streak_days = ?, last_played_on = ?
                WHERE user_id = ?
                """,
                (streak_days, played_on.isoformat(), user_id),
            )
        return streak_days

    def save_session(self, session: TrainingSession) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO training_sessions (
                    id, user_id, topic_id, lesson_id, source_tag, mode, current_index, completed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    topic_id=excluded.topic_id,
                    lesson_id=excluded.lesson_id,
                    source_tag=excluded.source_tag,
                    mode=excluded.mode,
                    current_index=excluded.current_index,
                    completed=excluded.completed
                """,
                (
                    session.id,
                    session.user_id,
                    session.topic_id,
                    session.lesson_id,
                    session.source_tag,
                    session.mode.value,
                    session.current_index,
                    1 if session.completed else 0,
                ),
            )
            connection.execute("DELETE FROM training_session_items WHERE session_id = ?", (session.id,))
            connection.execute("DELETE FROM training_session_answers WHERE session_id = ?", (session.id,))
            connection.execute("DELETE FROM user_session_word_history WHERE session_id = ?", (session.id,))
            for item in session.items:
                connection.execute(
                    """
                    INSERT INTO training_session_items (session_id, sort_order, vocabulary_item_id, mode)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        session.id,
                        item.order,
                        item.vocabulary_item_id,
                        item.mode.value if item.mode is not None else None,
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO user_session_word_history (session_id, user_id, word_id, seen_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (session.id, session.user_id, item.vocabulary_item_id),
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
                SELECT id, user_id, topic_id, lesson_id, source_tag, mode, current_index, completed
                FROM training_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if session_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT sort_order, vocabulary_item_id, mode
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
            source_tag=session_row["source_tag"],
            mode=TrainingMode(session_row["mode"]),
            current_index=session_row["current_index"],
            completed=bool(session_row["completed"]),
            items=[
                SessionItem(order=row["sort_order"], vocabulary_item_id=row["vocabulary_item_id"])
                if row["mode"] is None
                else SessionItem(
                    order=row["sort_order"],
                    vocabulary_item_id=row["vocabulary_item_id"],
                    mode=TrainingMode(row["mode"]),
                )
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

    def save_add_words_flow(self, flow: AddWordsFlowState) -> None:
        self.initialize()
        payload = {
            "flow_id": flow.flow_id,
            "editor_user_id": flow.editor_user_id,
            "stage": flow.stage,
            "raw_text": flow.raw_text,
            "draft_json": json.dumps(draft_to_data(flow.draft_result.draft), ensure_ascii=False),
            "validation_errors_json": json.dumps(
                [asdict(error) for error in flow.draft_result.validation.errors],
                ensure_ascii=False,
            ),
            "draft_output_path": str(flow.draft_output_path) if flow.draft_output_path else None,
            "final_output_path": str(flow.final_output_path) if flow.final_output_path else None,
            "image_review_flow_id": flow.image_review_flow_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        with _connect(self._db_path) as connection:
            connection.execute(
                "UPDATE add_words_flows SET is_active = 0 WHERE editor_user_id = ? AND flow_id != ?",
                (flow.editor_user_id, flow.flow_id),
            )
            connection.execute(
                """
                INSERT INTO add_words_flows (
                    flow_id, editor_user_id, is_active, stage, raw_text, draft_json,
                    validation_errors_json, draft_output_path, final_output_path,
                    image_review_flow_id, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(flow_id) DO UPDATE SET
                    editor_user_id=excluded.editor_user_id,
                    is_active=1,
                    stage=excluded.stage,
                    raw_text=excluded.raw_text,
                    draft_json=excluded.draft_json,
                    validation_errors_json=excluded.validation_errors_json,
                    draft_output_path=excluded.draft_output_path,
                    final_output_path=excluded.final_output_path,
                    image_review_flow_id=excluded.image_review_flow_id,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["flow_id"],
                    payload["editor_user_id"],
                    payload["stage"],
                    payload["raw_text"],
                    payload["draft_json"],
                    payload["validation_errors_json"],
                    payload["draft_output_path"],
                    payload["final_output_path"],
                    payload["image_review_flow_id"],
                    payload["updated_at"],
                ),
            )

    def get_active_add_words_flow_by_user(self, user_id: int) -> AddWordsFlowState | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM add_words_flows
                WHERE editor_user_id = ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return self._row_to_add_words_flow(row) if row is not None else None

    def get_add_words_flow_by_id(self, flow_id: str) -> AddWordsFlowState | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM add_words_flows WHERE flow_id = ?",
                (flow_id,),
            ).fetchone()
        return self._row_to_add_words_flow(row) if row is not None else None

    def discard_active_add_words_flow_by_user(self, user_id: int) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM add_words_flows WHERE editor_user_id = ? AND is_active = 1",
                (user_id,),
            )

    def save_image_review_flow(self, flow: ImageReviewFlowState) -> None:
        self.initialize()
        items_json = json.dumps(
            [
                {
                    "item_id": item.item_id,
                    "english_word": item.english_word,
                    "translation": item.translation,
                    "prompt": item.prompt,
                    "search_query": item.search_query,
                    "search_page": item.search_page,
                    "candidate_source_type": item.candidate_source_type,
                    "selected_candidate_index": item.selected_candidate_index,
                    "approved_source_type": item.approved_source_type,
                    "needs_review": item.needs_review,
                    "skipped": item.skipped,
                    "candidates": [
                        {
                            "model_name": candidate.model_name,
                            "image_ref": candidate.image_ref,
                            "output_path": str(candidate.output_path),
                            "prompt": candidate.prompt,
                            "source_type": candidate.source_type,
                            "source_id": candidate.source_id,
                            "preview_url": candidate.preview_url,
                            "full_image_url": candidate.full_image_url,
                            "source_page_url": candidate.source_page_url,
                            "width": candidate.width,
                            "height": candidate.height,
                        }
                        for candidate in item.candidates
                    ],
                }
                for item in flow.items
            ],
            ensure_ascii=False,
        )
        with _connect(self._db_path) as connection:
            connection.execute(
                "UPDATE image_review_flows SET is_active = 0 WHERE editor_user_id = ? AND flow_id != ?",
                (flow.editor_user_id, flow.flow_id),
            )
            connection.execute(
                """
                INSERT INTO image_review_flows (
                    flow_id, editor_user_id, is_active, content_pack_json, items_json,
                    current_index, output_path, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(flow_id) DO UPDATE SET
                    editor_user_id=excluded.editor_user_id,
                    is_active=1,
                    content_pack_json=excluded.content_pack_json,
                    items_json=excluded.items_json,
                    current_index=excluded.current_index,
                    output_path=excluded.output_path,
                    updated_at=excluded.updated_at
                """,
                (
                    flow.flow_id,
                    flow.editor_user_id,
                    json.dumps(flow.content_pack, ensure_ascii=False),
                    items_json,
                    flow.current_index,
                    str(flow.output_path) if flow.output_path else None,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_active_image_review_flow_by_user(self, user_id: int) -> ImageReviewFlowState | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM image_review_flows
                WHERE editor_user_id = ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return self._row_to_image_review_flow(row) if row is not None else None

    def get_image_review_flow_by_id(self, flow_id: str) -> ImageReviewFlowState | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM image_review_flows WHERE flow_id = ?",
                (flow_id,),
            ).fetchone()
        return self._row_to_image_review_flow(row) if row is not None else None

    def discard_active_image_review_flow_by_user(self, user_id: int) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM image_review_flows WHERE editor_user_id = ? AND is_active = 1",
                (user_id,),
            )

    def track_telegram_flow_message(
        self,
        *,
        flow_id: str,
        chat_id: int,
        message_id: int,
        tag: str,
    ) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO telegram_flow_messages (flow_id, chat_id, message_id, tag, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(flow_id, chat_id, message_id) DO UPDATE SET
                    tag=excluded.tag,
                    created_at=excluded.created_at
                """,
                (
                    flow_id,
                    chat_id,
                    message_id,
                    tag,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list_telegram_flow_messages(
        self,
        *,
        flow_id: str,
        tag: str | None = None,
    ) -> list[TrackedTelegramMessage]:
        self.initialize()
        query = """
            SELECT flow_id, chat_id, message_id, tag
            FROM telegram_flow_messages
            WHERE flow_id = ?
        """
        params: list[object] = [flow_id]
        if tag is not None:
            query += " AND tag = ?"
            params.append(tag)
        query += " ORDER BY created_at, message_id"
        with _connect(self._db_path) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            TrackedTelegramMessage(
                flow_id=row["flow_id"],
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                tag=row["tag"],
            )
            for row in rows
        ]

    def remove_telegram_flow_message(
        self,
        *,
        flow_id: str,
        chat_id: int,
        message_id: int,
    ) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                DELETE FROM telegram_flow_messages
                WHERE flow_id = ? AND chat_id = ? AND message_id = ?
                """,
                (flow_id, chat_id, message_id),
            )

    def clear_telegram_flow_messages(
        self,
        *,
        flow_id: str,
        tag: str | None = None,
    ) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            if tag is None:
                connection.execute(
                    "DELETE FROM telegram_flow_messages WHERE flow_id = ?",
                    (flow_id,),
                )
            else:
                connection.execute(
                    "DELETE FROM telegram_flow_messages WHERE flow_id = ? AND tag = ?",
                    (flow_id, tag),
                )

    def record_telegram_user_login(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> None:
        self.initialize()
        normalized_username = _optional_json_str(username)
        normalized_first_name = _optional_json_str(first_name)
        normalized_last_name = _optional_json_str(last_name)
        normalized_language_code = _optional_json_str(language_code)
        timestamp = datetime.now(UTC).isoformat()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO telegram_user_logins (
                    user_id, username, first_name, last_name, language_code, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    language_code=excluded.language_code,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    user_id,
                    normalized_username,
                    normalized_first_name,
                    normalized_last_name,
                    normalized_language_code,
                    timestamp,
                    timestamp,
                ),
            )

    def list_telegram_user_logins(self) -> list[TelegramUserLogin]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id, username, first_name, last_name, language_code, first_seen_at, last_seen_at
                FROM telegram_user_logins
                ORDER BY last_seen_at DESC, user_id ASC
                """
            ).fetchall()
        return [
            TelegramUserLogin(
                user_id=int(row["user_id"]),
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                language_code=row["language_code"],
                first_seen_at=str(row["first_seen_at"]),
                last_seen_at=str(row["last_seen_at"]),
            )
            for row in rows
        ]

    def grant_telegram_user_role(self, *, user_id: int, role: str) -> None:
        self.initialize()
        normalized_role = str(role).strip().lower()
        if not normalized_role:
            raise ValueError("Telegram role is required.")
        timestamp = datetime.now(UTC).isoformat()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO telegram_user_roles (user_id, role, assigned_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, role) DO NOTHING
                """,
                (user_id, normalized_role, timestamp),
            )

    def list_telegram_user_role_assignments(self) -> list[TelegramUserRoleAssignment]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id, role, assigned_at
                FROM telegram_user_roles
                ORDER BY role, user_id
                """
            ).fetchall()
        return [
            TelegramUserRoleAssignment(
                user_id=int(row["user_id"]),
                role=str(row["role"]),
                assigned_at=str(row["assigned_at"]),
            )
            for row in rows
        ]

    def list_telegram_user_role_memberships(self) -> dict[str, frozenset[int]]:
        assignments = self.list_telegram_user_role_assignments()
        memberships: dict[str, set[int]] = {"user": set()}
        for assignment in assignments:
            memberships.setdefault(assignment.role, set()).add(assignment.user_id)
        return {
            role_name: frozenset(sorted(user_ids))
            for role_name, user_ids in memberships.items()
        }

    def replace_telegram_user_roles(self, *, user_id: int, roles: tuple[str, ...]) -> None:
        self.initialize()
        normalized_roles = tuple(
            sorted(
                {
                    str(role).strip().lower()
                    for role in roles
                    if str(role).strip() and str(role).strip().lower() != "user"
                }
            )
        )
        timestamp = datetime.now(UTC).isoformat()
        with _connect(self._db_path) as connection:
            connection.execute("DELETE FROM telegram_user_roles WHERE user_id = ?", (user_id,))
            for role in normalized_roles:
                connection.execute(
                    """
                    INSERT INTO telegram_user_roles (user_id, role, assigned_at)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, role, timestamp),
                )

    def list_telegram_roles_for_user(self, *, user_id: int) -> tuple[str, ...]:
        self.initialize()
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT role
                FROM telegram_user_roles
                WHERE user_id = ?
                ORDER BY role ASC
                """,
                (user_id,),
            ).fetchall()
        return tuple(str(row["role"]) for row in rows)

    def list_telegram_admin_users(self) -> list[TelegramAdminUser]:
        login_map = {item.user_id: item for item in self.list_telegram_user_logins()}
        roles_by_user: dict[int, list[str]] = {}
        for assignment in self.list_telegram_user_role_assignments():
            roles_by_user.setdefault(assignment.user_id, []).append(assignment.role)
        users: list[TelegramAdminUser] = []
        all_user_ids = sorted(set(login_map) | set(roles_by_user))
        for user_id in all_user_ids:
            login = login_map.get(user_id)
            roles = tuple(sorted(set(roles_by_user.get(user_id, [])) | {"user"}))
            users.append(
                TelegramAdminUser(
                    id=user_id,
                    telegram_id=user_id,
                    username=None if login is None else login.username,
                    first_name=None if login is None else login.first_name,
                    last_name=None if login is None else login.last_name,
                    roles=roles,
                    first_seen_at=None if login is None else login.first_seen_at,
                    last_seen_at=None if login is None else login.last_seen_at,
                )
            )
        users.sort(key=lambda item: (item.last_seen_at or "", item.telegram_id), reverse=True)
        return users

    def save_pending_telegram_notification(
        self,
        *,
        notification_key: str,
        recipient_user_id: int,
        text: str,
        not_before_at: datetime,
    ) -> None:
        self.initialize()
        created_at = datetime.now(UTC).isoformat()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO pending_telegram_notifications (
                    notification_key, recipient_user_id, text, not_before_at, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(notification_key) DO UPDATE SET
                    recipient_user_id = excluded.recipient_user_id,
                    text = excluded.text,
                    not_before_at = excluded.not_before_at
                """,
                (
                    notification_key,
                    recipient_user_id,
                    text,
                    not_before_at.isoformat(),
                    created_at,
                ),
            )

    def get_pending_telegram_notification(
        self,
        *,
        notification_key: str,
    ) -> PendingTelegramNotification | None:
        self.initialize()
        with _connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT notification_key, recipient_user_id, text, not_before_at, created_at
                FROM pending_telegram_notifications
                WHERE notification_key = ?
                """,
                (notification_key,),
            ).fetchone()
        if row is None:
            return None
        return PendingTelegramNotification(
            key=str(row["notification_key"]),
            recipient_user_id=int(row["recipient_user_id"]),
            text=str(row["text"]),
            not_before_at=datetime.fromisoformat(str(row["not_before_at"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def list_pending_telegram_notifications(
        self,
        *,
        recipient_user_id: int | None = None,
    ) -> list[PendingTelegramNotification]:
        self.initialize()
        query = """
            SELECT notification_key, recipient_user_id, text, not_before_at, created_at
            FROM pending_telegram_notifications
        """
        params: list[object] = []
        if recipient_user_id is not None:
            query += " WHERE recipient_user_id = ?"
            params.append(recipient_user_id)
        query += " ORDER BY not_before_at ASC, created_at ASC"
        with _connect(self._db_path) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            PendingTelegramNotification(
                key=str(row["notification_key"]),
                recipient_user_id=int(row["recipient_user_id"]),
                text=str(row["text"]),
                not_before_at=datetime.fromisoformat(str(row["not_before_at"])),
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            for row in rows
        ]

    def remove_pending_telegram_notification(self, *, notification_key: str) -> None:
        self.initialize()
        with _connect(self._db_path) as connection:
            connection.execute(
                """
                DELETE FROM pending_telegram_notifications
                WHERE notification_key = ?
                """,
                (notification_key,),
            )

    def _upsert_lexeme(self, connection: sqlite3.Connection, *, headword: str) -> str:
        normalized_headword = _normalize_headword(headword)
        if not normalized_headword:
            raise ValueError("Learning item headword is required.")
        existing = connection.execute(
            """
            SELECT id
            FROM lexemes
            WHERE normalized_headword = ?
            """,
            (normalized_headword,),
        ).fetchone()
        if existing is not None:
            connection.execute(
                """
                UPDATE lexemes
                SET headword = ?
                WHERE id = ?
                """,
                (headword, existing["id"]),
            )
            return existing["id"]
        lexeme_id = normalized_headword.replace(" ", "-")
        suffix = 2
        while connection.execute(
            "SELECT 1 FROM lexemes WHERE id = ?",
            (lexeme_id,),
        ).fetchone() is not None:
            lexeme_id = f"{normalized_headword.replace(' ', '-')}-{suffix}"
            suffix += 1
        connection.execute(
            """
            INSERT INTO lexemes (id, headword, normalized_headword, part_of_speech, notes)
            VALUES (?, ?, ?, NULL, NULL)
            """,
            (lexeme_id, headword, normalized_headword),
        )
        return lexeme_id

    def _upsert_learning_item(
        self,
        connection: sqlite3.Connection,
        *,
        item: VocabularyItem,
        lexeme_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO learning_items (
                id, lexeme_id, display_word, display_translation, meaning_hint,
                image_ref, image_source, image_prompt, pixabay_search_query, source_fragment, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                lexeme_id=excluded.lexeme_id,
                display_word=excluded.display_word,
                display_translation=excluded.display_translation,
                meaning_hint=excluded.meaning_hint,
                image_ref=excluded.image_ref,
                image_source=excluded.image_source,
                image_prompt=excluded.image_prompt,
                pixabay_search_query=excluded.pixabay_search_query,
                source_fragment=excluded.source_fragment,
                is_active=excluded.is_active
            """,
            (
                item.id,
                lexeme_id,
                item.english_word,
                item.translation,
                item.meaning_hint,
                item.image_ref,
                item.image_source,
                item.image_prompt,
                item.pixabay_search_query,
                item.source_fragment,
                1 if item.is_active else 0,
            ),
        )

    def _row_to_vocabulary_item(self, row: sqlite3.Row) -> VocabularyItem:
        return VocabularyItem(
            id=row["id"],
            lexeme_id=row["lexeme_id"],
            english_word=row["english_word"],
            translation=row["translation"],
            topic_id=row["topic_id"],
            lesson_id=row["lesson_id"],
            meaning_hint=row["meaning_hint"],
            image_ref=row["image_ref"],
            image_source=row["image_source"],
            image_prompt=row["image_prompt"],
            pixabay_search_query=row["pixabay_search_query"],
            source_fragment=row["source_fragment"],
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

    def _row_to_add_words_flow(self, row: sqlite3.Row) -> AddWordsFlowState:
        draft = JsonDraftReader().read_data(json.loads(row["draft_json"]))
        raw_errors = json.loads(row["validation_errors_json"])
        errors = [ValidationError(**error) for error in raw_errors]
        return AddWordsFlowState(
            flow_id=row["flow_id"],
            editor_user_id=row["editor_user_id"],
            raw_text=row["raw_text"],
            draft_result=ImportLessonResult(
                draft=draft,
                validation=ValidationResult(errors=errors),
            ),
            stage=row["stage"],
            draft_output_path=Path(row["draft_output_path"]) if row["draft_output_path"] else None,
            final_output_path=Path(row["final_output_path"]) if row["final_output_path"] else None,
            image_review_flow_id=row["image_review_flow_id"],
        )

    def _row_to_image_review_flow(self, row: sqlite3.Row) -> ImageReviewFlowState:
        raw_items = json.loads(row["items_json"])
        items: list[ImageReviewItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            items.append(
                ImageReviewItem(
                    item_id=_required_json_str(raw_item.get("item_id", "")),
                    english_word=_required_json_str(raw_item.get("english_word", "")),
                    translation=_required_json_str(raw_item.get("translation", "")),
                    prompt=_required_json_str(raw_item.get("prompt", "")),
                    search_query=_optional_json_str(raw_item.get("search_query")),
                    search_page=int(raw_item.get("search_page", 1) or 1),
                    candidate_source_type=_optional_json_str(
                        raw_item.get("candidate_source_type")
                    ),
                    selected_candidate_index=raw_item.get("selected_candidate_index"),
                    approved_source_type=_optional_json_str(
                        raw_item.get("approved_source_type")
                    ),
                    needs_review=bool(raw_item.get("needs_review", True)),
                    skipped=bool(raw_item.get("skipped", False)),
                    candidates=[
                        ImageCandidate(
                            model_name=_required_json_str(candidate.get("model_name", "")),
                            image_ref=_required_json_str(candidate.get("image_ref", "")),
                            output_path=Path(_required_json_str(candidate.get("output_path", ""))),
                            prompt=_required_json_str(candidate.get("prompt", "")),
                            source_type=_required_json_str(
                                candidate.get("source_type", "generated")
                            ),
                            source_id=_optional_json_str(candidate.get("source_id")),
                            preview_url=_optional_json_str(candidate.get("preview_url")),
                            full_image_url=_optional_json_str(candidate.get("full_image_url")),
                            source_page_url=_optional_json_str(candidate.get("source_page_url")),
                            width=(
                                candidate.get("width")
                                if isinstance(candidate.get("width"), int)
                                else None
                            ),
                            height=(
                                candidate.get("height")
                                if isinstance(candidate.get("height"), int)
                                else None
                            ),
                        )
                        for candidate in raw_item.get("candidates", [])
                        if isinstance(candidate, dict)
                    ],
                )
            )
        return ImageReviewFlowState(
            flow_id=row["flow_id"],
            editor_user_id=row["editor_user_id"],
            content_pack=json.loads(row["content_pack_json"]),
            items=items,
            current_index=row["current_index"],
            output_path=Path(row["output_path"]) if row["output_path"] else None,
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

    def get_word_stats(self, user_id: int, item_id: str) -> WordStats | None:
        return self._store.get_word_stats(user_id, item_id)

    def save_word_stats(self, stats: WordStats) -> None:
        self._store.save_word_stats(stats)

    def award_weekly_points(
        self,
        *,
        user_id: int,
        word_id: str,
        mode: TrainingMode,
        level_up_delta: int,
        awarded_at: datetime,
    ) -> int:
        return self._store.award_weekly_points(
            user_id=user_id,
            word_id=word_id,
            mode=mode,
            level_up_delta=level_up_delta,
            awarded_at=awarded_at,
        )

    def update_goals_progress(
        self,
        *,
        user_id: int,
        word_id: str,
        topic_id: str,
        is_correct: bool,
        current_level: int,
    ) -> None:
        self._store.update_goals_progress(
            user_id=user_id,
            word_id=word_id,
            topic_id=topic_id,
            is_correct=is_correct,
            current_level=current_level,
        )

    def required_homework_level(self, *, user_id: int, item_id: str) -> int | None:
        return self._store.required_homework_level(user_id=user_id, item_id=item_id)

    def list_due_review_words(self, *, user_id: int) -> set[str]:
        return self._store.list_due_review_words(user_id=user_id)

    def get_homework_stage_mode(self, *, user_id: int, item_id: str) -> TrainingMode | None:
        return self._store.get_homework_stage_mode(user_id=user_id, item_id=item_id)

    def update_homework_word_progress(
        self,
        *,
        user_id: int,
        word_id: str,
        mode: TrainingMode,
        is_correct: bool,
        current_level: int,
    ) -> None:
        self._store.update_homework_word_progress(
            user_id=user_id,
            word_id=word_id,
            mode=mode,
            is_correct=is_correct,
            current_level=current_level,
        )


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


class SQLiteAddWordsFlowRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def save(self, flow: AddWordsFlowState) -> None:
        self._store.save_add_words_flow(flow)

    def get_active_by_user(self, user_id: int) -> AddWordsFlowState | None:
        return self._store.get_active_add_words_flow_by_user(user_id)

    def get_by_id(self, flow_id: str) -> AddWordsFlowState | None:
        return self._store.get_add_words_flow_by_id(flow_id)

    def discard_active_by_user(self, user_id: int) -> None:
        self._store.discard_active_add_words_flow_by_user(user_id)


class SQLiteImageReviewFlowRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def save(self, flow: ImageReviewFlowState) -> None:
        self._store.save_image_review_flow(flow)

    def get_active_by_user(self, user_id: int) -> ImageReviewFlowState | None:
        return self._store.get_active_image_review_flow_by_user(user_id)

    def get_by_id(self, flow_id: str) -> ImageReviewFlowState | None:
        return self._store.get_image_review_flow_by_id(flow_id)

    def discard_active_by_user(self, user_id: int) -> None:
        self._store.discard_active_image_review_flow_by_user(user_id)


class SQLiteTelegramFlowMessageRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self._store.track_telegram_flow_message(
            flow_id=flow_id,
            chat_id=chat_id,
            message_id=message_id,
            tag=tag,
        )

    def list(self, *, flow_id: str, tag: str | None = None) -> list[TrackedTelegramMessage]:
        return self._store.list_telegram_flow_messages(flow_id=flow_id, tag=tag)

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self._store.remove_telegram_flow_message(
            flow_id=flow_id,
            chat_id=chat_id,
            message_id=message_id,
        )

    def clear(self, *, flow_id: str, tag: str | None = None) -> None:
        self._store.clear_telegram_flow_messages(flow_id=flow_id, tag=tag)


class SQLiteTelegramUserLoginRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def record(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> None:
        self._store.record_telegram_user_login(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )

    def list(self) -> list[TelegramUserLogin]:
        return self._store.list_telegram_user_logins()


class SQLiteTelegramUserRoleRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def grant(self, *, user_id: int, role: str) -> None:
        self._store.grant_telegram_user_role(user_id=user_id, role=role)

    def replace(self, *, user_id: int, roles: tuple[str, ...]) -> None:
        self._store.replace_telegram_user_roles(user_id=user_id, roles=roles)

    def list_roles_for_user(self, *, user_id: int) -> tuple[str, ...]:
        return self._store.list_telegram_roles_for_user(user_id=user_id)

    def list_assignments(self) -> list[TelegramUserRoleAssignment]:
        return self._store.list_telegram_user_role_assignments()

    def list_memberships(self) -> dict[str, frozenset[int]]:
        return self._store.list_telegram_user_role_memberships()

    def list_users(self) -> list[TelegramAdminUser]:
        return self._store.list_telegram_admin_users()


class SQLitePendingTelegramNotificationRepository:
    def __init__(self, store: SQLiteContentStore) -> None:
        self._store = store

    def save(
        self,
        *,
        notification_key: str,
        recipient_user_id: int,
        text: str,
        not_before_at: datetime,
    ) -> None:
        self._store.save_pending_telegram_notification(
            notification_key=notification_key,
            recipient_user_id=recipient_user_id,
            text=text,
            not_before_at=not_before_at,
        )

    def get(self, *, notification_key: str) -> PendingTelegramNotification | None:
        return self._store.get_pending_telegram_notification(notification_key=notification_key)

    def list(self, *, recipient_user_id: int | None = None) -> list[PendingTelegramNotification]:
        return self._store.list_pending_telegram_notifications(recipient_user_id=recipient_user_id)

    def remove(self, *, notification_key: str) -> None:
        self._store.remove_pending_telegram_notification(notification_key=notification_key)
