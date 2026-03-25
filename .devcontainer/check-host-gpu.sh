#!/usr/bin/env bash
set -euo pipefail

if [[ "${DEVCONTAINER_SKIP_GPU_CHECK:-0}" == "1" ]]; then
  echo "Skipping GPU host preflight because DEVCONTAINER_SKIP_GPU_CHECK=1."
  exit 0
fi

fail() {
  local message="$1"
  cat >&2 <<EOF

GPU devcontainer preflight failed.
${message}

This profile requires NVIDIA to be ready on the host and exposed to Docker.

Required checks:
1. Host driver works:
   nvidia-smi
2. Docker GPU runtime works:
   docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi

Ubuntu 24.04 host setup:
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \\
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \\
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | \\
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker

If you need to bypass this check temporarily:
  DEVCONTAINER_SKIP_GPU_CHECK=1

EOF
  exit 1
}

if ! command -v docker >/dev/null 2>&1; then
  fail "'docker' is not installed on the host."
fi

if ! docker info >/dev/null 2>&1; then
  fail "Docker daemon is not reachable for the current user."
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  fail "'nvidia-smi' is not available on the host. NVIDIA driver is missing or not in PATH."
fi

if ! nvidia-smi >/dev/null 2>&1; then
  fail "'nvidia-smi' exists but the NVIDIA driver is not working correctly on the host."
fi

runtimes="$(docker info --format '{{json .Runtimes}}' 2>/dev/null || true)"
if [[ "${runtimes}" != *'"nvidia"'* ]]; then
  fail "Docker does not expose the 'nvidia' runtime. Install and configure nvidia-container-toolkit on the host."
fi

echo "GPU host preflight passed: NVIDIA driver is up and Docker exposes the nvidia runtime."
