FROM mcr.microsoft.com/devcontainers/python:3-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /tmp/englishbot-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg zstd \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

RUN mkdir -p src/englishbot \
    && touch src/englishbot/__init__.py

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
    && python -m pip install '.[dev,llm]'

WORKDIR /workspaces/EnglishBot
