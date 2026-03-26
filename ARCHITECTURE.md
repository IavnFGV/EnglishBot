# Architecture

EnglishBot is a modular monolith with a domain/application/infrastructure split.

The current codebase should be treated as a working POC with real editor and learner flows, not just a toy training MVP.

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
- Start add-words flow from raw teacher/parent text
- Edit extracted draft text
- Approve, publish, and enrich a draft with image prompts
- Run image review for newly imported or already published words
- Edit a published word after release
- Edit a published word image after release

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
- Support editor workflows for add-words, image review, published-word editing, and published-image editing

The adapter does not contain business rules. It only maps Telegram updates to application service calls.

## Storage abstraction

Repository protocols isolate the application layer from persistence:

- `TopicRepository`
- `LessonRepository`
- `VocabularyRepository`
- `UserProgressRepository`
- `SessionRepository`

The current implementation still uses in-memory learner state and file-backed JSON content packs. That is acceptable for the POC, but it is not the target long-term persistence model.

Current simplifications:

- in-memory repositories are used instead of durable persistence
- medium mode uses typed input with a shuffled-letter hint instead of a custom letter-assembly UI
- content is still stored in JSON files rather than a normalized database
- the same logical word may still appear in multiple packs instead of being canonically deduplicated

Likely long-term storage direction:

- canonical vocabulary table
- topic and lesson tables
- many-to-many links between vocabulary and topic/lesson groupings
- durable learner/session storage
- explicit review/publication/image state

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

## Lesson Extraction Pipeline

Messy teacher-provided lesson text is handled by a separate import pipeline instead of rigid text parsing.

Stages:

- raw input ingestion
- semantic extraction into a draft result
- strict validation in code
- canonicalization into content-pack JSON
- file writing

Key components:

- `LessonExtractionClient`: abstraction for semantic extraction
- `LessonExtractionDraft`: structured draft schema from free-form text
- `LessonExtractionValidator`: code-level validation that returns structured errors
- `DraftToContentPackCanonicalizer`: stable slug/id generation and canonical normalization
- `JsonContentPackWriter`: writes canonical packs to disk
- `LessonImportPipeline`: orchestration layer joining the steps together

The draft schema supports:

- topic title
- optional lesson title
- vocabulary items with English word, translation, optional notes, optional image prompt, and source fragment
- warnings, unparsed lines, and confidence notes

This keeps future OCR compatibility straightforward: OCR can feed raw text or an extraction draft into the same downstream validation, canonicalization, and writing path.

The current implementation already supports real Ollama-backed extraction and prompt generation, while tests still stay deterministic through fake clients and app-level harnesses.

## Editor and Content Curation Flow

The current editor flow is already a first-class part of the application:

- import raw text
- parse line by line into vocabulary pairs
- review the draft
- edit the draft text
- publish directly or continue to image generation
- auto-generate or manually review images
- later edit a published word or a published word image

This flow is intentionally application-driven and tested independently from Telegram where possible.

## Testing Strategy

The project favors application-level integration-style tests over Telegram API tests.

Important consequences:

- core product behavior is tested through harnesses and use cases
- Telegram handlers are tested only as a thin transport adapter
- long-running or external integrations such as Ollama and ComfyUI can be covered by optional live integration tests without making the main test suite brittle

This approach is critical for reproducing beta issues quickly from concrete inputs.

## Next Product Direction

The next architectural slice is not another content-management variant. It is proactive learner interaction.

Target scenario:

- an admin or parent uploads and curates words
- the bot then interacts with Teia in a shared Telegram chat
- the bot periodically invites Teia to review or continue learning
- Teia responds directly in chat

This implies the next design pressure points will be:

- group-chat aware routing
- scheduled review invitations
- durable learner state
- stronger separation between editor actions and learner-facing chat behavior
