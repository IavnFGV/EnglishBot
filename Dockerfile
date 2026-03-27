FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY prompts ./prompts
COPY content/demo ./content/demo

RUN python -m pip install --upgrade pip \
    && python -m pip install -e '.[llm]'

CMD ["python", "-m", "englishbot"]
