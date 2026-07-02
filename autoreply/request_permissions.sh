#!/bin/zsh

set -u

BASE_DIR="${0:A:h}"
PYTHON="$BASE_DIR/../.venv/bin/python"
REAL_PYTHON="$(realpath "$PYTHON")"
WECHAT_CLI="${AUTOREPLY_WECHAT_CLI:-$BASE_DIR/../.venv/bin/wechat-cli}"

print -r -- "Requesting Accessibility permission for the actual Python -> osascript path..."
SCRIPT_PATH="$BASE_DIR/../sendwechat.scpt" "$PYTHON" - <<'PY' >/dev/null 2>&1 || true
import os
import subprocess
subprocess.run(
    ["/usr/bin/osascript", os.environ["SCRIPT_PATH"], "--request-access"],
    check=False,
    timeout=15,
)
PY

print -r -- "Requesting Python access needed to read WeChat application data..."
"$WECHAT_CLI" sessions --limit 1 --format json >/dev/null 2>&1 || true

print -r -- "Opening Accessibility settings..."
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'

print -r -- "Opening Full Disk Access settings..."
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles'

print -r -- ""
PYTHON_LABEL="$("$PYTHON" - <<'PY'
import sys
print(f"Python {sys.version_info.major}.{sys.version_info.minor}")
PY
)"

print -r -- "If prompted, allow $PYTHON_LABEL / osascript to control System Events."
print -r -- "If $PYTHON_LABEL asks for access to data from other apps, allow it; this lets wechat-cli read WeChat data."
print -r -- "This is an App Data / Full Disk Access request, not an Automation permission."
print -r -- "If the popup was previously denied, add this Python executable under Full Disk Access:"
print -r -- "$REAL_PYTHON"
print -r -- ""
print -r -- "Automation has no + button by design; entries appear only when an app sends an Apple Event."
print -r -- "This autoreply setup does not require a $PYTHON_LABEL -> WeChat Automation entry."
print -r -- "macOS requires you to approve these switches manually."
