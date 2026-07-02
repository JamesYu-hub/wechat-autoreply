#!/bin/zsh

set -u

BASE_DIR="${0:A:h}"
SOURCE="$BASE_DIR/../sendwechat.scpt"
PYTHON="$BASE_DIR/../.venv/bin/python"

print -r -- "== 1. Direct osascript permission =="
osascript "$SOURCE" --check-permission
print -r -- "exit=$?"

print -r -- "\n== 2. Direct osascript focus and empty keystroke =="
osascript "$SOURCE" --test-access
print -r -- "exit=$?"

print -r -- "\n== 3. Actual Python -> osascript path =="
"$PYTHON" - <<PY
import subprocess
result = subprocess.run(
    ["/usr/bin/osascript", "$SOURCE", "--test-access"],
    capture_output=True,
    text=True,
    timeout=15,
)
print(result.stdout.strip())
raise SystemExit(result.returncode)
PY
print -r -- "exit=$?"

print -r -- "\nNo WeChat message was sent."
