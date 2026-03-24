# EnglishBot

Starter repository for a Telegram bot in Python with a ready-to-use Dev Container.

## What's included

- Python 3.12
- Application skeleton in `src/englishbot`
- Dev Container configuration in `.devcontainer/`
- Baseline dependencies for a Telegram bot
- Lint/format tooling configuration (`ruff`)

## Quick start (local)

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

## Quick start in VS Code Dev Container

1. Open the project in VS Code.
2. Install the **Dev Containers** extension.
3. Run **Dev Containers: Reopen in Container**.
4. After the container starts, install dependencies:

```bash
pip install -e .[dev]
```

5. Run the bot:

```bash
python -m englishbot
```

## Next steps

- Define business requirements and key scenarios
- Add command and conversation routing
- Add state storage if needed
- Add tests
