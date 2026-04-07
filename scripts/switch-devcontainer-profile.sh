#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
devcontainer_dir="$repo_root/.devcontainer"

profile="${1:-default}"

case "$profile" in
  cpu)
    cp "$devcontainer_dir/devcontainer.cpu.json" "$devcontainer_dir/devcontainer.json"
    ;;
  gpu)
    cp "$devcontainer_dir/devcontainer.gpu.json" "$devcontainer_dir/devcontainer.json"
    ;;
  default)
    cp "$devcontainer_dir/devcontainer.default.json" "$devcontainer_dir/devcontainer.json"
    ;;
  *)
    echo "Usage: $0 [default|cpu|gpu]" >&2
    exit 1
    ;;
esac

echo "Switched devcontainer profile to $profile"
