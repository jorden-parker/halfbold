#!/bin/sh
set -e
dir="$(cd "$(dirname "$0")" && pwd)"
printf '%s' "$dir" | pbcopy
osascript <<'EOF'
tell application "Google Chrome"
  activate
  if (count of windows) = 0 then make new window
  make new tab at end of tabs of front window with properties {URL:"chrome://extensions"}
end tell
EOF
cat <<MSG
Folder path copied to clipboard:
  $dir

In the chrome://extensions tab that just opened:
  1. Turn on "Developer mode" (toggle, top right).
  2. Click "Load unpacked". In the file dialog press Cmd+Shift+G,
     paste, press Enter, then click "Select".

That is the only manual step, ever. From then on the extension checks its
own files every 30 seconds and reloads itself when they change.
MSG
