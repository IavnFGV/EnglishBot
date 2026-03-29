#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
devcontainer_dir="$repo_root/.devcontainer"

mode="${1:-off}"

case "$mode" in
  on)
    cp "$devcontainer_dir/local-ai.on.env" "$devcontainer_dir/local-ai.env"
    ;;
  off)
    cp "$devcontainer_dir/local-ai.off.env" "$devcontainer_dir/local-ai.env"
    ;;
  *)
    echo "Usage: $0 [on|off]" >&2
    exit 1
    ;;
esac

echo "Switched local AI mode to $mode"
echo "Rebuild/Reopen devcontainer to apply env-file changes"
