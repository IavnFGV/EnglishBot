#!/usr/bin/env bash
set -euo pipefail

ensure_owned_dir() {
  local target_dir="$1"
  if [[ ! -e "$target_dir" ]]; then
    mkdir -p "$target_dir"
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R vscode:vscode "$target_dir" || true
  else
    chown -R vscode:vscode "$target_dir" || true
  fi
}

ensure_owned_dir_if_exists() {
  local target_dir="$1"
  if [[ ! -e "$target_dir" ]]; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R vscode:vscode "$target_dir" || true
  else
    chown -R vscode:vscode "$target_dir" || true
  fi
}

ensure_owned_dir "/home/vscode/.ollama"
ensure_owned_dir "/home/vscode/.cache/pip"
ensure_owned_dir "/home/vscode/.codex"

# ComfyUI directories should be handled only when ComfyUI is installed in this profile.
ensure_owned_dir_if_exists "/opt/ComfyUI"
ensure_owned_dir_if_exists "/opt/ComfyUI/user"
ensure_owned_dir_if_exists "/opt/ComfyUI/input"
ensure_owned_dir_if_exists "/opt/ComfyUI/temp"
ensure_owned_dir_if_exists "/opt/ComfyUI/output"
