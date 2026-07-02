#!/bin/zsh

set -u

BASE_DIR="${0:A:h}"

print -r -- "== Autoreply switch =="
"$BASE_DIR/control.sh" status

print -r -- "\n== Cron =="
crontab -l 2>/dev/null | grep -F '# summaryassist-autoreply-poll' || print -r -- "cron missing"

print -r -- "\n== Scheduler state =="
cat "$BASE_DIR/scheduler_state.json" 2>/dev/null || print -r -- "state missing"

print -r -- "\n== Actual sender path =="
SCRIPT_PATH="$BASE_DIR/../sendwechat.scpt" "$BASE_DIR/../.venv/bin/python" - <<'PY' >/dev/null 2>&1
import os
import subprocess
subprocess.run(
    ["/usr/bin/osascript", os.environ["SCRIPT_PATH"], "--test-access"],
    check=True,
    capture_output=True,
    text=True,
    timeout=15,
)
PY
then
  print -r -- "Python -> osascript -> System Events access passed"
else
  print -r -- "Python -> osascript -> System Events access FAILED"
  print -r -- "run ./autoreply/request_permissions.sh"
fi

print -r -- "\n== Qwen =="
if curl -fsS --max-time 2 http://127.0.0.1:8080/v1/models >/dev/null; then
  print -r -- "Qwen online"
else
  print -r -- "Qwen offline"
fi

print -r -- "\n== Recent errors =="
grep -E 'error|Error|failed|timed out|not allowed' "$BASE_DIR/logs/poll.log" 2>/dev/null | tail -10
