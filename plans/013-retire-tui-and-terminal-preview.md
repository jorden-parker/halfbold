# Plan 013: Retire the Go TUI and the terminal preview now that the app covers searching, installing, converting and previewing

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7b9c258..HEAD -- src/halfbold/cli.py src/halfbold/preview.py tests/test_preview.py tests/test_brewcask.py pyproject.toml README.md AGENTS.md .gitignore tui/`
> Plans 011 and 012 must be DONE and the maintainer must have used the app
> at least once (check the 012 status row). Expected drift: plan 011 added a
> README paragraph and `pyproject.toml` script; plan 012 added a README
> section and `.gitignore` lines. Any other change to the in-scope files is a
> STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (deletes working, tested features; reversible via git but the maintainer must confirm they no longer want the terminal paths)
- **Depends on**: plans/011-json-api-for-the-app.md, plans/012-tauri-font-app.md
- **Category**: tech-debt
- **Planned at**: commit `7b9c258`, 2026-09-16

## Why this matters

The maintainer's request was to "move font searching and installation and
conversion out of the cli and move it to the app". After plan 012 the app
does all of that with a real font preview. What remains in the terminal is
now a second, weaker implementation of the same flows:

- the Go TUI in `tui/` (picker, `i` Homebrew install, `p` preview, `s` slot
  switch) — its own font scanner and kind heuristic duplicated in Go;
- `halfbold --preview`, `--preview-cask`, `--png`, `--wait` and the whole
  `src/halfbold/preview.py` (Pillow + kitty graphics protocol) plus the
  Pillow runtime dependency.

Two implementations of one feature drift. This plan removes the terminal
copies and keeps the parts the automation still needs: the single-file
build (`halfbold REGULAR [BOLD]`), `--all` (used by the launchd watcher in
`scripts/install-watcher.sh`), and `--sans/--serif/--mono` (scriptable slot
switching, also used by the Chrome extension README).

**This is the maintainer's call.** The plan is written so it can be executed
as-is, but the index marks it as awaiting confirmation.

## Current state

- `tui/` — Go module `halfbold/tui` (Bubble Tea). Files: `brew.go`,
  `brew_test.go`, `fonts.go`, `fonts_test.go`, `go.mod`, `go.sum`, `main.go`,
  `model.go`, `model_test.go`, `run.go`, `run_test.go`. It shells out to
  `uv run --project <repo> halfbold …` with `--preview … --wait`,
  `--preview-cask TOKEN --wait`, and `--<kind> FAMILY`.
- `src/halfbold/preview.py` (205 lines) — `render_preview`, `kitty_chunks`,
  `show_image`, `preview_images`, `preview_candidates`, `preview_files`,
  `SAMPLE_TEXT`. Imported only by `cli.py` (line 13):
  ```python
  from halfbold.preview import preview_candidates, preview_files
  ```
  and by `tests/test_preview.py`. Plan 011's `api.py` does **not** import
  it (it copies the candidate-from-files lines).
- `src/halfbold/cli.py` — preview flags at lines 103–124, mode validation at
  lines 130–137 and 139–149, handlers at lines 167–191:
  ```python
  if args.preview:
      try:
          if args.regular.is_dir():
              lines = preview_candidates(args.regular, png=args.png, wait=args.wait)
          else:
              lines = preview_files(
                  args.regular, args.bold, png=args.png, wait=args.wait
              )
      except ValueError as err:
          print(err)
          return 1
      for line in lines:
          print(line)
      return 0
  if args.preview_cask:
      with tempfile.TemporaryDirectory(prefix="halfbold-cask-") as tmp:
          try:
              print(f"fetching {args.preview_cask} …", flush=True)
              fonts_dir = cask_font_dir(args.preview_cask, Path(tmp))
              lines = preview_candidates(fonts_dir, png=args.png, wait=args.wait)
          except ValueError as err:
              print(f"{args.preview_cask}: {err}")
              return 1
      for line in lines:
          print(line)
      return 0
  ```
  The final "give a font file, --all …, or --sans/--serif/--mono" check at
  lines 139–149 references `args.preview` and `args.preview_cask`.
- `tests/test_preview.py` — tests only `preview.py` and the `--preview` CLI
  flag. `tests/test_brewcask.py` lines 147–163 hold two CLI tests for
  `--preview-cask` (`test_cli_preview_cask_png`,
  `test_cli_preview_cask_rejects_other_modes`); the rest of that file tests
  `brewcask.py`, which stays.
- `pyproject.toml` runtime dependencies:
  ```toml
  dependencies = [
      "fonttools>=4.65.0",
      "pillow>=12.3.0",
  ]
  ```
  `uharfbuzz` in the dev group is used by `tests/test_shaping.py` — keep it.
- `README.md` sections: `## Interactive picker` (lines 10–24, the TUI),
  the `--preview` paragraph and code block (lines 42–58, including the tmux
  `allow-passthrough` note), and in `## Develop` the line
  `go -C tui vet ./... && go -C tui test ./...`.
- `AGENTS.md` does not mention `tui/` or the preview; nothing to edit there
  unless plan 011/012 added lines (check with `grep -n "tui\|preview" AGENTS.md`).
- `.gitignore` has a `# Go` block with `tui/halfbold-tui` and `tui/tui`.
- `brewcask.cask_font_dir` stays: `halfbold-api cask-fonts` uses it.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Sync deps | `uv sync` | exit 0, Pillow removed from the environment |
| Tests | `uv run pytest -q` | all pass |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| App still builds | `cd app && pnpm build` | exit 0 |

## Scope

**In scope**:
- `tui/` (delete the directory)
- `src/halfbold/preview.py` (delete)
- `tests/test_preview.py` (delete)
- `src/halfbold/cli.py` (remove the four flags and two handlers)
- `tests/test_brewcask.py` (remove the two `--preview-cask` CLI tests)
- `pyproject.toml`, `uv.lock` (drop Pillow)
- `README.md`, `.gitignore`

**Out of scope**:
- `src/halfbold/brewcask.py`, `scan.py`, `build.py`, `web.py`, `api.py` —
  all still used by the app.
- `--all`, `--sans/--serif/--mono`, the single-file build, `scripts/`,
  `chrome-extension/`, `app/`.
- `tests/test_shaping.py` and `uharfbuzz`.

## Git workflow

- Branch: `advisor/013-retire-tui`
- Two commits: `chore: remove the Go TUI, superseded by the app` and
  `chore: remove the terminal preview and the Pillow dependency`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Delete the TUI

`git rm -r tui/`. Remove the `# Go` block (three lines) from `.gitignore`.
In `README.md` delete the `## Interactive picker` section entirely (heading
through the paragraph starting "Press `i` to install"), and remove
`go -C tui vet ./... && go -C tui test ./...` from the `## Develop` block.

**Verify**: `test ! -d tui && ! grep -n "tui" README.md .gitignore` → exit 0. `uv run pytest -q` → all pass (nothing Python changed yet).

### Step 2: Remove the preview flags from `cli.py`

1. Delete the import `from halfbold.preview import preview_candidates, preview_files`
   and, if now unused, `import tempfile` and `from halfbold.brewcask import cask_font_dir`
   (ruff `F401` will tell you).
2. Delete the four `parser.add_argument` calls for `--preview`, `--png`,
   `--wait`, `--preview-cask`.
3. Delete the two `parser.error` checks that mention `--preview` and the
   one for `--png and --wait`.
4. In the final "give a font file…" check, drop the
   `and not args.preview` / `and not args.preview_cask` lines.
5. Delete the `if args.preview:` and `if args.preview_cask:` blocks from
   `main`.

`git rm src/halfbold/preview.py tests/test_preview.py`. In
`tests/test_brewcask.py` delete `test_cli_preview_cask_png` and
`test_cli_preview_cask_rejects_other_modes` and any import that becomes
unused (`cli`, `variable_font` fixture usage).

**Verify**: `uv run ruff check . && uv run ruff format --check .` → exit 0. `uv run halfbold --preview x.ttf` → exits 2 with `unrecognized arguments: --preview`. `uv run pytest -q` → all pass.

### Step 3: Drop Pillow

Remove `"pillow>=12.3.0",` from `pyproject.toml` dependencies; run
`uv sync` (this rewrites `uv.lock`).

**Verify**: `grep -rn "PIL\|pillow" src/ tests/ pyproject.toml` → no matches. `uv run pytest -q` → all pass. `uv run python -c "import PIL"` → `ModuleNotFoundError`.

### Step 4: README

Delete the `--preview` paragraph, its code block, the `--preview-cask`
sentence and the tmux `allow-passthrough` paragraph. Read the remaining
README top to bottom once and fix any sentence that still says the preview
is drawn in the terminal; the `## App` section from plan 012 is now the only
preview documentation.

**Verify**: `grep -n "preview" README.md` lists only lines inside the `## App` section. `cd app && pnpm build` → exit 0.

## Test plan

No new tests. Deleted tests: all of `tests/test_preview.py` and two in
`tests/test_brewcask.py`. `uv run pytest -q` must still pass with the
remaining suites (`test_api`, `test_brewcask`, `test_build`, `test_scan`,
`test_shaping`, `test_variable`, `test_web`).

## Done criteria

- [ ] `tui/` and `src/halfbold/preview.py` no longer exist
- [ ] `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` exit 0
- [ ] `grep -rn "preview" src/halfbold/cli.py` → no matches
- [ ] `grep -n pillow pyproject.toml` → no matches; `uv.lock` regenerated
- [ ] `uv run halfbold --all --dry-run` still works (the watcher's command)
- [ ] `uv run halfbold-api preview <some .ttf>` still works (the app's preview)
- [ ] `plans/README.md` status row updated

## STOP conditions

- The 013 row in `plans/README.md` still says "awaiting maintainer
  confirmation" — do not execute until the maintainer changes it to TODO.
- `api.py` imports anything from `preview.py` (plan 011 was executed
  differently than written) — report; do not move code around.
- Removing Pillow breaks a test outside `test_preview.py`.
- `scripts/install-watcher.sh` or `chrome-extension/README.md` reference a
  flag you are removing.

## Maintenance notes

- After this lands, the only interactive surface is `app/`; the CLI is for
  the watcher and scripts. Keep new interactive features in the app.
- Plans 001–010 in `plans/` describe the TUI; they stay as history. Mark
  them "superseded by 012/013" in the index, do not delete them.
