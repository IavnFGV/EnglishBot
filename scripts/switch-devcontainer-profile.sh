#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
devcontainer_dir="$repo_root/.devcontainer"

profile="${1:-default}"

show_profile() {
  local active_file="$devcontainer_dir/devcontainer.json"
  if cmp -s "$active_file" "$devcontainer_dir/devcontainer.default.json"; then
    echo "default"
    return 0
  fi
  if cmp -s "$active_file" "$devcontainer_dir/devcontainer.cpu.json"; then
    echo "cpu"
    return 0
  fi
  if cmp -s "$active_file" "$devcontainer_dir/devcontainer.gpu.json"; then
    echo "gpu"
    return 0
  fi
  echo "custom"
}

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
  status)
    echo "Current devcontainer profile: $(show_profile)"
    exit 0
    ;;
  *)
    echo "Usage: $0 [default|cpu|gpu|status]" >&2
    exit 1
    ;;
esac

echo "Switched devcontainer profile to $profile"
