#!/bin/zsh

set -u

BASE_DIR="${0:A:h}"
LOCK_DIR="$BASE_DIR/.poll.lock"
LOG_DIR="$BASE_DIR/logs"
CONFIG_FILE="$BASE_DIR/config.env"
ENABLED_FILE="$BASE_DIR/.enabled"

mkdir -p "$LOG_DIR"

if [[ -f "$CONFIG_FILE" ]]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi

if [[ ! -f "$ENABLED_FILE" ]]; then
  print -r -- "[$(date '+%Y-%m-%d %H:%M:%S')] skipped: autoreply disabled" >> "$LOG_DIR/poll.log"
  exit 0
fi

if [[ -d "$LOCK_DIR" ]]; then
  LOCK_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    print -r -- "[$(date '+%Y-%m-%d %H:%M:%S')] skipped: poll already running" >> "$LOG_DIR/poll.log"
    exit 0
  fi
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  print -r -- "[$(date '+%Y-%m-%d %H:%M:%S')] skipped: unable to acquire poll lock" >> "$LOG_DIR/poll.log"
  exit 1
fi
print -r -- "$$" > "$LOCK_DIR/pid"

trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$BASE_DIR/.."
"$BASE_DIR/../.venv/bin/python" -m autoreply.adaptive_scheduler >> "$LOG_DIR/poll.log" 2>&1
