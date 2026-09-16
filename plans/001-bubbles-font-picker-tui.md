# Plan 001: Add a Bubble Tea font-picker TUI that runs halfbold on a chosen installed font

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 6091679..HEAD -- src/halfbold/cli.py README.md .gitignore tui/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (additive; no Python source changes)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `6091679`, 2026-09-16

## Why this matters

Today the only way to use halfbold is to type two font paths by hand:
`uv run halfbold ~/Library/Fonts/InterVariable.ttf -o ~/Library/Fonts/Inter-Half.ttf`.
The user has to know which files are TrueType, which are variable, and which
Regular/Bold pair belong together. The maintainer asked for an interactive
picker built with **Bubbles** (`github.com/charmbracelet/bubbles`, Go) so
they can scroll a list of installed fonts, press Enter, and get the `-Half`
font written straight into `~/Library/Fonts`.

The maintainer explicitly chose Go + Bubbles living inside this Python repo,
with the TUI shelling out to the existing Python CLI. The Python code stays
the single source of truth for font conversion; the Go program only
discovers fonts, builds the command line, runs it, and shows the result.

## Current state

### Files

- `src/halfbold/cli.py` — argparse entrypoint. Positional `regular` (a Regular
  weight **or** a variable `.ttf`), optional positional `bold`, `-o/--output`.
  Prints `wrote <path> (<n> letter glyphs bolded)` and returns 0 on success;
  on failure fontTools / `ValueError` propagates and the process exits non-zero
  with a traceback on stderr.
- `src/halfbold/build.py` — the conversion. Only TrueType (`glyf`) fonts are
  supported; CFF/OTF raises `ValueError("... has no TrueType outlines (CFF/OTF is not supported)")`.
  A single file is treated as a variable font only if it has an `fvar` table,
  else `ValueError("... is not a variable font; pass a Bold file as well")`.
- `README.md` — usage docs. Has a `## Develop` section listing the dev commands.
- `.gitignore` — Python-only ignores today.
- `pyproject.toml` — `[project.scripts] halfbold = "halfbold.cli:main"`, so
  `uv run halfbold ...` works from the repo root. `uv 0.12.1` is installed and
  supports `uv run --project <dir>`.
- `AGENTS.md` — repo conventions (quoted below).
- There is **no** `tui/` directory, no `go.mod`, and no Go toolchain installed
  on the machine (`go version` → `command not found`). Homebrew is installed.

### Excerpt: `src/halfbold/cli.py:22-30` (positional arguments)

```python
    parser.add_argument("regular", type=Path, help="Regular weight or variable .ttf")
    parser.add_argument(
        "bold",
        type=Path,
        nargs="?",
        help="Bold weight .ttf of the same family; omit for a variable font",
    )
```

### Excerpt: `src/halfbold/cli.py:55-66` (what success prints)

```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    letters = build_halfbold_font(
        ...
    )
    print(f"wrote {output} ({len(letters)} letter glyphs bolded)")
    return 0
```

### Excerpt: `README.md:1-12`

```markdown
# halfbold

Turn any Regular + Bold TrueType pair into a bionic-reading font.

```sh
uv run halfbold Inter-Regular.ttf Inter-Bold.ttf -o Inter-Half.ttf
uv run halfbold InterVariable.ttf -o ~/Library/Fonts/Inter-Half.ttf
```

A single variable font is instanced at weight 400 and 700 (`--regular-weight`, `--bold-weight` to change). Output written into `~/Library/Fonts` is installed immediately on macOS.
```

### What `~/Library/Fonts` looks like on the maintainer's machine (real data)

This is the input the picker must handle. 139 files; the `.ttf` ones include:

```
Inter-Half.ttf                       <- previous halfbold output; must be hidden
InterVariable.ttf                    <- variable font (has fvar); one list entry
InterVariable-Italic.ttf             <- italic; hide
JetBrainsMonoNerdFont-Regular.ttf    <- static pair member
JetBrainsMonoNerdFont-Bold.ttf       <- static pair member -> one list entry
JetBrainsMonoNerdFont-Half.ttf       <- previous output; hide
JetBrainsMonoNerdFont-ExtraBold.ttf  <- other weights; ignored
JetBrainsMonoNerdFontMono-Regular.ttf / -Bold.ttf   <- different family name -> own entry
JetBrainsMonoNerdFontPropo-Regular.ttf / -Bold.ttf  <- own entry
JetBrainsMonoNLNerdFont*-Regular/-Bold.ttf          <- own entries
SourceSerif4[opsz,wght].ttf          <- variable; one entry
SourceSerif4-Italic[opsz,wght].ttf   <- italic; hide
SourceSerif4-Half.ttf                <- previous output; hide
Inter-Regular.otf, Inter-Bold.otf ... <- CFF; must NOT be listed (halfbold rejects them)
```

Do not rely on filenames to decide what a font is. Read the font's table
directory (does it have `glyf`? `fvar`?) and its `name` table (family,
subfamily). The filename heuristics fall apart on `[opsz,wght]` names.

### Repo conventions that apply (from `AGENTS.md`, quoted)

> - Code carries no comments. The `ERA` ruff rule catches commented-out code; keep the rest out by naming things well.
> - Commit messages are Conventional Commits (`feat:`, `fix:`, `chore:`). The `commit-msg` hook rejects anything else.
> - Hooks live in `.githooks/`; run `git config core.hooksPath .githooks` after a fresh clone.
> - Only TrueType (`glyf`) fonts are supported. CFF/OTF raises a clear error.

Apply the "no comments" rule to the Go code too: no `//` comments except
where `gofmt`/`go vet` conventions require none (they don't). Name things well
instead. Doc comments on exported identifiers are also **not** wanted here —
keep everything unexported except `main`.

The pre-commit hook (`.githooks/pre-commit`) runs `uv run ruff format --check .`,
`uv run ruff check .`, `uv run pytest -q`. None of these look at `.go` files,
so the Go module cannot break them, but they must still pass at commit time.

### Design decisions already made (do not re-open)

1. **Location**: Go module at `tui/` inside this repo. Module path
   `halfbold/tui`. Binary name `halfbold-tui`.
2. **Library line**: Bubble Tea **v1** (`github.com/charmbracelet/bubbletea`
   v1.x, `github.com/charmbracelet/bubbles` v0.x, `github.com/charmbracelet/lipgloss`
   v1.x). Do **not** use the v2 line (`charm.land/bubbletea/v2`,
   `charm.land/bubbles/v2`) — its API differs (`tea.KeyPressMsg`,
   `list.New(delegate, w, h)` with no items argument, etc.) and this plan's
   code shapes are written for v1.
3. **Conversion stays in Python**. The TUI runs
   `uv run --project <repo> halfbold <regular> [<bold>] -o <output>` as a
   subprocess. It never parses glyphs or writes fonts itself.
4. **Font discovery**: scan `~/Library/Fonts` (override/add with a repeatable
   `-fonts` flag). Only files whose SFNT table directory contains `glyf`.
   Two candidate kinds:
   - **variable**: has `fvar` and subfamily does not contain `Italic`.
     Command: `halfbold <path> -o <out>`.
   - **pair**: static fonts grouped by family name where both a `Regular`
     and a `Bold` subfamily exist. Command: `halfbold <regular> <bold> -o <out>`.
   Files whose base name ends in `-Half.ttf` are skipped (they are halfbold
   output). Italics are skipped.
5. **Output path**: `<first font's directory>/<family with spaces removed>-Half.ttf`.
   For the real data that yields `~/Library/Fonts/Inter-Half.ttf`,
   `~/Library/Fonts/JetBrainsMonoNerdFont-Half.ttf`,
   `~/Library/Fonts/SourceSerif4-Half.ttf` — matching what the maintainer
   already produces by hand. Overridable with `-out-dir`.
6. **Family name** = name ID 16 if present, else name ID 1. **Subfamily** =
   name ID 17 if present, else name ID 2. Strip the word `Variable` from the
   family when building the output filename (mirrors `rename_font` in
   `build.py`, which does the same for the installed family name).
7. **Weights for variable fonts**: use halfbold's defaults (400/700). No
   weight UI in this plan (deferred, see Maintenance notes).

## Commands you will need

| Purpose | Command (run from repo root unless noted) | Expected on success |
|---|---|---|
| Install Go | `brew install go` | `go version` prints `go version go1.2x ...` |
| Go deps | `cd tui && go mod tidy` | exit 0, `go.sum` written |
| Go build | `cd tui && go build ./...` | exit 0 |
| Go vet | `cd tui && go vet ./...` | exit 0, no output |
| Go format | `gofmt -l tui/` | **no output** (empty list = all formatted) |
| Go tests | `cd tui && go test ./...` | `ok  halfbold/tui` |
| Run TUI | `go run ./tui` (from repo root) or `cd tui && go run . -project ..` | list of fonts appears |
| Python lint | `uv run ruff check . && uv run ruff format --check .` | exit 0 |
| Python tests | `uv run pytest -q` | all pass (currently 8+ tests) |
| Python CLI smoke | `uv run halfbold --help` | usage text, exit 0 |

Note on `go run ./tui` from the repo root: Go needs to find the module.
Because `tui/go.mod` is a separate module, `go run ./tui` from the root will
**fail** with "go: cannot find main module". Always `cd tui` first, or use
`go run -C tui . -project ..` (Go ≥ 1.20 supports `-C`). Document the
`-C` form in the README.

## Suggested executor toolkit

- Bubble Tea v1 examples: https://github.com/charmbracelet/bubbletea/tree/v1.3.4/examples
  (`list-default`, `spinner`, `exec`). Bubbles v0.21 `list` docs:
  https://pkg.go.dev/github.com/charmbracelet/bubbles/list
- OpenType table directory spec (12-byte header + 16-byte records):
  https://learn.microsoft.com/en-us/typography/opentype/spec/otff#table-directory
- `golang.org/x/image/font/sfnt` for reading the `name` table:
  https://pkg.go.dev/golang.org/x/image/font/sfnt (`Parse`, `(*Font).Name(nil, sfnt.NameID)`).

## Scope

**In scope** (the only files you should create or modify):

- `tui/go.mod`, `tui/go.sum` (create)
- `tui/main.go` (create) — program entry, flags, `tea.NewProgram`
- `tui/fonts.go` (create) — scanning, SFNT parsing, candidate grouping
- `tui/fonts_test.go` (create)
- `tui/model.go` (create) — Bubble Tea model, list, spinner, result screen
- `tui/run.go` (create) — building and executing the `uv run` command
- `.gitignore` (append Go build output)
- `README.md` (add a short "Interactive picker" section and a Go line under Develop)

**Out of scope** (do NOT touch, even though they look related):

- `src/halfbold/**` — no Python changes. The TUI must work against the CLI
  exactly as it exists at commit `6091679`.
- `tests/**` — Python tests unchanged.
- `pyproject.toml`, `uv.lock` — no new Python deps, no version bump.
- `.githooks/**` — do not add Go checks to the hooks in this plan.
- Any font file under `~/Library/Fonts` during tests. Tests must use
  `t.TempDir()`.

## Git workflow

- Branch: `advisor/001-bubbles-font-picker-tui`
- One commit per step group is fine. Conventional Commits, e.g.
  `feat: add bubble tea font picker tui` — the `commit-msg` hook rejects other
  formats (`.githooks/commit-msg`). Run `git config core.hooksPath .githooks`
  once if hooks are not active.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Install Go

```sh
brew install go
go version
```

**Verify**: `go version` → prints `go version go1.2`… (anything ≥ 1.22 is fine).

### Step 1: Create the module and pin the Bubble Tea v1 line

Create `tui/go.mod` by running, from the repo root:

```sh
mkdir -p tui && cd tui
go mod init halfbold/tui
go get github.com/charmbracelet/bubbletea@v1
go get github.com/charmbracelet/bubbles@latest
go get github.com/charmbracelet/lipgloss@v1
go get golang.org/x/image@latest
```

Then check the resolved versions:

```sh
grep -E 'bubbletea|bubbles|lipgloss' go.mod
```

**Verify**: bubbletea line shows `v1.` (not `v2.`), bubbles shows `v0.`
(not `v2.`), lipgloss shows `v1.`. If `bubbles@latest` resolved to a `v2.x`
version, run `go get github.com/charmbracelet/bubbles@v0` instead and re-check.

Append to the repo-root `.gitignore`:

```
# Go
tui/halfbold-tui
```

### Step 2: `tui/fonts.go` — scan a directory and classify each font

Implement these unexported types and functions (exact names, so the tests in
Step 3 compile):

```go
type fontFile struct {
	path      string
	family    string
	subfamily string
	variable  bool
}

type candidate struct {
	label   string
	regular string
	bold    string
}

func scanFonts(dirs []string) ([]fontFile, error)
func readFont(path string) (fontFile, bool, error)
func groupCandidates(files []fontFile) []candidate
func outputPath(c candidate, outDir string) string
```

Behavior:

- `scanFonts` walks each dir non-recursively (`os.ReadDir`), considers only
  regular files whose lowercased extension is `.ttf` or `.otf`, skips names
  ending in `-Half.ttf`, calls `readFont`, and keeps the ones where the second
  return value is `true`. A directory that does not exist is skipped silently
  (not an error). Any other I/O error is returned.
- `readFont` reads the file and parses the **SFNT table directory** by hand:
  bytes 0–3 are the sfnt version (`0x00010000` or `"true"` for TrueType,
  `"OTTO"` for CFF; `"ttcf"` collections → return `false`, they are
  unsupported), bytes 4–5 big-endian uint16 `numTables`, then from offset 12
  one 16-byte record per table whose first 4 bytes are the tag. Collect tags
  into a `map[string]bool`. Return `false` (skip) when `glyf` is absent.
  `variable = tags["fvar"]`.
  Then parse the same bytes with `sfnt.Parse` from
  `golang.org/x/image/font/sfnt` and read names via
  `f.Name(nil, sfnt.NameID(16))` falling back to `sfnt.NameIDFamily` (ID 1)
  when 16 is empty or errors, and `sfnt.NameID(17)` falling back to
  `sfnt.NameIDSubfamily` (ID 2). Trim whitespace.
- `groupCandidates`:
  - Skip any file whose `subfamily` contains `Italic` (case-insensitive).
  - For each `variable` file: one candidate with `regular = path`,
    `bold = ""`, `label = family` (family with the word `Variable` removed
    and whitespace collapsed, e.g. `Inter Variable` → `Inter`).
  - For static files: group by `family`; when a group has a file with
    `subfamily == "Regular"` and one with `subfamily == "Bold"` (exact,
    case-insensitive compare), emit one candidate `label = family`,
    `regular = <Regular path>`, `bold = <Bold path>`.
  - Sort candidates by `label`, then by `regular` path, so output is
    deterministic. If the same label appears twice (a variable and a static
    pair of the same family), keep both; append ` (variable)` to the variable
    one's label so the user can tell them apart. Always show the kind in the
    list description anyway (see Step 4).
- `outputPath` = `filepath.Join(outDir, strings.ReplaceAll(labelWithoutVariableSuffix, " ", "") + "-Half.ttf")`
  where `outDir` is the caller's choice (the `-out-dir` flag, default = the
  directory of `c.regular`). Strip a trailing ` (variable)` before building
  the name.

**Verify**: `cd tui && go build ./... && go vet ./...` → exit 0.

### Step 3: `tui/fonts_test.go` — unit tests with synthetic data

Tests must not read `~/Library/Fonts`. Model them as plain table-driven Go
tests (there is no existing Go test in the repo to mirror; the Python tests
in `tests/test_build.py` are short, single-assertion functions — match that
spirit).

Write at least these tests:

1. `TestGroupCandidatesPairsRegularWithBold` — input three static
   `fontFile`s of family `"Mono"` with subfamilies `Regular`, `Bold`,
   `ExtraBold`; expect exactly one candidate with `regular` and `bold` set to
   the Regular and Bold paths.
2. `TestGroupCandidatesSkipsFamilyWithoutBold` — family with only `Regular`
   → zero candidates.
3. `TestGroupCandidatesSkipsItalics` — a variable file with subfamily
   `"Italic"` → zero candidates; a variable file with subfamily `"Regular"`
   → one candidate with empty `bold`.
4. `TestGroupCandidatesStripsVariableFromLabel` — variable file with family
   `"Inter Variable"` → label `"Inter"`.
5. `TestOutputPathRemovesSpaces` — candidate label `"JetBrainsMono Nerd Font"`,
   outDir `/x` → `/x/JetBrainsMonoNerdFont-Half.ttf`.
6. `TestReadFontDetectsGlyfAndFvar` — build a minimal byte slice by hand:
   sfnt version `0x00010000`, `numTables = 2`, records for tags `glyf` and
   `fvar` with zero offsets/lengths. Write it to `t.TempDir()`. Since
   `sfnt.Parse` will fail on such a stub (no `name` table), structure
   `readFont` so the **table-directory parse is a separate function**
   `readTableTags(data []byte) (map[string]bool, error)` and test that
   function directly: expect `tags["glyf"] && tags["fvar"]`. Also test that
   the `OTTO` header with no `glyf` yields no `glyf` tag, and that `ttcf`
   returns an error.
7. `TestScanFontsSkipsHalfOutputAndMissingDir` — in a `t.TempDir()` create
   `Foo-Half.ttf` (any bytes) and `notes.txt`; call
   `scanFonts([]string{dir, filepath.Join(dir, "missing")})`; expect zero
   files and `nil` error.

**Verify**: `cd tui && go test ./...` → `ok  halfbold/tui`.

### Step 4: `tui/model.go` — the Bubble Tea model

Use Bubble Tea v1 shapes. One model, three screens driven by a `screen`
enum: `screenPick`, `screenRunning`, `screenDone`.

```go
type item struct{ c candidate }

func (i item) Title() string       { return i.c.label }
func (i item) Description() string { /* "variable font" or "Regular + Bold pair" plus the file base names */ }
func (i item) FilterValue() string { return i.c.label }

type model struct {
	list     list.Model
	spinner  spinner.Model
	screen   screen
	runner   runner
	outDir   string
	chosen   candidate
	output   string
	err      error
}

type runDoneMsg struct {
	output string
	err    error
}
```

- Construct the list with `list.New(items, list.NewDefaultDelegate(), 0, 0)`,
  `l.Title = "halfbold: pick a font to convert"`, enable filtering (default
  delegate supports `/` to filter). Set size on `tea.WindowSizeMsg`
  (`m.list.SetSize(msg.Width, msg.Height-2)`).
- `Init` returns `nil`. Spinner: `spinner.New()`, `s.Spinner = spinner.Dot`.
- `Update`:
  - `tea.KeyMsg` `ctrl+c` → `tea.Quit` on any screen. `q` quits on
    `screenPick` and `screenDone` only when the list is **not** filtering
    (`m.list.FilterState() != list.Filtering`), so typing `q` into the filter
    still works.
  - `enter` on `screenPick`: take `m.list.SelectedItem().(item)`; set
    `m.chosen`, `m.screen = screenRunning`, return
    `tea.Batch(m.spinner.Tick, m.runner.run(m.chosen, outputPath(m.chosen, dirFor(m))))`
    where `run` returns a `tea.Cmd` that executes the subprocess and yields a
    `runDoneMsg`.
  - `spinner.TickMsg` while `screenRunning` → forward to `m.spinner.Update`.
  - `runDoneMsg` → store `output`/`err`, `m.screen = screenDone`.
  - `enter` or `esc` on `screenDone` → back to `screenPick`.
  - Otherwise forward to `m.list.Update` when on `screenPick`.
- `View`:
  - `screenPick`: `m.list.View()`.
  - `screenRunning`: `fmt.Sprintf("%s converting %s …", m.spinner.View(), m.chosen.label)`.
  - `screenDone`: on success show the CLI's stdout (which contains
    `wrote <path> (<n> letter glyphs bolded)`) and the line
    `Enable "calt" in your app if it is off.`; on error show the **last 15
    lines** of combined stdout+stderr (the Python traceback is long; its
    final `ValueError: ...` line is what matters) in a lipgloss red style.
    Both end with `enter: back  q: quit`.

Keep all styling in a few package-level `lipgloss.NewStyle()` vars. No
comments.

**Verify**: `cd tui && go build ./... && go vet ./...` → exit 0.

### Step 5: `tui/run.go` — build and execute the halfbold command

```go
type runner struct {
	project string
}

func (r runner) args(c candidate, out string) []string
func (r runner) run(c candidate, out string) tea.Cmd
```

- `args` returns
  `["run", "--project", r.project, "halfbold", c.regular, "-o", out]` for a
  variable candidate and
  `["run", "--project", r.project, "halfbold", c.regular, c.bold, "-o", out]`
  for a pair. (`uv` is the program; these are its arguments.)
- `run` returns a `tea.Cmd` closure that does
  `exec.Command("uv", r.args(c, out)...).CombinedOutput()` and returns
  `runDoneMsg{output: string(outBytes), err: err}`. Do not use
  `tea.ExecProcess` — the conversion is non-interactive and we want to keep
  the spinner on screen.
- Add `TestRunnerArgsVariable` and `TestRunnerArgsPair` in `tui/fonts_test.go`
  (or a new `run_test.go`, also in scope) asserting the exact slices above.

**Verify**: `cd tui && go test ./...` → `ok`.

### Step 6: `tui/main.go` — flags and program start

Flags (standard `flag` package):

- `-project string` — path to the halfbold repo root (the directory holding
  `pyproject.toml`), default `".."` (because the binary is normally run from
  `tui/`). Resolve with `filepath.Abs` and STOP with a clear error if
  `<project>/pyproject.toml` does not exist:
  `halfbold-tui: no pyproject.toml in <abs path>; pass -project <repo root>`.
- `-fonts value` — repeatable (implement `flag.Value` on a `[]string`),
  default `["~/Library/Fonts"]` with `~` expanded via `os.UserHomeDir`.
- `-out-dir string` — default empty, meaning "same directory as the chosen
  font". When set, all output goes there (create it with `os.MkdirAll`).

Flow: parse flags → `scanFonts` → `groupCandidates` → if zero candidates,
print `no Regular+Bold pairs or variable TrueType fonts found in <dirs>` to
stderr and exit 1 → else `tea.NewProgram(newModel(...), tea.WithAltScreen()).Run()`.

**Verify** (manual, from repo root — this actually converts a font, so it
writes into `~/Library/Fonts`; that is the intended behavior on the
maintainer's machine):

```sh
go run -C tui . -project ..
```

Expected: an alt-screen list with entries such as `Inter (variable)`,
`JetBrainsMono Nerd Font`, `JetBrainsMono Nerd Font Mono`, `Source Serif 4`.
Press `/`, type `inter`, Enter, Enter → spinner → a done screen containing
`wrote /Users/<you>/Library/Fonts/Inter-Half.ttf (`. Press `q`.

If you cannot run an interactive terminal in your environment, do the
non-interactive check instead and note it in your report:

```sh
cd tui && go build -o halfbold-tui . && ./halfbold-tui -project .. -fonts /nonexistent; echo "exit=$?"
```

Expected: the "no Regular+Bold pairs…" message and `exit=1`.

### Step 7: README

Under the first code block in `README.md` add:

````markdown
## Interactive picker

A small Bubble Tea TUI lists the Regular + Bold pairs and variable TrueType fonts in `~/Library/Fonts` and runs `halfbold` on the one you pick:

```sh
go run -C tui . -project ..
```

`-fonts DIR` (repeatable) scans other directories; `-out-dir DIR` writes the `-Half.ttf` somewhere other than next to the source font.
````

Under `## Develop` add one line after the ruff line:

```sh
go -C tui vet ./... && go -C tui test ./...
```

**Verify**: `grep -n 'go run -C tui' README.md` → one match.

## Test plan

- New Go tests in `tui/fonts_test.go` (and optionally `tui/run_test.go`):
  the seven cases in Step 3 plus the two `runner.args` cases in Step 5.
  Nine tests minimum.
- No Python test changes. `uv run pytest -q` must still pass unchanged.
- Verification: `cd tui && go test ./...` → `ok  halfbold/tui` and
  `go test -v ./... | grep -c '^--- PASS'` ≥ 9.

## Done criteria

Machine-checkable. ALL must hold (run from repo root):

- [ ] `go version` exits 0
- [ ] `cd tui && go build ./... && go vet ./...` exits 0
- [ ] `gofmt -l tui/` prints nothing
- [ ] `cd tui && go test ./...` exits 0 with ≥ 9 passing tests
- [ ] `grep -E 'charm.land|/v2' tui/go.mod` prints nothing (v1 line only)
- [ ] `grep -rn '^\s*//' tui/*.go` prints nothing (no comments)
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` exits 0
- [ ] `git status --porcelain` lists only: `tui/`, `.gitignore`, `README.md`, `plans/README.md`
- [ ] `git diff --stat 6091679..HEAD -- src tests pyproject.toml uv.lock .githooks` prints nothing
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `brew install go` fails or Homebrew is unavailable — the maintainer must
  install Go themselves.
- `go get github.com/charmbracelet/bubbles@v0` cannot resolve a `v0.x`
  version, or the resolved bubbles `v0.x` requires bubbletea `v2` (check
  with `cd tui && go mod graph | grep bubbletea`). Report the versions you
  saw; do not switch to the v2 import paths.
- `uv run halfbold --help` fails, or `uv run --project` is not accepted by
  the installed `uv` (it is in `uv 0.12.1`).
- `golang.org/x/image/font/sfnt` cannot read name IDs 16/17 (it exposes
  `Name(b []byte, id NameID)` for any ID; if the installed version's
  signature differs, report rather than vendoring a parser).
- The `cli.py` excerpts in "Current state" no longer match (positional
  argument order or the `wrote ...` line changed).
- Making the picker work seems to require editing anything under `src/`.

## Maintenance notes

- **Coupling to the CLI's argv**: `runner.args` hard-codes
  `halfbold <regular> [bold] -o <out>`. If `cli.py` ever renames `-o` or
  changes positional order, update `run.go` and its tests together.
- **Coupling to stdout text**: the done screen just echoes stdout, so
  changes to the `wrote ...` line are cosmetic, not breaking.
- **Weights**: variable fonts always use 400/700. A follow-up could add a
  `textinput` bubble for `--regular-weight`/`--bold-weight`; it was left out
  to keep this plan small.
- **Font detection**: the picker trusts the `name` table's Regular/Bold
  subfamily strings. Families that ship `Book`/`Semibold` instead will not
  pair; they can still be converted by hand with the CLI. If that bites,
  extend `groupCandidates` with a weight-class (`OS/2 usWeightClass`) fallback.
- **Reviewer checklist**: confirm no `.go` file has comments, `go.mod` is on
  the v1 line, tests never touch the real font directory, and nothing under
  `src/` moved.
- **Deferred**: adding `go vet`/`go test` to `.githooks/pre-commit` (would
  make Go a hard requirement for every commit — maintainer's call).
