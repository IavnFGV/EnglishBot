#!/usr/bin/env bash
set -euo pipefail

if [[ "${COMFYUI_AUTOSTART:-0}" != "1" ]]; then
  echo "COMFYUI_AUTOSTART is disabled; skipping ComfyUI startup"
  exit 0
fi

base_url="${COMFYUI_BASE_URL:-http://127.0.0.1:8188}"
workspace="${COMFYUI_WORKSPACE:-/opt/ComfyUI}"
port="${COMFYUI_PORT:-8188}"
extra_args="${COMFYUI_EXTRA_ARGS:-}"
checkpoint_name="${COMFYUI_CHECKPOINT_NAME:-}"
checkpoint_url="${COMFYUI_CHECKPOINT_URL:-}"
checkpoint_dir="${workspace}/models/checkpoints"
checkpoint_path="${checkpoint_dir}/${checkpoint_name}"
startup_timeout_sec="${COMFYUI_STARTUP_TIMEOUT_SEC:-180}"
log_path="${COMFYUI_LOG_PATH:-/tmp/englishbot-comfyui.log}"

is_ready() {
  curl --silent --show-error --fail "$base_url" >/dev/null 2>&1
}

if [[ ! -f "$workspace/main.py" ]]; then
  echo "ComfyUI workspace not found at $workspace; skipping startup"
  exit 0
fi

mkdir -p "$checkpoint_dir"

if [[ -n "$checkpoint_name" && ! -f "$checkpoint_path" ]]; then
  if [[ -z "$checkpoint_url" ]]; then
    echo "ComfyUI checkpoint missing and COMFYUI_CHECKPOINT_URL is empty: $checkpoint_path" >&2
    exit 1
  fi
  echo "Downloading ComfyUI checkpoint: $checkpoint_name"
  tmp_path="${checkpoint_path}.part"
  rm -f "$tmp_path"
  curl --fail --location --output "$tmp_path" "$checkpoint_url"
  mv "$tmp_path" "$checkpoint_path"
elif [[ -n "$checkpoint_name" ]]; then
  echo "ComfyUI checkpoint already present: $checkpoint_path"
fi

python_bin="python"
if [[ -x "$workspace/venv/bin/python" ]]; then
  python_bin="$workspace/venv/bin/python"
fi

if ! is_ready; then
  if pgrep -f "ComfyUI.*main.py" >/dev/null 2>&1; then
    echo "ComfyUI process exists but is not ready yet"
  else
    echo "Starting ComfyUI from $workspace"
    (
      cd "$workspace"
      nohup "$python_bin" main.py --listen 127.0.0.1 --port "$port" $extra_args \
        >"$log_path" 2>&1 &
    )
  fi
fi

for _ in $(seq 1 "$startup_timeout_sec"); do
  if is_ready; then
    echo "ComfyUI is ready at $base_url"
    exit 0
  fi
  sleep 1
done

echo "ComfyUI did not become ready at $base_url" >&2
if [[ -f "$log_path" ]]; then
  echo "Last ComfyUI log lines from $log_path:" >&2
  tail -n 80 "$log_path" >&2 || true
else
  echo "ComfyUI log file not found: $log_path" >&2
fi
echo "Continuing container startup without ComfyUI readiness" >&2
exit 0
