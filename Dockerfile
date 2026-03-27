FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

RUN python - <<'PY' > /tmp/requirements.txt
import tomllib
from pathlib import Path

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
requirements = list(data["project"].get("dependencies", []))
requirements.extend(data["project"].get("optional-dependencies", {}).get("llm", []))
print("\n".join(requirements))
PY

RUN python -m pip install -r /tmp/requirements.txt

COPY src ./src
COPY prompts ./prompts
COPY content/demo ./content/demo

RUN python -m pip install --no-deps .

ARG ENGLISHBOT_GIT_SHA=unknown
ARG ENGLISHBOT_GIT_BRANCH=unknown
ARG ENGLISHBOT_BUILD_VERSION=unknown
ARG ENGLISHBOT_BUILD_NUMBER=0

ENV ENGLISHBOT_BUILD_VERSION=${ENGLISHBOT_BUILD_VERSION} \
    ENGLISHBOT_BUILD_NUMBER=${ENGLISHBOT_BUILD_NUMBER} \
    ENGLISHBOT_GIT_SHA=${ENGLISHBOT_GIT_SHA} \
    ENGLISHBOT_GIT_BRANCH=${ENGLISHBOT_GIT_BRANCH}

CMD ["python", "-m", "englishbot"]
