#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command="${1:-status}"
service="${2:-all}"

ollama_base_url="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
ollama_tags_url="${ollama_base_url%/}/api/tags"
ollama_log_path="${OLLAMA_LOG_PATH:-/tmp/englishbot-ollama.log}"

comfyui_base_url="${COMFYUI_BASE_URL:-http://127.0.0.1:8188}"
comfyui_log_path="${COMFYUI_LOG_PATH:-/tmp/englishbot-comfyui.log}"

usage() {
  cat <<'EOF'
Usage:
  bash .devcontainer/manage-generation-services.sh status [all|ollama|comfyui]
  bash .devcontainer/manage-generation-services.sh start [all|ollama|comfyui]
  bash .devcontainer/manage-generation-services.sh restart [all|ollama|comfyui]
  bash .devcontainer/manage-generation-services.sh logs [all|ollama|comfyui]
EOF
}

is_ollama_ready() {
  curl --silent --show-error --fail "$ollama_tags_url" >/dev/null 2>&1
}

is_comfyui_ready() {
  curl --silent --show-error --fail "$comfyui_base_url" >/dev/null 2>&1
}

print_ollama_status() {
  if is_ollama_ready; then
    echo "ollama: ready ($ollama_tags_url)"
  elif pgrep -x ollama >/dev/null 2>&1; then
    echo "ollama: process running, not ready ($ollama_tags_url)"
  else
    echo "ollama: stopped"
  fi
}

print_comfyui_status() {
  if is_comfyui_ready; then
    echo "comfyui: ready ($comfyui_base_url)"
  elif pgrep -f "ComfyUI.*main.py" >/dev/null 2>&1; then
    echo "comfyui: process running, not ready ($comfyui_base_url)"
  else
    echo "comfyui: stopped"
  fi
}

start_ollama() {
  bash "$script_dir/start-ollama.sh"
}

start_comfyui() {
  bash "$script_dir/start-comfyui.sh"
}

stop_ollama() {
  pkill -f "ollama serve" >/dev/null 2>&1 || true
  pkill -x ollama >/dev/null 2>&1 || true
}

stop_comfyui() {
  pkill -f "ComfyUI.*main.py" >/dev/null 2>&1 || true
}

show_logs() {
  local name="$1"
  local path="$2"
  echo "=== $name log: $path ==="
  if [[ -f "$path" ]]; then
    tail -n 80 "$path"
  else
    echo "log file not found"
  fi
}

case "$command" in
  status)
    case "$service" in
      all)
        print_ollama_status
        print_comfyui_status
        ;;
      ollama)
        print_ollama_status
        ;;
      comfyui)
        print_comfyui_status
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  start)
    case "$service" in
      all)
        start_ollama
        start_comfyui
        ;;
      ollama)
        start_ollama
        ;;
      comfyui)
        start_comfyui
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  restart)
    case "$service" in
      all)
        stop_ollama
        stop_comfyui
        start_ollama
        start_comfyui
        ;;
      ollama)
        stop_ollama
        start_ollama
        ;;
      comfyui)
        stop_comfyui
        start_comfyui
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  logs)
    case "$service" in
      all)
        show_logs "ollama" "$ollama_log_path"
        show_logs "comfyui" "$comfyui_log_path"
        ;;
      ollama)
        show_logs "ollama" "$ollama_log_path"
        ;;
      comfyui)
        show_logs "comfyui" "$comfyui_log_path"
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  *)
    usage
    exit 1
    ;;
esac
