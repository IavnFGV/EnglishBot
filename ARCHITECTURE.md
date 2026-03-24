# Architecture

EnglishBot is a simple modular monolith with a domain/application/infrastructure split.

## Layers

- `englishbot.domain`: core entities and repository contracts
- `englishbot.application`: small use cases and focused services for topic listing, lesson listing, session startup, question retrieval, answer submission, selection, checking, and summary calculation
- `englishbot.infrastructure`: in-memory repositories and JSON-loaded demo content packs
- `englishbot.bot`: Telegram adapter with thin handlers
- `englishbot.bootstrap`: composition root for wiring dependencies

## Main entities

- `Topic`: top-level vocabulary grouping
- `Lesson`: optional school-material grouping inside a topic
- `VocabularyItem`: a word card with English text, translation, topic, optional lesson, and image reference
- `UserProgress`: per-user counters for answers and exposure
- `TrainingSession`: active session state, deterministic selected items, current cursor, completion status, and answer history
- `TrainingQuestion`, `CheckResult`, `SessionSummary`: value objects used by the application layer

## Use cases

- List topics
- List lessons for a topic
- Start a training session by topic, optional lesson, and mode
- Select words for the session, preferring unseen words first
- Generate questions for easy, medium, and hard modes
- Check an answer and persist user progress
- Finish a session and return a summary

## Application responsibilities

- `ListTopicsUseCase`: learner topic discovery
- `ListLessonsByTopicUseCase`: lesson discovery for the selected topic with topic-only fallback
- `ValidateTopicLessonUseCase`: defensive check that a lesson belongs to the selected topic
- `StartTrainingSessionUseCase`: validates topic and optional lesson, applies topic/lesson-aware word selection, creates a deterministic session, and returns the first question
- `GetCurrentQuestionUseCase`: resolves the current session item into a question
- `SubmitAnswerUseCase`: checks the answer, updates progress, advances the session, and returns either the next question or the final summary
- `UnseenFirstWordSelector`: replaceable word selection strategy for the MVP
- `QuestionFactory`: mode-aware question generation
- `AnswerChecker`: answer normalization and correctness evaluation
- `SessionSummaryCalculator`: final session result calculation

## Session lifecycle

- A session stores the exact selected vocabulary item ids in order
- `current_index` points to the next unanswered item
- `answer_history` preserves submitted answers and correctness flags
- once the last answer is recorded, the session becomes completed
- completed sessions reject further question access and extra answers defensively

## Telegram adapter responsibilities

- Convert `/start` into topic selection
- Handle topic, lesson, and mode callbacks
- Render multiple-choice options only for easy mode
- Accept free-text answers for medium and hard modes
- Display feedback and session summary

The adapter does not contain business rules. It only maps Telegram updates to application service calls.

## Storage abstraction

Repository protocols isolate the application layer from persistence:

- `TopicRepository`
- `LessonRepository`
- `VocabularyRepository`
- `UserProgressRepository`
- `SessionRepository`

The current implementation uses in-memory storage for a clean MVP slice. A future database can replace only the infrastructure layer without changing domain or Telegram code.

Current simplifications:

- in-memory repositories are used instead of durable persistence
- medium mode uses typed input with a shuffled-letter hint instead of a custom letter-assembly UI
- image support is represented by `image_ref` placeholders rather than real Telegram media files
- content packs are loaded from local JSON files rather than a database or admin-managed import flow

## Content packs

Demo content is loaded from JSON files under `content/demo/`.

Each pack contains:

- `topic`: object with `id` and `title`
- `lessons`: array of lesson objects with `id` and `title`
- `vocabulary_items`: array of vocabulary objects with `id`, `english_word`, `translation`, optional `lesson_id`, optional `image_ref`, and optional `is_active`

The loader validates:

- top-level structure
- required string fields
- lesson references inside vocabulary items
- consistent topic ownership inside the pack

## Future admin bot and import pipeline

The future admin bot can reuse the same domain model and application services while adding a different Telegram entrypoint and admin-specific use cases for content editing, approval, and scheduling.

A content import pipeline can plug into the infrastructure/application boundary by parsing teacher materials into `Topic`, `Lesson`, and `VocabularyItem` records, then saving them through repository implementations. That keeps parsing concerns separate from the learner bot flow.
