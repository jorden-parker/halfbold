# halfbold

Personal Python CLI. Takes a Regular and a Bold TrueType font of the same family and writes one font whose `calt` OpenType feature renders the first half of every word in bold. This is the "bionic reading" effect, built like the Fast-Font project, but for any font pair on disk. It is not published to PyPI.

## How it works

- A single variable font is instanced with `fontTools.varLib.instancer` at two weights first; a Regular + Bold pair is used as-is.
- `build.py` copies every letter glyph from the Bold font into the Regular font under a `.half` suffix, decomposing composites so no cross-font component references survive.
- It then generates an OpenType feature file with two chained `calt` lookups. `MARK_STARTS` bolds the first letter of every subword (a run of letters split at camelCase boundaries: a capital after a lowercase letter, or the last capital of an acronym before a lowercase one). `COUNT` then matches each subword from its bold start, longest first, bolds the next `ceil(n * bold_share) - 1` letters, and un-bolds the start of any subword shorter than the shortest word.
- `fontTools.feaLib` compiles that into a fresh `GSUB` table. The original font's `GSUB` features (ligatures, etc.) are dropped; `GPOS` (kerning) is kept.
- The family name gets a ` Half` suffix so it installs next to the original.

## Automation

- `scripts/install-watcher.sh` installs a launchd user agent (`com.jorden.halfbold`) with `WatchPaths` on `~/Library/Fonts`. Every change there runs `halfbold --all`. Its own output lands in the same folder, which re-triggers one more run that reports everything up to date; that is expected.
- `chrome-extension/install.sh` opens `chrome://extensions` via AppleScript (macOS `open` silently drops `chrome://` URLs) for the one manual Load unpacked step.

## Conventions

- Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest` after making changes, and fix everything they report.
- Fix any error you notice - a failing type check, a lint error, a failing test, a bug in code you read - even when it sits outside the task you were given. Say what you fixed. If a fix would be large or risky, finish the task first, then describe the problem and ask.
- Code carries no comments. The `ERA` ruff rule catches commented-out code; keep the rest out by naming things well.
- Commit messages are Conventional Commits (`feat:`, `fix:`, `chore:`). The `commit-msg` hook rejects anything else.
- Hooks live in `.githooks/`; run `git config core.hooksPath .githooks` after a fresh clone.
- Only TrueType (`glyf`) fonts are supported. CFF/OTF raises a clear error.

## Agent skills

### Issue tracker

Issues and specs are local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
