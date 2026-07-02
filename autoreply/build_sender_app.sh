#!/bin/zsh

set -euo pipefail

BASE_DIR="${0:A:h}"
SOURCE="$BASE_DIR/../sendwechat.scpt"
APP="$BASE_DIR/WeChatAutoReplySender.app"
BUNDLE_ID="com.summaryassist.wechat-auto-reply-sender"

if [[ ! -d "$APP" ]]; then
  osacompile -o "$APP" "$SOURCE"
else
  osacompile -o "$APP" "$SOURCE"
fi

/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$APP/Contents/Info.plist"
codesign --force --sign - --identifier "$BUNDLE_ID" "$APP"

print -r -- "Built: $APP"
print -r -- "Bundle ID: $BUNDLE_ID"
print -r -- "Grant this app permission in:"
print -r -- "System Settings > Privacy & Security > Accessibility"
