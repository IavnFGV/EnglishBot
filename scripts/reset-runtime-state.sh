#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

backup_name=""

usage() {
  cat <<'EOF'
Usage: scripts/reset-runtime-state.sh [--backup-name NAME]

Moves runtime database files, generated image assets, and custom content files
into backup/<name> and recreates empty runtime directories so the bot starts
like a fresh instance.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-name)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --backup-name" >&2
        exit 2
      fi
      backup_name="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

timestamp="$(date -u +%Y%m%d-%H%M%S)"
resolved_backup_name="${backup_name:-runtime-reset-$timestamp}"
backup_dir="$REPO_ROOT/backup/$resolved_backup_name"
mkdir -p "$backup_dir"

shopt -s nullglob

moved_count=0

move_into_backup() {
  local source_path="$1"
  local relative_path="${source_path#$REPO_ROOT/}"
  local destination_path="$backup_dir/$relative_path"
  mkdir -p "$(dirname "$destination_path")"
  mv "$source_path" "$destination_path"
  echo "Moved $relative_path"
  moved_count=$((moved_count + 1))
}

for source_path in "$REPO_ROOT"/data/*.db "$REPO_ROOT"/data/*.db-* "$REPO_ROOT"/*.db "$REPO_ROOT"/*.db-*; do
  [[ -e "$source_path" ]] || continue
  move_into_backup "$source_path"
done

for source_path in "$REPO_ROOT"/assets*; do
  [[ -e "$source_path" ]] || continue
  move_into_backup "$source_path"
done

for source_path in "$REPO_ROOT"/content/custom/*; do
  [[ -e "$source_path" ]] || continue
  move_into_backup "$source_path"
done

mkdir -p "$REPO_ROOT/data"
mkdir -p "$REPO_ROOT/content/custom"

echo "Backup created at: $backup_dir"
echo "Moved entries: $moved_count"
