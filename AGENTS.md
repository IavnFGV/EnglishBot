# AGENTS.md

## Environment Mapping

This repository may be opened in two environments:

- Host workspace: `/workspace/EnglishBot`
- Devcontainer workspace: `/workspaces/EnglishBot`

Treat these as the same repository root.

## Path Rules

- Prefer repository-relative paths in commands, scripts, and explanations.
- Prefer `.devcontainer/...`, `src/...`, `docs/...`, `scripts/...` over hardcoded absolute paths.
- Do not hardcode `/workspace/EnglishBot` in repo scripts.
- Do not hardcode `/workspaces/EnglishBot` in repo scripts.
- If an absolute path is required for explanation or debugging, clarify whether it is the host or devcontainer path.

## Container-Specific Paths

Inside the devcontainer, use these locations:

- Codex state: `/home/vscode/.codex`
- Workspace root: `/workspaces/EnglishBot`

## Host-Specific Paths

On the host, the workspace root is:

- `/workspace/EnglishBot`

## Script Conventions

- In shell scripts, derive the repository root from the script location instead of assuming an absolute workspace path.
- For repo files, use paths relative to the repo root whenever possible.
- When a task may run both on the host and in the devcontainer, write commands so they work from the current repository root.

## Devcontainer Notes

- Codex sessions are shared via a bind mount from the host into `/home/vscode/.codex`.
- Avoid assumptions that Docker named volumes are host directories.
