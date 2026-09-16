#!/bin/sh
set -e
repo="$(cd "$(dirname "$0")/.." && pwd)"
label="com.jorden.halfbold"
plist="$HOME/Library/LaunchAgents/$label.plist"
log="$HOME/Library/Logs/halfbold.log"
uv="$(command -v uv)"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$uv</string>
    <string>run</string>
    <string>--project</string>
    <string>$repo</string>
    <string>halfbold</string>
    <string>--all</string>
  </array>
  <key>WatchPaths</key>
  <array><string>$HOME/Library/Fonts</string></array>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$log</string>
  <key>StandardErrorPath</key><string>$log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "installed $label"
echo "watches:  $HOME/Library/Fonts"
echo "log:      $log"
echo "remove:   launchctl bootout gui/$(id -u)/$label && rm $plist"
