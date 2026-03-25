#!/usr/bin/env bash
set -euo pipefail

host_home="${HOME}"
required_dirs=(
  "$host_home/.comfyui/models"
  "$host_home/.comfyui/output"
  "$host_home/.ollama"
)

for dir in "${required_dirs[@]}"; do
  mkdir -p "$dir"
  echo "Prepared host directory: $dir"
done
