# Architecture

EnglishBot is a simple modular monolith with a domain/application/infrastructure split.

## Layers

- `englishbot.domain`: core entities and repository contracts
- `englishbot.application`: training use cases and stateless services for selection, question generation, and answer checking
- `englishbot.infrastructure`: in-memory repositories and demo seed data
- `englishbot.bot`: Telegram adapter with thin handlers
- `englishbot.bootstrap`: composition root for wiring dependencies

## Main entities

- `Topic`: vocabulary grouping
- `Lesson`: optional extra grouping inside a topic
- `VocabularyItem`: a word card with English text, translation, topic, optional lesson, and image reference
- `UserProgress`: per-user counters for answers and exposure
- `TrainingSession`: active session state and answer history
- `TrainingQuestion`, `CheckResult`, `SessionSummary`: value objects used by the application layer

## Use cases

- List topics
- Start a training session by topic and mode
- Select words for the session, preferring unseen words first
- Generate questions for easy, medium, and hard modes
- Check an answer and persist user progress
- Finish a session and return a summary

## Telegram adapter responsibilities

- Convert `/start` into topic selection
- Handle topic and mode callbacks
- Render multiple-choice options for easy and medium modes
- Accept free-text answers for hard mode
- Display feedback and session summary

The adapter does not contain business rules. It only maps Telegram updates to application service calls.

## Storage abstraction

Repository protocols isolate the application layer from persistence:

- `TopicRepository`
- `VocabularyRepository`
- `UserProgressRepository`
- `SessionRepository`

The current implementation uses in-memory storage for a clean MVP slice. A future database can replace only the infrastructure layer without changing domain or Telegram code.

## Future admin bot and import pipeline

The future admin bot can reuse the same domain model and application services while adding a different Telegram entrypoint and admin-specific use cases for content editing, approval, and scheduling.

A content import pipeline can plug into the infrastructure/application boundary by parsing teacher materials into `Topic`, `Lesson`, and `VocabularyItem` records, then saving them through repository implementations. That keeps parsing concerns separate from the learner bot flow.
