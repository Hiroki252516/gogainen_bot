#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LOCAL_DIR="$ROOT_DIR/.local"
TOKEN_FILE="$LOCAL_DIR/codex-ws-token"
PID_FILE="$LOCAL_DIR/codex-app-server.pid"
LOG_FILE="$LOCAL_DIR/codex-app-server.log"
ERROR_FILE="$LOCAL_DIR/codex-app-server.err"
PLIST_FILE="$LOCAL_DIR/com.hiroki.ai-tutor.codex-app-server.plist"
LAUNCH_LABEL="com.hiroki.ai-tutor.codex-app-server"
LAUNCH_DOMAIN="gui/$(id -u)"
CODEX_BIN=${CODEX_BIN:-/Applications/Codex.app/Contents/Resources/codex}

mkdir -p "$LOCAL_DIR"

if [ ! -x "$CODEX_BIN" ]; then
  echo "Codex CLIが見つかりません: $CODEX_BIN" >&2
  exit 1
fi

if [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  openssl rand -hex 32 > "$TOKEN_FILE"
fi
chmod 600 "$TOKEN_FILE"

cat > "$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LAUNCH_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$CODEX_BIN</string>
    <string>app-server</string>
    <string>--listen</string>
    <string>ws://0.0.0.0:4500</string>
    <string>--ws-auth</string>
    <string>capability-token</string>
    <string>--ws-token-file</string>
    <string>$TOKEN_FILE</string>
  </array>
  <key>KeepAlive</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>
  <key>StandardErrorPath</key>
  <string>$ERROR_FILE</string>
</dict>
</plist>
EOF

launchctl bootout "$LAUNCH_DOMAIN/$LAUNCH_LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "$LAUNCH_DOMAIN" "$PLIST_FILE"

ATTEMPT=0
while [ "$ATTEMPT" -lt 30 ]; do
  if lsof -nP -iTCP:4500 -sTCP:LISTEN >/dev/null 2>&1; then
    SERVER_PID=$(launchctl print "$LAUNCH_DOMAIN/$LAUNCH_LABEL" | awk '/pid =/{print $3; exit}')
    if [ -n "$SERVER_PID" ]; then
      echo "$SERVER_PID" > "$PID_FILE"
    fi
    echo "Codex app-serverを起動しました (PID: ${SERVER_PID:-unknown})"
    exit 0
  fi
  ATTEMPT=$((ATTEMPT + 1))
  sleep 0.2
done

echo "Codex app-serverの待受開始を確認できませんでした。" >&2
tail -20 "$ERROR_FILE" >&2 || true
exit 1
