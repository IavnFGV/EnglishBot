# AGENTS.md

## Environment Mapping

This repository may be opened in two environments:

- Host workspace: `/workspace/EnglishBot`
- Devcontainer workspace: `/workspaces/EnglishBot`

Treat these as the same repository root.

## Path Rules

- Prefer repository-relative paths in commands, scripts, and explanations.
- Prefer `.devcontainer/...`, `src/...`, `docs/...`, `scripts/...` over hardcoded absolute paths.
- Do not hardcode `/workspace/EnglishBot` in repo scripts.
- Do not hardcode `/workspaces/EnglishBot` in repo scripts.
- If an absolute path is required for explanation or debugging, clarify whether it is the host or devcontainer path.

## Container-Specific Paths

Inside the devcontainer, use these locations:

- Codex state: `/home/vscode/.codex`
- Workspace root: `/workspaces/EnglishBot`

## Host-Specific Paths

On the host, the workspace root is:

- `/workspace/EnglishBot`

## Script Conventions

- In shell scripts, derive the repository root from the script location instead of assuming an absolute workspace path.
- For repo files, use paths relative to the repo root whenever possible.
- When a task may run both on the host and in the devcontainer, write commands so they work from the current repository root.

## Devcontainer Notes

- Codex sessions are shared via a bind mount from the host into `/home/vscode/.codex`.
- Avoid assumptions that Docker named volumes are host directories.

## Docker Build Conventions

- Keep stable Docker layers early and frequently changing metadata late.
- Do not place changing build metadata such as git SHA, branch name, build timestamp, or commit-derived `ARG`/`ENV` near the top of the `Dockerfile`.
- Prefer adding build metadata as one of the last layers, ideally right before `CMD`, so Docker cache remains effective for package install and dependency layers.

## Logging Conventions

Use standard Python `logging` with one shared formatter configured at application startup:

- format: `%(asctime)s %(levelname)s [%(name)s] %(message)s`
- configure logging once at the application entrypoint
- prefer module-level loggers via `logging.getLogger(__name__)`

For service and use-case methods:

- log method entry and exit through a decorator, not by hand in every method
- use `englishbot.logging_utils.logged_service_call(...)` for atomic service calls
- include only meaningful inputs in decorator logs
- use transforms to log compact derived fields like `item_count`, `session_id`, `mode`, `answer_length`
- use `result=...` in the decorator to log meaningful outputs like `is_valid`, `error_count`, `session_completed`, `item_id`
- do not log `self`, `cls`, or large raw payloads directly unless needed for debugging

Keep direct logs only for:

- intermediate branch decisions
- warnings on invalid or suspicious states
- exceptions
- low-level repository diagnostics
- adapter-layer events such as Telegram updates

Recommended pattern:

```python
from englishbot.logging_utils import logged_service_call


@logged_service_call(
    "SomeUseCase.execute",
    include=("user_id", "topic_id"),
    transforms={"items": lambda value: {"item_count": len(value)}},
    result=lambda value: {"result_count": len(value)},
)
def execute(...):
    ...
```

Do not:

- duplicate the same start/done logs manually inside decorated methods
- put business-event logging only in Telegram handlers while leaving application services silent
- dump full objects into logs when a compact derived field is enough

## Startup Conventions

Application startup should be explicit and centralized:

- keep one entrypoint for the bot runtime in `src/.../__main__.py`
- load `.env` at startup
- build settings from environment
- configure logging before building services
- create and register an explicit asyncio event loop before `run_polling()` on modern Python

Current bot startup pattern:

```bash
python -m englishbot
```

Expected responsibilities of `__main__.py`:

- `load_dotenv()`
- `Settings.from_env()`
- `configure_logging(...)`
- build the Telegram application
- create `asyncio.new_event_loop()`
- `asyncio.set_event_loop(loop)`
- `app.run_polling()`
- close the loop in `finally`

CLI startup conventions:

- prefer `typer` for user-facing CLI tools
- keep argument parsing and orchestration in the CLI module
- keep business logic in application/importing services, not inside CLI parsing code
- call shared `configure_logging(...)` from CLI commands

Current import CLI pattern:

```bash
python -m englishbot.import_lesson_text --help
python -m englishbot.import_lesson_text --input lesson.txt --output content/custom/topic.json
```

CLI modules should:

- define a `typer.Typer(...)` app
- expose one clear command for the task
- validate option values early
- return machine-readable validation errors when possible
- exit with non-zero code on validation failure

## Configuration Conventions

Runtime configuration must be centralized:

- use `englishbot.config.RuntimeConfigService` as the single source for environment-backed settings
- build typed `Settings` through `Settings.from_config_service(...)` or `Settings.from_env()`
- when code needs a config default for URLs, model names, prompt paths, timeouts, API keys, or file paths, read it through the config service instead of calling `os.getenv(...)` directly
- if a setting needs to become editable, add it to the centralized config service and use its `set(...)/update(...)/save()` flow rather than introducing ad hoc file readers
- treat model names, prompt paths, and related file-backed parameters the same way as any other runtime setting
- in tests, prefer injecting a prepared `RuntimeConfigService` over mutating process env vars; keep env precedence tests focused in config-service tests

Do not:

- call `os.getenv(...)` directly in runtime modules outside `englishbot.config`
- keep separate one-off config files for individual features when the value can live in the centralized config service
- add new env-backed settings in constructors without registering and reading them through the config service


## Additional notes 

Do NOT:
- build microservices
- introduce event buses or message brokers
- add unnecessary CQRS/event sourcing
- put business logic into Telegram handlers
- hardcode vocabulary inside handlers
- tightly couple session logic to Telegram callback payloads
- skip tests for domain/application services

## Telegram UX Conventions

For Telegram flows that trigger background or long-running work:

- always inform the user that work has started
- do not leave the user waiting silently while LLM, import, image generation, or file-processing steps are running
- send a short status message before the expensive step starts
- when possible, update progress with concrete counters such as `processed 3/20`, `generated 2/5`, `validated 18/18`
- prefer editing one status/summary message over sending many noisy progress messages
- if a flow is step-based, show the current stage explicitly, for example:
  - `Parsing draft`
  - `Generating prompts`
  - `Reviewing images 4/12`
  - `Publishing content pack`
- on failure, replace the in-progress status with a clear error state instead of leaving the last visible message as "working"
- on success, replace the in-progress status with a short completion summary

For editor/import flows specifically:

- acknowledge the uploaded text immediately
- show draft extraction status while parsing is running
- show item counts in previews and summaries
- for image review or generation, keep one persistent summary message and update its counters as the flow advances
- when temporary Telegram editor/review messages need cleanup, reuse the shared tracked-message registry in the bot (`flow_id + tag`) instead of adding one-off delete logic
- prefer adding a new tag to the existing cleanup mechanism over introducing separate ad hoc state for each Telegram subflow


# Testing is mandatory.
Do not substitute test coverage with helper scripts, demo scripts, CLI flows, or manual verification notes.
For every scenario implemented, add pytest coverage.
If a scenario is hard to test, simplify the production code until it becomes testable.
