#!/bin/sh
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
uv run --project "$root" halfbold-api browser --setup
cat <<'MSG'
In Chrome, enable Developer mode and click Load unpacked.
Press Cmd+Shift+G, paste the copied folder path, then select it.
Remove the old halfbold extension first if upgrading from an earlier version.
Once connected, font changes reach open pages without refreshing.
MSG
