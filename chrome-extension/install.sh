#!/bin/sh
set -e
dir="$(cd "$(dirname "$0")" && pwd)"
printf '%s' "$dir" | pbcopy
open -a "Google Chrome" "chrome://extensions"
cat <<MSG
Folder path copied to clipboard:
  $dir

In the Chrome tab that just opened:
  1. Turn on "Developer mode" (top right).
  2. Click "Load unpacked", press Cmd+Shift+G, paste, Enter, then "Select".

That is the only manual step, ever. From then on the extension checks its
own files every 30 seconds and reloads itself when they change.
MSG
