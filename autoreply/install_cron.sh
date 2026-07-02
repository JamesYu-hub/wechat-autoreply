#!/bin/zsh

set -euo pipefail

BASE_DIR="${0:A:h}"
RUNNER="$BASE_DIR/run_poll.sh"
MARKER="# summaryassist-autoreply-poll"
CRON_LINE="* * * * * /bin/zsh \"$RUNNER\" $MARKER"
TMP_FILE="$(mktemp)"

trap 'rm -f "$TMP_FILE"' EXIT

crontab -l 2>/dev/null | grep -vF "$MARKER" > "$TMP_FILE" || true
print -r -- "$CRON_LINE" >> "$TMP_FILE"
crontab "$TMP_FILE"

print -r -- "Installed cron task:"
print -r -- "$CRON_LINE"
