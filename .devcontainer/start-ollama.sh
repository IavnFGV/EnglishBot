#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${OLLAMA_AUTOSTART:-1}" != "1" ]]; then
  echo "OLLAMA_AUTOSTART is disabled; skipping Ollama startup"
  exit 0
fi

base_url="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
tags_url="${base_url%/}/api/tags"
chat_model="${OLLAMA_PULL_MODEL:-}"

is_ready() {
  curl --silent --show-error --fail "$tags_url" >/dev/null 2>&1
}

if ! is_ready; then
  if pgrep -x ollama >/dev/null 2>&1; then
    echo "Ollama process exists but is not ready yet"
  else
    echo "Starting ollama serve"
    nohup ollama serve >/tmp/englishbot-ollama.log 2>&1 &
  fi
fi

for _ in $(seq 1 60); do
  if is_ready; then
    break
  fi
  sleep 1
done

if ! is_ready; then
  echo "Ollama did not become ready at $tags_url" >&2
  exit 1
fi

if [[ -z "$chat_model" ]]; then
  echo "OLLAMA_PULL_MODEL is empty; skipping model pull"
  exit 0
fi

if curl --silent --show-error --fail "$tags_url" | python -c '
import json
import sys

model_name = sys.argv[1]
payload = json.load(sys.stdin)
models = payload.get("models", [])
found = any(model.get("name") == model_name for model in models)
raise SystemExit(0 if found else 1)
' "$chat_model"
then
  echo "Ollama model already present: $chat_model"
  exit 0
fi

echo "Pulling Ollama model: $chat_model"
ollama pull "$chat_model"
