# Plan 002: Let the TUI install a font from a Homebrew cask and convert it in one flow

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 64d4948..HEAD -- tui/ README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (additive Go code inside `tui/`; Python source untouched; the only side effect is `brew install --cask`, which the user triggers by pressing Enter)
- **Depends on**: plans/001-bubbles-font-picker-tui.md (DONE, merged at `64d4948`)
- **Category**: direction
- **Planned at**: commit `64d4948`, 2026-09-16

## Why this matters

Today the TUI (`tui/`) only lists fonts that are already in `~/Library/Fonts`.
To try a new font the maintainer has to leave the TUI, remember the Homebrew
cask token, run `brew install --cask font-…`, restart the TUI, and pick the
font. The maintainer asked for this to become one flow inside the TUI:

1. press a key, pick a font cask from Homebrew's `font-*` list,
2. the TUI installs the cask (this installs the "main" font into `~/Library/Fonts`),
3. the TUI then runs `halfbold` on the freshly installed font and writes the
   `-Half.ttf` next to it, exactly as if the user had picked it from the list.

The maintainer chose the Go TUI as the home for this feature (not the Python
CLI) because the TUI already knows how to scan font files, group them into
Regular + Bold pairs or variable fonts, and shell out to `uv run halfbold`.
This plan reuses all of that. The Python package stays the single place that
converts fonts.

## Current state

### Repo facts

- Python package in `src/halfbold/` does the conversion. `uv run halfbold REGULAR [BOLD] -o OUT` is its CLI. **Do not modify it.**
- Go module `halfbold/tui` in `tui/` (`go 1.27.1`, Bubble Tea v1.3.10, Bubbles v1.0.0, Lipgloss v1.1.0). Go 1.27.1 is installed. Run everything with `go -C tui …` from the repo root.
- Homebrew 7.0.2 is installed at `/opt/homebrew`. Verified behaviors (2026-09-16):
  - `brew search --cask font-` prints one token per line, no header when stdout is not a TTY, ~1.5 s, ~2600 lines. It also includes non-font casks that merely contain "font" (`birdfont`, `fontforge-app`, …). Keep only lines starting with `font-`.
  - `brew search --cask <no-match>` still exits 0 (prints fuzzy matches).
  - `brew install --cask font-inter` installs font files straight into `~/Library/Fonts` (no sudo). Re-installing an installed cask exits 0 with `Warning: Not upgrading font-inter, the latest version is already installed`.
  - `brew info --cask --json=v2 <token>` works for installed **and** not-yet-installed casks. Unknown token: exit 1, stderr `Error: Cask 'x' is unavailable: No Cask with this name exists.`
  - Its JSON: `{"casks":[{"token":"font-inter","name":["Inter"],"installed":"4.1"|null,"artifacts":[{"font":["InterVariable.ttf"],"target":"/Users/jorden/Library/Fonts/InterVariable.ttf"}, …]}]}`. For font casks the artifact key set observed is exactly `font` and `target`. Some casks ship only `.otf` (CFF) files, which halfbold cannot convert; some ship dozens of `.ttf` files that group into several candidates (e.g. `font-jetbrains-mono-nerd-font` → "JetBrainsMono Nerd Font", "JetBrainsMono NF", "… Mono", "… Propo" variants).
- Repo conventions (from `AGENTS.md`): no code comments; Conventional Commits; run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` and `go -C tui vet ./... && go -C tui test ./...` after changes and fix everything they report. The `.githooks/pre-commit` hook runs the Python checks.
- No `CONTEXT.md` or `docs/adr/` exist. Nothing to honor there.

### Files (all in `tui/`)

- `main.go` — flag parsing (`-project`, `-out-dir`, `-list`, `-fonts`), builds `dirs`, calls `scanFonts` + `groupCandidates`, then `newModel(candidates, runner{project}, outDir)` and runs the Bubble Tea program.
- `model.go` — the Bubble Tea model: `screenPick` (list), `screenRunning` (spinner), `screenDone` (output). Keys: `enter` converts, `q`/`ctrl+c` quit, `esc`/`enter` on done returns to pick.
- `fonts.go` — `scanFonts(dirs) ([]fontFile, error)`, `readFont(path) (fontFile, bool, error)` (returns ok=false for non-TrueType, collections, unparsable), `groupCandidates([]fontFile) []candidate`, `outputPath(candidate, outDir) string`.
- `run.go` — `runner{project}` with `args(candidate, out) []string` and `run(candidate, out) tea.Cmd` that executes `uv run --project … halfbold …` and returns `runDoneMsg{output, err}`.
- `fonts_test.go`, `run_test.go` — table-free plain `testing` tests, `t.Fatalf` on mismatch, `reflect.DeepEqual` for slices.
- `../README.md` lines 10–29 document the picker and Homebrew usage.

### Excerpt: `tui/model.go:13-19` (screens)

```go
type screen int

const (
	screenPick screen = iota
	screenRunning
	screenDone
)
```

### Excerpt: `tui/model.go:40-54` (model struct)

```go
type runDoneMsg struct {
	output string
	err    error
}

type model struct {
	list    list.Model
	spinner spinner.Model
	screen  screen
	runner  runner
	outDir  string
	chosen  candidate
	output  string
	err     error
}
```

### Excerpt: `tui/model.go:91-107` (enter on the pick screen — the conversion trigger to reuse)

```go
		case "enter":
			switch m.screen {
			case screenPick:
				if m.list.FilterState() != list.Filtering {
					selected, ok := m.list.SelectedItem().(item)
					if !ok {
						return m, nil
					}
					m.chosen = selected.c
					m.screen = screenRunning
					dir := m.outDir
					if dir == "" {
						dir = filepath.Dir(m.chosen.regular)
					}
					out := outputPath(m.chosen, dir)
					return m, tea.Batch(m.spinner.Tick, m.runner.run(m.chosen, out))
				}
```

### Excerpt: `tui/model.go:139-148` (View)

```go
func (m model) View() string {
	switch m.screen {
	case screenRunning:
		return fmt.Sprintf("%s converting %s …\n", m.spinner.View(), m.chosen.label)
	case screenDone:
		return m.doneView()
	default:
		return m.list.View()
	}
}
```

### Excerpt: `tui/run.go` (whole file — the exec pattern to copy)

```go
type runner struct {
	project string
}

func (r runner) args(c candidate, out string) []string {
	base := []string{"run", "--project", r.project, "halfbold", c.regular}
	if c.bold != "" {
		base = append(base, c.bold)
	}
	return append(base, "-o", out)
}

func (r runner) run(c candidate, out string) tea.Cmd {
	return func() tea.Msg {
		output, err := exec.Command("uv", r.args(c, out)...).CombinedOutput()
		return runDoneMsg{output: string(output), err: err}
	}
}
```

### Excerpt: `tui/fonts.go:28-57` (scanFonts iterates directories; you will need a per-file variant)

```go
func scanFonts(dirs []string) ([]fontFile, error) {
	var files []fontFile
	for _, dir := range dirs {
		entries, err := os.ReadDir(dir)
		...
			path := filepath.Join(dir, name)
			font, ok, err := readFont(path)
			if err != nil {
				return nil, err
			}
			if !ok {
				continue
			}
			files = append(files, font)
		}
	}
	return files, nil
}
```

### Excerpt: `tui/main.go:77-81` (how the model is built today)

```go
	r := runner{project: absProject}
	m := newModel(candidates, r, *outDir)
	if _, err := tea.NewProgram(m, tea.WithAltScreen()).Run(); err != nil {
```

### Excerpt: `tui/run_test.go:8-16` (test style to match)

```go
func TestRunnerArgsVariable(t *testing.T) {
	r := runner{project: "/repo"}
	c := candidate{label: "Inter", regular: "/fonts/InterVariable.ttf"}
	got := r.args(c, "/fonts/Inter-Half.ttf")
	want := []string{"run", "--project", "/repo", "halfbold", "/fonts/InterVariable.ttf", "-o", "/fonts/Inter-Half.ttf"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}
```

### Bubbles v1.0.0 `list.Model` methods you will use (verified in the module cache)

`SetItems([]Item) tea.Cmd`, `SetSize(w, h)`, `SelectedItem() Item`,
`FilterState() FilterState` (compare to `list.Filtering`), `ResetFilter()`,
`ResetSelected()`, the exported `Title string` field, and `NewStatusMessage(string) tea.Cmd`.

## Commands you will need

| Purpose | Command (from repo root) | Expected on success |
|---------|--------------------------|---------------------|
| Go build | `go -C tui build ./...` | exit 0, no output |
| Go vet | `go -C tui vet ./...` | exit 0, no output |
| Go tests | `go -C tui test ./...` | `ok  	halfbold/tui` |
| Go format check | `gofmt -l tui` | prints nothing |
| Python checks (must stay green, nothing changes) | `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` | `All checks passed!`, `N files already formatted`, `10 passed` |
| Manual smoke | `go run -C tui . -project ..` | TUI opens; footer help mentions `i: install from Homebrew` |
| Brew present | `brew --version` | `Homebrew 7.x` |

## Scope

**In scope** (the only files you should create or modify):
- `tui/brew.go` (create) — Homebrew command builders, output parsing, install command.
- `tui/brew_test.go` (create)
- `tui/model.go` — new screens, keys, messages.
- `tui/main.go` — pass `dirs` into the model so it can rescan after an install.
- `tui/fonts.go` — add `readFonts(paths []string)` helper.
- `tui/fonts_test.go` — one test for the helper.
- `README.md` — document the new key in the "Interactive picker" section.
- `plans/README.md` — status row only.

**Out of scope** (do NOT touch, even though they look related):
- `src/halfbold/**`, `tests/**`, `pyproject.toml`, `uv.lock` — the Python conversion is not part of this feature.
- `chrome-extension/**`.
- `tui/go.mod` / `tui/go.sum` — no new dependencies are needed. `encoding/json`, `os/exec`, `bufio`/`strings` are stdlib; the list and spinner components are already imported. If you believe a new dependency is required, that is a STOP condition.
- Do not add a `-brew` flag or any non-interactive install path to `main.go`; the feature is interactive only.
- Do not change the existing `-list` flag output or the existing conversion keys.

## Git workflow

- Branch: `advisor/002-brew-cask-install-in-tui`
- Commit per step or logical unit. Conventional Commits, enforced by `.githooks/commit-msg` (run `git config core.hooksPath .githooks` first). Examples from history: `feat: add bubble tea font picker tui`, `fix: reach code blocks inside shadow roots and keep mono precedence`. Suggested: `feat: install homebrew font casks from the tui`.
- Do NOT push or open a PR unless the operator instructed it.
- Do not write code comments (repo rule).

## Steps

### Step 1: Add the Homebrew helpers in `tui/brew.go`

Create `tui/brew.go` with these exact identifiers so the tests in Step 2 compile:

```go
package main

const fontCaskPrefix = "font-"

type brew struct{}

func brewSearchArgs() []string       // → []string{"search", "--cask", "font-"}
func brewInstallArgs(token string) []string  // → []string{"install", "--cask", token}
func brewInfoArgs(token string) []string     // → []string{"info", "--cask", "--json=v2", token}

func filterFontCaskTokens(lines []string) []string
```

`filterFontCaskTokens` trims each line, drops empty lines and any line that
does not start with `fontCaskPrefix`, and returns the rest in input order.

```go
type caskArtifact struct {
	Font   []string `json:"font"`
	Target string   `json:"target"`
}

type caskInfo struct {
	Casks []struct {
		Token     string         `json:"token"`
		Artifacts []caskArtifact `json:"artifacts"`
	} `json:"casks"`
}

func parseCaskFontTargets(data []byte, fontsDir string) ([]string, error)
```

`parseCaskFontTargets`:
- `json.Unmarshal` into `caskInfo`; on error return it.
- If `len(info.Casks) == 0` return `errors.New("brew info returned no cask")`.
- For each artifact of the first cask with `len(a.Font) > 0`: use `a.Target` if non-empty, else `filepath.Join(fontsDir, filepath.Base(a.Font[0]))`.
- Return the resulting paths (may be empty; that is not an error here).

Then the three `tea.Cmd` producers and their messages:

```go
type brewSearchMsg struct {
	tokens []string
	err    error
}

type brewInstallMsg struct {
	token      string
	candidates []candidate
	output     string
	err        error
}

func (brew) search() tea.Cmd
func (brew) install(token, fontsDir string) tea.Cmd
```

- `search()`: run `exec.Command("brew", brewSearchArgs()...).Output()`. On error return `brewSearchMsg{err: fmt.Errorf("brew search failed: %w", err)}` (wrap `*exec.ExitError` stderr into the message if available: `if ee, ok := err.(*exec.ExitError); ok { err = fmt.Errorf("%w: %s", err, strings.TrimSpace(string(ee.Stderr))) }`). On success split stdout by `\n`, pass through `filterFontCaskTokens`, return `brewSearchMsg{tokens: tokens}`.
- `install(token, fontsDir)`: 
  1. `exec.Command("brew", brewInstallArgs(token)...).CombinedOutput()` → on error return `brewInstallMsg{token, output: string(out), err}`.
  2. `exec.Command("brew", brewInfoArgs(token)...).Output()` → on error return the msg with `err` and the install output so far.
  3. `paths, err := parseCaskFontTargets(info, fontsDir)` → on error return it.
  4. `files, err := readFonts(paths)` (added in Step 3) → on error return it.
  5. `return brewInstallMsg{token: token, candidates: groupCandidates(files), output: string(out)}`.

Use the existing `runner` in `run.go` as the pattern: a value type, pure `args` functions, and a `tea.Cmd` closure that calls `exec.Command`.

**Verify**: `go -C tui build ./...` → exit 0 (the `readFonts` reference will fail until Step 3; if you prefer, do Step 3 first — order between Steps 1 and 3 is free).

### Step 2: Write `tui/brew_test.go`

Model after `tui/run_test.go` (plain `testing`, `reflect.DeepEqual`, `t.Fatalf`). Tests, each a separate `func TestXxx(t *testing.T)`:

1. `TestBrewSearchArgs` — `brewSearchArgs()` equals `[]string{"search", "--cask", "font-"}`.
2. `TestBrewInstallArgs` — `brewInstallArgs("font-inter")` equals `[]string{"install", "--cask", "font-inter"}`.
3. `TestBrewInfoArgs` — `brewInfoArgs("font-inter")` equals `[]string{"info", "--cask", "--json=v2", "font-inter"}`.
4. `TestFilterFontCaskTokensKeepsOnlyFontPrefix` — input `[]string{"birdfont", "font-inter", "  font-roboto ", "", "fontforge-app"}` → `[]string{"font-inter", "font-roboto"}`.
5. `TestParseCaskFontTargetsUsesTarget` — JSON `{"casks":[{"token":"font-inter","artifacts":[{"font":["InterVariable.ttf"],"target":"/f/InterVariable.ttf"},{"font":["extras/otf/Inter-Bold.otf"],"target":"/f/Inter-Bold.otf"}]}]}` with fontsDir `/ignored` → `[]string{"/f/InterVariable.ttf", "/f/Inter-Bold.otf"}`.
6. `TestParseCaskFontTargetsFallsBackToFontsDir` — artifact `{"font":["ttf/FiraCode-Bold.ttf"]}` (no target), fontsDir `/fonts` → `[]string{"/fonts/FiraCode-Bold.ttf"}`.
7. `TestParseCaskFontTargetsIgnoresNonFontArtifacts` — artifacts `[{"zap":[{"trash":"x"}]},{"font":["A.ttf"],"target":"/f/A.ttf"}]` → `[]string{"/f/A.ttf"}`.
8. `TestParseCaskFontTargetsRejectsEmptyCasks` — `{"casks":[]}` → non-nil error.

**Verify**: `go -C tui test ./... -run 'Brew|Cask'` → `ok  	halfbold/tui` with 8 tests passing (`-v` to see them).

### Step 3: Add `readFonts(paths []string)` to `tui/fonts.go`

Add, next to `scanFonts`, a function that takes explicit file paths instead of directories:

```go
func readFonts(paths []string) ([]fontFile, error) {
	var files []fontFile
	for _, path := range paths {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			continue
		}
		font, ok, err := readFont(path)
		if err != nil {
			return nil, err
		}
		if !ok {
			continue
		}
		files = append(files, font)
	}
	return files, nil
}
```

Missing files are skipped on purpose: a cask's declared targets can differ from what actually landed on disk, and the install already succeeded. Non-TrueType files (`.otf`) are skipped by `readFont` returning `ok=false`, exactly as in the directory scan.

Add one test to `tui/fonts_test.go`, modeled on `TestScanFontsSkipsHalfOutputAndMissingDir`: `TestReadFontsSkipsMissingAndNonTrueType` — write a file containing the bytes from `buildSfntHeader(t, "OTTO", [][4]byte{{'C','F','F',' '}})` into `t.TempDir()`, call `readFonts` with that path plus a non-existent path, expect no error and 0 files.

**Verify**: `go -C tui test ./...` → `ok  	halfbold/tui`.

### Step 4: Wire the screens into `tui/model.go`

Add three screens after `screenDone`:

```go
	screenBrewLoading
	screenBrewPick
	screenBrewInstalling
	screenCaskPick
```

Add to `model`: `brew brew`, `brewList list.Model`, `dirs []string`, `fontsDir string`, `caskToken string`, `width, height int`. Change `newModel` to `newModel(candidates []candidate, r runner, outDir string, dirs []string) model`; set `dirs` and `fontsDir = dirs[0]` (the first scanned directory is `~/Library/Fonts` by default and is where Homebrew installs). Build `brewList` with `list.New(nil, list.NewDefaultDelegate(), 0, 0)` and `Title = "halfbold: pick a Homebrew font cask to install"`. Define a tiny item type for it:

```go
type caskItem struct{ token string }

func (i caskItem) Title() string       { return i.token }
func (i caskItem) Description() string { return "brew install --cask " + i.token }
func (i caskItem) FilterValue() string { return i.token }
```

Behavior to implement in `Update`:

- `tea.WindowSizeMsg`: store width/height, call `SetSize` on **both** lists (`msg.Height-2`).
- Key `i` on `screenPick` when `m.list.FilterState() != list.Filtering`: set `screen = screenBrewLoading`, return `tea.Batch(m.spinner.Tick, m.brew.search())`. (Note: `i` must not fire while the user is typing a filter; the guard above handles that, same as the existing `q` guard.)
- `brewSearchMsg`: on `err` → `m.err = err; m.output = err.Error(); screen = screenDone`. Otherwise build `caskItem`s, `cmd := m.brewList.SetItems(items)`, `m.brewList.ResetFilter(); m.brewList.ResetSelected()`, `screen = screenBrewPick`, return cmd.
- On `screenBrewPick`: `esc` (when not filtering) → back to `screenPick`; `enter` (when not filtering) → read `SelectedItem().(caskItem)`, set `m.caskToken`, `screen = screenBrewInstalling`, return `tea.Batch(m.spinner.Tick, m.brew.install(token, m.fontsDir))`. Every other message while on this screen goes to `m.brewList.Update`, mirroring how `screenPick` forwards to `m.list.Update` today. The `q` quit guard must also check `m.brewList.FilterState()` when on this screen.
- `spinner.TickMsg`: keep the spinner ticking while `screen` is any of `screenRunning`, `screenBrewLoading`, `screenBrewInstalling`.
- `brewInstallMsg`:
  - always first refresh the main list so the newly installed fonts appear: `files, err := scanFonts(m.dirs)`; on nil error `m.list.SetItems(itemsFor(groupCandidates(files)))` (extract the small items-building loop from `newModel` into `func itemsFor([]candidate) []list.Item`). Ignore a rescan error (keep the old items).
  - `msg.err != nil` → `m.output = msg.output` (or `msg.err.Error()` if output is empty), `m.err = msg.err`, `screen = screenDone`.
  - `len(msg.candidates) == 0` → `m.err = fmt.Errorf("%s installed no convertible TrueType font (OTF-only or italic-only cask)", msg.token)`, `m.output = m.err.Error()`, `screen = screenDone`.
  - `len(msg.candidates) == 1` → start conversion immediately using the same code path as `enter` on `screenPick`. Extract that block into `func (m model) startRun(c candidate) (model, tea.Cmd)` and call it from both places.
  - otherwise → `m.list.SetItems(itemsFor(msg.candidates))`, `m.list.Title = msg.token + " installed: pick a font to convert"`, `m.list.ResetFilter(); m.list.ResetSelected()`, `screen = screenCaskPick`.
- On `screenCaskPick`: `enter` → `startRun` with the selected item (same guard as `screenPick`); `esc` (not filtering) → restore the full list (`scanFonts(m.dirs)` + `groupCandidates` + `SetItems`, title back to `"halfbold: pick a font to convert"`) and `screen = screenPick`; other messages forward to `m.list.Update`.
- `screenDone` → `enter`/`esc` currently return to `screenPick`. After a cask-driven conversion the list may still show the cask-only items with the cask title. Make the return-to-pick path always restore the full title (`"halfbold: pick a font to convert"`) and full items (rescan `m.dirs`). Do this in one helper `func (m model) showAllFonts() (model, tea.Cmd)` used by both `esc` on `screenCaskPick` and the done-screen return.

`View`:
- `screenBrewLoading` → `fmt.Sprintf("%s searching Homebrew font casks …\n", m.spinner.View())`
- `screenBrewInstalling` → `fmt.Sprintf("%s brew install --cask %s …\n", m.spinner.View(), m.caskToken)`
- `screenBrewPick` → `m.brewList.View()`
- `screenCaskPick` → `m.list.View()`
- `screenPick` → `m.list.View() + "\n" + helpStyle.Render("enter: convert  i: install from Homebrew  /: filter  q: quit")`. Reduce the `SetSize` height for the main list by one more line (`msg.Height-3`) so the help line fits.

`doneView` is unchanged, except the `body` for a successful cask install + conversion should keep whatever `runDoneMsg` produced (the `wrote … ` line). Do not append the `brew install` log on success; it is shown only on failure via `lastLines(m.output, 15)`.

**Verify**: `go -C tui vet ./... && go -C tui test ./...` → exit 0, `ok  	halfbold/tui`.

### Step 5: Pass `dirs` from `tui/main.go`

Change the call at `tui/main.go:78` to `newModel(candidates, r, *outDir, dirs)`. Nothing else in `main.go` changes. Note `dirs` is already computed above (default `~/Library/Fonts`, or the `-fonts` values).

Also relax the "no candidates found" exit at `tui/main.go:64-68`: with the install feature, an empty font directory is a valid starting state. Replace the `os.Exit(1)` with printing the same message to stderr **only when `-list` is set**; otherwise continue into the TUI with an empty list (the user can press `i`). Keep `-list` behavior unchanged apart from that.

**Verify**: `go -C tui build ./... && go -C tui vet ./...` → exit 0. `go run -C tui . -project .. -fonts /nonexistent` → opens the TUI with an empty list (previously exited with an error). Press `q`.

### Step 6: Manual smoke test

1. `go run -C tui . -project ..` → list of installed fonts, help line shows `i: install from Homebrew`.
2. Press `i` → spinner "searching Homebrew font casks", then a list of `font-…` tokens (~2600). Type `/` then `roboto` to filter, Enter on `font-roboto`.
3. Spinner "brew install --cask font-roboto …" (30–60 s on first download), then either the conversion spinner (Roboto ships a single variable `Roboto[wdth,wght].ttf` plus an italic, so exactly one candidate) and a done screen with `wrote /Users/…/Library/Fonts/Roboto-Half.ttf (… letter glyphs bolded)`.
4. Press Enter → back on the main list; `Roboto` now appears in it.
5. Press `i`, filter `jetbrains-mono-nerd`, Enter → after the (already installed, fast) install you land on `screenCaskPick` titled `font-jetbrains-mono-nerd-font installed: pick a font to convert` with several JetBrainsMono entries. `esc` returns to the full list.
6. Press `i`, filter `source-serif-4`, note this cask is OTF-only on some versions; if you land on the done screen with `installed no convertible TrueType font`, that is the intended path.

Clean up if you want: `brew uninstall --cask font-roboto` and delete `~/Library/Fonts/Roboto-Half.ttf`. Not required.

**Verify**: steps 1–5 behave as described. If step 3 fails because `brew` cannot download (offline), report it as an environment limitation, not a code bug, and still complete Step 7.

### Step 7: Document in `README.md`

In the "Interactive picker" section (lines 10–20), after the sentence about `-fonts DIR` / `-out-dir DIR`, add:

```
Press `i` to install a font from a Homebrew cask (`brew search --cask font-`) without leaving the picker. After `brew install --cask` finishes, the new font is converted straight away; when a cask ships several families you pick one first.
```

Keep the existing "Fonts from Homebrew work directly" block as-is.

**Verify**: `grep -n "Press \`i\`" README.md` → one match.

## Test plan

- New `tui/brew_test.go`: 8 tests listed in Step 2 (arg builders, token filter, JSON parsing incl. fallback target, non-font artifacts, empty casks).
- New test in `tui/fonts_test.go`: `TestReadFontsSkipsMissingAndNonTrueType`.
- No model/Update unit tests are required (the existing code has none either); Step 6 covers the interactive behavior manually.
- Pattern: `tui/run_test.go` for arg builders, `tui/fonts_test.go` for file-based tests.
- Verification: `go -C tui test ./...` → all pass, 9 new tests; `uv run pytest -q` → still `10 passed`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `go -C tui build ./... && go -C tui vet ./...` exit 0
- [ ] `gofmt -l tui` prints nothing
- [ ] `go -C tui test ./... -v 2>&1 | grep -c '^--- PASS'` ≥ 19 (10 existing + 9 new)
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` exit 0 (Python untouched)
- [ ] `git diff --stat 64d4948..HEAD -- src tests pyproject.toml uv.lock tui/go.mod tui/go.sum chrome-extension` shows no changes
- [ ] `grep -n '"i"' tui/model.go` shows the install key handler; `grep -n 'func (brew) install' tui/brew.go` matches
- [ ] `grep -n "Press \`i\`" README.md` → one match
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row for 002 updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations in "Current state" doesn't match the excerpts (the codebase drifted since `64d4948`).
- `brew --version` fails or `brew search --cask font-` prints no `font-` lines — the feature cannot be smoke-tested.
- `brew info --cask --json=v2 font-inter` no longer contains `artifacts[].font` / `artifacts[].target` in the shape shown above (Homebrew changed its JSON). Report the new shape.
- You find you need a new Go dependency (a text-input widget, a JSON library, …). The design above only needs stdlib plus the already-imported `list` and `spinner`.
- Implementing the feature seems to require changing `src/halfbold/cli.py` or any Python file.
- A step's verification fails twice after a reasonable fix attempt.

## Maintenance notes

- Homebrew's `--json=v2` schema is the only external contract. `parseCaskFontTargets` is the single place that reads it; if a future Homebrew adds nested artifact shapes, that function and its tests are what to update.
- `fontsDir` is `dirs[0]`. If someone passes `-fonts` pointing elsewhere, the fallback target path (used only when Homebrew omits `target`) may be wrong; Homebrew currently always sets `target`, so this is a corner case. A reviewer should confirm the fallback is only reached when `target` is empty.
- `brew install` can take a minute; the TUI stays responsive because the work runs in a `tea.Cmd` goroutine. Do not move it onto the Update path.
- Deferred on purpose: a non-interactive `-brew TOKEN` flag; a Python `halfbold --brew` mode; uninstall; upgrading casks. Add a new plan if wanted.
- Reviewer focus: the `q`/`i`/`enter` guards against `list.Filtering` on **both** lists, the title/items restoration in `showAllFonts`, and that nothing under `src/` changed.
