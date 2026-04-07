# Devcontainer Profiles

This repository keeps one active devcontainer file and three named profiles.

## Active file

- [devcontainer.json](/workspaces/EnglishBot/.devcontainer/devcontainer.json)
  This is the file VS Code actually opens.

## Named profiles

- [devcontainer.default.json](/workspaces/EnglishBot/.devcontainer/devcontainer.default.json)
  Lightweight default profile for normal bot work. No local Ollama or ComfyUI.
- [devcontainer.cpu.json](/workspaces/EnglishBot/.devcontainer/devcontainer.cpu.json)
  Optional AI-tooling profile for CPU-only local Ollama and ComfyUI work.
- [devcontainer.gpu.json](/workspaces/EnglishBot/.devcontainer/devcontainer.gpu.json)
  Optional AI-tooling profile for GPU-enabled local Ollama and ComfyUI work.

## Recommended rule

Use the default profile unless you are actively working on optional AI tooling.

For `1.0.0`, normal bot development should mean:

1. open [devcontainer.json](/workspaces/EnglishBot/.devcontainer/devcontainer.json)
2. install the project dependencies from the profile
3. run `python -m englishbot`

## Switching profiles

Use the helper script from the repository root:

```bash
bash scripts/switch-devcontainer-profile.sh default
bash scripts/switch-devcontainer-profile.sh cpu
bash scripts/switch-devcontainer-profile.sh gpu
bash scripts/switch-devcontainer-profile.sh status
```

`status` reports which named profile currently matches the active
[devcontainer.json](/workspaces/EnglishBot/.devcontainer/devcontainer.json).

## Local AI startup files

These files only matter for the optional `cpu` and `gpu` profiles:

- [local-ai.on.env](/workspaces/EnglishBot/.devcontainer/local-ai.on.env)
- [ollama.env](/workspaces/EnglishBot/.devcontainer/ollama.env)
- [comfyui.env](/workspaces/EnglishBot/.devcontainer/comfyui.env)
- [start-ollama.sh](/workspaces/EnglishBot/.devcontainer/start-ollama.sh)
- [start-comfyui.sh](/workspaces/EnglishBot/.devcontainer/start-comfyui.sh)
- [manage-generation-services.sh](/workspaces/EnglishBot/.devcontainer/manage-generation-services.sh)

They are part of optional tooling, not the default bot startup path.
