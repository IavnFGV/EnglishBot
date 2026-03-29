FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

ARG OLLAMA_INSTALL=1
ARG COMFYUI_INSTALL=1
ARG PYTHON_EXTRAS=dev,llm
ARG COMFYUI_REPO=https://github.com/Comfy-Org/ComfyUI.git
ARG COMFYUI_REF=master
ARG COMFYUI_TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /tmp/englishbot-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg git sqlite3 zstd \
    && if [ "${OLLAMA_INSTALL}" = "1" ]; then \
         curl -fsSL https://ollama.com/install.sh | sh; \
       fi \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "${COMFYUI_INSTALL}" = "1" ]; then \
      git clone --depth 1 --branch "${COMFYUI_REF}" "${COMFYUI_REPO}" /opt/ComfyUI \
      && python -m venv /opt/ComfyUI/venv \
      && /opt/ComfyUI/venv/bin/python -m pip install --upgrade pip \
      && /opt/ComfyUI/venv/bin/python -m pip install \
        torch torchvision torchaudio \
        --index-url "${COMFYUI_TORCH_INDEX_URL}" \
      && /opt/ComfyUI/venv/bin/python -m pip install -r /opt/ComfyUI/requirements.txt \
      && mkdir -p /opt/ComfyUI/user /opt/ComfyUI/input /opt/ComfyUI/temp /opt/ComfyUI/output \
      && chown -R vscode:vscode /opt/ComfyUI; \
    fi

COPY pyproject.toml README.md ./

RUN mkdir -p src/englishbot \
    && touch src/englishbot/__init__.py

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
    && python -m pip install ".[${PYTHON_EXTRAS}]"

WORKDIR /workspaces/EnglishBot
