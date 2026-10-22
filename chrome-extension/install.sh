#!/bin/sh
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
uv run --project "$root" halfbold-api browser --setup
cat <<'MSG'
In Chrome, enable Developer mode and click Load unpacked.
Press Cmd+Shift+G, paste the copied folder path, then select it.
Already loaded halfbold? Click the reload button on its card instead.
Once connected, every page keeps its own fonts, converted to Half.
MSG
