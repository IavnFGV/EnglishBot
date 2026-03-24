# Architecture

EnglishBot is a simple modular monolith with a domain/application/infrastructure split.

## Layers

- `englishbot.domain`: core entities and repository contracts
- `englishbot.application`: small use cases and focused services for topic listing, session startup, question retrieval, answer submission, selection, checking, and summary calculation
- `englishbot.infrastructure`: in-memory repositories and demo seed data
- `englishbot.bot`: Telegram adapter with thin handlers
- `englishbot.bootstrap`: composition root for wiring dependencies

## Main entities

- `Topic`: vocabulary grouping
- `Lesson`: optional extra grouping inside a topic
- `VocabularyItem`: a word card with English text, translation, topic, optional lesson, and image reference
- `UserProgress`: per-user counters for answers and exposure
- `TrainingSession`: active session state, deterministic selected items, current cursor, completion status, and answer history
- `TrainingQuestion`, `CheckResult`, `SessionSummary`: value objects used by the application layer

## Use cases

- List topics
- Start a training session by topic and mode
- Select words for the session, preferring unseen words first
- Generate questions for easy, medium, and hard modes
- Check an answer and persist user progress
- Finish a session and return a summary

## Application responsibilities

- `ListTopicsUseCase`: learner topic discovery
- `StartTrainingSessionUseCase`: validates topic, applies topic/lesson-aware word selection, creates a deterministic session, and returns the first question
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
- Handle topic and mode callbacks
- Render multiple-choice options only for easy mode
- Accept free-text answers for medium and hard modes
- Display feedback and session summary

The adapter does not contain business rules. It only maps Telegram updates to application service calls.

## Storage abstraction

Repository protocols isolate the application layer from persistence:

- `TopicRepository`
- `VocabularyRepository`
- `UserProgressRepository`
- `SessionRepository`

The current implementation uses in-memory storage for a clean MVP slice. A future database can replace only the infrastructure layer without changing domain or Telegram code.

Current simplifications:

- in-memory repositories are used instead of durable persistence
- medium mode uses typed input with a shuffled-letter hint instead of a custom letter-assembly UI
- image support is represented by `image_ref` placeholders rather than real Telegram media files
- lesson-aware filtering exists in the application/storage layers even though the learner UI does not yet expose lesson selection

## Future admin bot and import pipeline

The future admin bot can reuse the same domain model and application services while adding a different Telegram entrypoint and admin-specific use cases for content editing, approval, and scheduling.

A content import pipeline can plug into the infrastructure/application boundary by parsing teacher materials into `Topic`, `Lesson`, and `VocabularyItem` records, then saving them through repository implementations. That keeps parsing concerns separate from the learner bot flow.
