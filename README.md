# EnglishBot

Starter repository for a Telegram bot in Python with a ready-to-use Dev Container.

## What's included

- Python 3.12
- Application skeleton in `src/englishbot`
- Dev Container configuration in `.devcontainer/`
- Baseline dependencies for a Telegram bot
- Lint/format tooling configuration (`ruff`)

## Quick start in VS Code Dev Container (recommended)

If you work in a Dev Container, you usually **do not need a virtual environment** (`.venv`).
The container itself is already an isolated environment.

1. Open the project in VS Code.
2. Install the **Dev Containers** extension.
3. Run **Dev Containers: Reopen in Container**.
4. Dependencies are installed automatically via `postCreateCommand`.
5. Run the bot:

```bash
python -m englishbot
```

## Quick start (local, outside container)

If you prefer local development on your host machine, use a virtual environment:

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Create `.env` from the example:

```bash
cp .env.example .env
```

4. Set your Telegram bot token in `.env`.

5. Run the bot:

```bash
python -m englishbot
```

## Next steps

- Define business requirements and key scenarios
- Add command and conversation routing
- Add state storage if needed
- Add tests
