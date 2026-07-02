#!/bin/zsh

set -u

BASE_DIR="${0:A:h}"
LOCK_DIR="$BASE_DIR/.poll.lock"
CONFIG_FILE="$BASE_DIR/config.env"
ENABLED_FILE="$BASE_DIR/.enabled"

if [[ -f "$CONFIG_FILE" ]]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi

if [[ ! -f "$ENABLED_FILE" ]]; then
  print -u2 -r -- "autoreply is disabled; run ./autoreply/control.sh start first"
  exit 1
fi

if [[ -d "$LOCK_DIR" ]]; then
  LOCK_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    print -u2 -r -- "autoreply poll is already running (pid $LOCK_PID)"
    exit 1
  fi
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  print -u2 -r -- "unable to acquire autoreply lock"
  exit 1
fi
print -r -- "$$" > "$LOCK_DIR/pid"
trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

cd "$BASE_DIR/.."
"$BASE_DIR/../.venv/bin/python" -m autoreply.run_now "$@"
