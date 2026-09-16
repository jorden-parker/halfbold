# halfbold

Personal Python CLI. Takes a Regular and a Bold TrueType font of the same family and writes one font whose `calt` OpenType feature renders the first half of every word in bold. This is the "bionic reading" effect, built like the Fast-Font project, but for any font pair on disk. It is not published to PyPI.

## How it works

- A single variable font is instanced with `fontTools.varLib.instancer` at two weights first; a Regular + Bold pair is used as-is.
- `build.py` copies every letter glyph from the Bold font into the Regular font under a `.half` suffix, decomposing composites so no cross-font component references survive.
- It then generates an OpenType feature file: one chained `calt` rule per word length, longest first, each bolding `ceil(n / 2)` letters. An `ignore` rule stops the chain from re-firing mid-word.
- `fontTools.feaLib` compiles that into a fresh `GSUB` table. The original font's `GSUB` features (ligatures, etc.) are dropped; `GPOS` (kerning) is kept.
- The family name gets a ` Half` suffix so it installs next to the original.

## Conventions

- Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest` after making changes, and fix everything they report.
- Fix any error you notice - a failing type check, a lint error, a failing test, a bug in code you read - even when it sits outside the task you were given. Say what you fixed. If a fix would be large or risky, finish the task first, then describe the problem and ask.
- Code carries no comments. The `ERA` ruff rule catches commented-out code; keep the rest out by naming things well.
- Commit messages are Conventional Commits (`feat:`, `fix:`, `chore:`). The `commit-msg` hook rejects anything else.
- Hooks live in `.githooks/`; run `git config core.hooksPath .githooks` after a fresh clone.
- Only TrueType (`glyf`) fonts are supported. CFF/OTF raises a clear error.
