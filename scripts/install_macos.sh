#!/usr/bin/env bash
# Install Stoa as a background service on macOS (starts at login, restarts if it crashes).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env. Edit it (set STOA_PASSWORD), then re-run."; exit 0; }

PLIST="$HOME/Library/LaunchAgents/com.stoa.app.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.stoa.app</string>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>ProgramArguments</key><array>
    <string>$ROOT/.venv/bin/uvicorn</string><string>app.main:create_app</string><string>--factory</string>
    <string>--host</string><string>0.0.0.0</string><string>--port</string><string>8000</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/data/stoa.log</string>
  <key>StandardErrorPath</key><string>$ROOT/data/stoa.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Stoa is running at http://localhost:8000 (logs: data/stoa.log)"
