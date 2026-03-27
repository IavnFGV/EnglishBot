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
- `Lexeme`: one global word entry identified by normalized headword
- `VocabularyItem`: the actual teachable learning item with translation, hint, image, prompt, and source fragment
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

The runtime learner/editor state now uses SQLite with a normalized content split:

- `lexemes`
- `learning_items`
- `topic_learning_items`
- `lesson_learning_items`

The JSON content packs are still used as import/export artifacts, but not as the runtime source of truth.

Current simplifications:

- in-memory repositories are used instead of durable persistence
- medium mode uses typed input with a shuffled-letter hint instead of a custom letter-assembly UI
- full sense-level dictionary modeling is intentionally postponed
- ambiguity is still handled at the `learning_item` level through translation and optional hint text

Behavioral rule:

- learner sessions, answer history, progress, and image review use `learning_item.id`
- topics and lessons reference learning items through relation tables rather than owning the meaning directly

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
- smart semantic extraction into a draft result when the external AI capability is available
- fallback template-based extraction when the AI capability is unavailable or fails
- strict validation in code
- canonicalization into content-pack JSON
- file writing

Key components:

- `SmartLessonParsingGateway`: thin boundary for external AI-backed parsing
- `TemplateLessonFallbackParser`: simple local fallback parser for obvious line formats
- `LessonExtractionClient`: low-level extraction client used behind the smart parsing boundary
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

Behavioral rule:

- AI parsing is optional and external
- learner flows must not depend on AI availability
- admin import remains synchronous
- when smart parsing fails, the pipeline produces a fallback draft with explicit warnings and unparsed lines instead of crashing the flow

The current implementation supports real Ollama-backed extraction behind an explicit AI boundary, graceful fallback to local parsing, and deterministic tests through fakes and app-level harnesses.

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

## Image Generation Boundary

Image generation now follows the same resilience rule as lesson parsing:

- local AI image generation is optional and external
- editor flows must keep working when the external image node is unavailable
- fallback behavior should stay explicit and readable

Current structure:

- `ComfyUIImageGenerationGateway`: thin boundary for the external ComfyUI capability
- `ResilientImageGenerator`: explicit smart-or-fallback orchestration
- `LocalPlaceholderImageGenerationClient`: simple local fallback renderer
- `ContentPackImageEnricher`: applies resilient generation to published content packs
- `ImageReviewFlowHarness`: keeps image review usable even when generated candidates come from fallback mode

Behavioral rule:

- if ComfyUI is healthy, the app uses normal local AI generation
- if ComfyUI is unavailable, times out, or fails, the app falls back to placeholder images
- the editor can still search Pixabay, edit prompts, or upload a custom image
- learner flows do not depend on ComfyUI availability

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
