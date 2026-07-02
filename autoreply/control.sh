#!/bin/zsh

set -euo pipefail

BASE_DIR="${0:A:h}"
ENABLED_FILE="$BASE_DIR/.enabled"

case "${1:-status}" in
  start)
    touch "$ENABLED_FILE"
    print -r -- "autoreply enabled"
    ;;
  stop)
    rm -f "$ENABLED_FILE"
    print -r -- "autoreply disabled"
    ;;
  status)
    if [[ -f "$ENABLED_FILE" ]]; then
      print -r -- "autoreply enabled"
    else
      print -r -- "autoreply disabled"
    fi
    ;;
  *)
    print -u2 -r -- "Usage: $0 start|stop|status"
    exit 2
    ;;
esac
