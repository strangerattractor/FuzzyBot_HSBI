#!/usr/bin/env bash
set -euo pipefail

# --- config --------------------------------------------------------------
MODEL_NAME="${MODEL_NAME:-Apertus-8B-Instruct-2509-unsloth-bnb-4bit}"
MODEL_SRC="${MODEL_SRC:-$HOME/models/$MODEL_NAME}"
SCRATCH_BASE="${SCRATCH_BASE:-/dev/shm/$USER/models}"
MODEL_DST="$SCRATCH_BASE/$MODEL_NAME"

VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8000}"

GPU_UTIL="${GPU_UTIL:-0.8}"        # A100 80GB → comfy, leaves headroom
DTYPE="${DTYPE:-auto}"
MAXLEN="${MAXLEN:-65536}"          # full Apertus context
QUANTIZATION="${QUANTIZATION:-bitsandbytes}"
LOG_VLLM="${LOG_VLLM:-$HOME/vllm_apertus_8b.log}"

# use the dedicated vLLM env
VLLM_ENV="${VLLM_ENV:-vllm-env}"

# -------------------------------------------------------------------------
have_proc() { pgrep -a -u "$USER" -f "$1" >/dev/null 2>&1; }
du_bytes() { du -sb "$1" 2>/dev/null | awk '{print $1}'; }

copy_model_if_needed() {
  echo "[model] NAME: $MODEL_NAME"
  echo "[model] SRC:  $MODEL_SRC"
  echo "[model] DST:  $MODEL_DST"

  if [[ ! -d "$MODEL_SRC" ]]; then
    echo "[model] ERROR: source dir does not exist: $MODEL_SRC"
    exit 1
  fi

  if [[ ! -d "$MODEL_DST" ]]; then
    mkdir -p "$MODEL_DST"
    echo "[copy] $MODEL_SRC -> $MODEL_DST (initial)"
    rsync -a --partial --mkpath --info=progress2 "$MODEL_SRC"/ "$MODEL_DST"/
    return
  fi

  local src_size dst_size diff pct
  src_size=$(du_bytes "$MODEL_SRC" || echo 0)
  dst_size=$(du_bytes "$MODEL_DST" || echo 0)

  if [[ "$src_size" -gt 0 ]]; then
    diff=$(( src_size>dst_size ? src_size-dst_size : dst_size-src_size ))
    pct=$(( diff * 100 / src_size ))
    if (( pct > 1 )); then
      echo "[copy] size drift (${pct}%) → syncing"
      rsync -a --partial --mkpath --delete --info=progress2 "$MODEL_SRC"/ "$MODEL_DST"/
    else
      echo "[copy] already present on /dev/shm (within 1%)"
    fi
  else
    echo "[copy] source size unknown; syncing to be safe"
    rsync -a --partial --mkpath --info=progress2 "$MODEL_SRC"/ "$MODEL_DST"/
  fi
}

start_vllm() {
  if have_proc "vllm serve .*:$VLLM_PORT"; then
    echo "[vllm] already running on :$VLLM_PORT"
    return
  fi

  # Activate conda env with vllm
  # shellcheck disable=SC1090
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate "$VLLM_ENV"

  echo "[vllm] using env: $VLLM_ENV"
  which vllm || echo "[warn] vllm not found in PATH!"

  echo "[vllm] launching on $VLLM_HOST:$VLLM_PORT"
  echo "[vllm] model dir: $MODEL_DST"

  extra_args=()
  if [[ -n "$QUANTIZATION" ]]; then
    extra_args+=( --quantization "$QUANTIZATION" )
    extra_args+=( --load-format bitsandbytes )
  fi

  nohup vllm serve "$MODEL_DST" \
    --host "$VLLM_HOST" --port "$VLLM_PORT" \
    --dtype "$DTYPE" \
    --max-model-len "$MAXLEN" \
    --gpu-memory-utilization "$GPU_UTIL" \
    --enforce-eager \
    "${extra_args[@]}" \
    >"$LOG_VLLM" 2>&1 < /dev/null &

  local health="http://127.0.0.1:$VLLM_PORT/v1/models"
  echo -n "[vllm] warming up"
  for i in {1..90}; do
    if curl -fsS "$health" >/dev/null 2>&1; then
      echo " ✓"
      echo "[vllm] models endpoint:"
      curl -s "$health"; echo
      return
    fi
    sleep 2
    echo -n "."
  done
  echo
  echo "[vllm] failed to become healthy; last log lines:"
  tail -n 60 "$LOG_VLLM" || true
  exit 1
}

# --- main ----------------------------------------------------------------
copy_model_if_needed
start_vllm
echo "[done] vLLM running on :$VLLM_PORT (Apertus 8B, 65k ctx)"
