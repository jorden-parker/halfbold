# Plan 005: Press `p` in the picker to preview a font's half-bold look in the browser

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 56a59d9..HEAD -- tui/ README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (additive Go code inside `tui/`; Python source untouched; the only side effects are one HTML file written to the OS temp dir and `open` launching the default browser)
- **Depends on**: none (plans 001–004 are DONE and merged; this builds on them)
- **Category**: direction
- **Planned at**: commit `56a59d9`, 2026-09-16

## Why this matters

The picker (`tui/`) lists every convertible font on disk, but the only way to
see what a font looks like — let alone what its half-bold twin looks like — is
to convert it, install it, and open some app. The maintainer asked for a way
to preview fonts straight from the picker.

A terminal cannot draw glyphs, and the maintainer runs Ghostty inside tmux,
where inline-image protocols need passthrough tweaks and are fragile. So the
preview is a small HTML page opened in the default browser. It renders one
sample paragraph three ways with the picked font:

1. plain (the font as it is),
2. **simulated half-bold**: the first `ceil(n/2)` letters of every word
   wrapped in `<b>`, using the real Bold face (or the variable font at weight
   700) — this needs no conversion and closely matches what halfbold produces,
3. the **real Half font**, when the `-Half.ttf` for that candidate already
   exists on disk, with `calt` on — so the user can compare.

Verified on 2026-09-16 in the maintainer's Chrome: installed fonts resolve by
family name, `@font-face` with `url()` to a local `.ttf` loads, `<b>` inside a
paragraph picks the Bold face, and the real Half font bolds word starts via
`calt`. Screenshot showed the simulated and real versions side by side.

## Current state

### Repo facts

- Python package in `src/halfbold/` does the conversion. **Do not modify it.**
- Go module `halfbold/tui` in `tui/` (`go 1.27.1`, Bubble Tea v1.3.10,
  Bubbles v1.0.0, Lipgloss v1.1.0). Run everything with `go -C tui …` from the
  repo root.
- Repo conventions (from `AGENTS.md`): **no code comments**; Conventional
  Commits (`feat:`, `fix:`, `chore:`); after changes run
  `go -C tui vet ./... && go -C tui test ./...` and fix everything reported.
  Name things well instead of commenting.
- No `CONTEXT.md` or `docs/adr/` exist. Nothing to honor there.
- macOS only. `open FILE` opens a file in the default app (`/usr/bin/open`).
- The maintainer's own Chrome extension (`chrome-extension/halfbold.css`)
  runs on **every** URL, including `file://` pages, and forces
  `font-family: var(--halfbold-sans) !important` on almost every element via a
  `:where(...)` selector (zero specificity). A page rule with `!important` and
  any specificity beats it. **Every `font-family` in the preview page must be
  `!important`**, or the preview will silently show the extension's font
  instead. This was observed in the verification run.

### Files (all in `tui/`)

- `fonts.go` — `candidate{label, regular, bold, kind}`; `familyName(c)` strips
  a trailing ` (variable)`; `outputPath(c, outDir)` returns
  `<outDir>/<label without spaces>-Half.ttf`. Excerpt (`tui/fonts.go:24-29`, `:275-283`):

  ```go
  type candidate struct {
  	label   string
  	regular string
  	bold    string
  	kind    string
  }

  func familyName(c candidate) string {
  	return strings.TrimSuffix(c.label, " (variable)")
  }

  func outputPath(c candidate, outDir string) string {
  	label := familyName(c)
  	name := strings.ReplaceAll(label, " ", "") + "-Half.ttf"
  	return filepath.Join(outDir, name)
  }
  ```

  `c.bold == ""` means a single variable font at `c.regular`; otherwise
  `c.regular` and `c.bold` are the Regular and Bold files of a static pair.
  The Half font's family name (as written by `src/halfbold/build.py`
  `rename_font`) is `familyName(c) + " Half"`.

- `run.go` — `runner{project}` builds `uv` argv in pure functions
  (`args`, `webArgs`) and wraps `exec.Command` in `tea.Cmd`s returning
  `runDoneMsg{output, err}`. Excerpt (`tui/run.go:21-26`):

  ```go
  func (r runner) run(c candidate, out string) tea.Cmd {
  	return func() tea.Msg {
  		output, err := exec.Command("uv", r.args(c, out)...).CombinedOutput()
  		return runDoneMsg{output: string(output), err: err}
  	}
  }
  ```

- `model.go` — Bubble Tea model. Screens: `screenPick`, `screenRunning`,
  `screenDone`, `screenBrewLoading`, `screenBrewPick`, `screenBrewInstalling`,
  `screenCaskPick`, `screenSlotPick`. Key handling is a `switch msg.String()`
  inside `case tea.KeyMsg`. The `s` key is the exemplar for "act on the
  selected row" (`tui/model.go:167-176`):

  ```go
  		case "s":
  			if m.screen == screenPick && m.list.FilterState() != list.Filtering {
  				selected, ok := m.list.SelectedItem().(item)
  				if !ok {
  					return m, nil
  				}
  				m.chosen = selected.c
  				m.screen = screenSlotPick
  				return m, nil
  			}
  ```

  `startRun` computes the output dir (`tui/model.go:112-121`):

  ```go
  func (m model) startRun(c candidate) (model, tea.Cmd) {
  	m.chosen = c
  	m.slot = ""
  	m.screen = screenRunning
  	dir := m.outDir
  	if dir == "" {
  		dir = filepath.Dir(m.chosen.regular)
  	}
  	out := outputPath(m.chosen, dir)
  	return m, tea.Batch(m.spinner.Tick, m.runner.run(m.chosen, out))
  }
  ```

  `runDoneMsg` handling (`tui/model.go:240-244`) sets `m.output`, `m.err`,
  `m.screen = screenDone`. `doneView` (`tui/model.go:329-340`) renders
  `m.output` red via `errorStyle` when `m.err != nil`.

  The default `View` help line (`tui/model.go:324-325`):

  ```go
  	default:
  		return m.list.View() + "\n" + helpStyle.Render("enter: convert  s: use on web  i: install from Homebrew  /: filter  q: quit")
  ```

- `run_test.go`, `brew_test.go` — the test style: table-free, one `Test…`
  per case, `reflect.DeepEqual` on argv slices, `t.Fatalf("got %v, want %v")`.
- `model_test.go` — drives `model.Update` with `tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("s")}`
  and asserts on the returned `model`'s fields. Model it.

### Repo README

`README.md` has an "Interactive picker" section (lines 11–22) listing the keys.
It gets one new sentence.

## Commands you will need

| Purpose   | Command                                            | Expected on success |
|-----------|----------------------------------------------------|---------------------|
| Vet       | `go -C tui vet ./...`                              | exit 0, no output   |
| Tests     | `go -C tui test ./...`                             | `ok  	halfbold/tui` |
| Build     | `go -C tui build -o /dev/null .`                   | exit 0              |
| Run TUI   | `go run -C tui . -project ..`                      | picker appears      |
| Python    | `uv run ruff check . && uv run ruff format --check . && uv run pytest` | all pass (must stay green; you touch no Python) |

## Scope

**In scope** (the only files you should modify or create):
- `tui/preview.go` (create)
- `tui/preview_test.go` (create)
- `tui/model.go`
- `tui/model_test.go`
- `README.md` (one sentence in "Interactive picker")

**Out of scope** (do NOT touch):
- `src/halfbold/**`, `tests/**` — Python conversion; untouched.
- `chrome-extension/**` — do not weaken the extension's `!important` rules to
  make the preview work; the preview page uses `!important` itself.
- `tui/fonts.go`, `tui/run.go`, `tui/brew.go`, `tui/main.go` — no changes
  needed; do not add fields to `candidate`.
- Any inline-image / terminal-graphics approach (kitty, iTerm2, sixel).
  Rejected: fragile through tmux, and the maintainer's terminal is tmux.
- Plan 006 (Homebrew cask preview) — separate plan; leave `screenBrewPick`
  keys alone.

## Git workflow

- Branch: `advisor/005-preview-installed-font`
- Commit per step; Conventional Commits, e.g. `feat: tui previews a font in the browser with p`
  (see `git log`: `feat: tui sets the extension's active font with s`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Pure HTML builders in `tui/preview.go`

Create `tui/preview.go` with `package main` and these symbols. Use only the
standard library (`html`, `strings`, `unicode`, `os`, `path/filepath`,
`os/exec`) plus `tea "github.com/charmbracelet/bubbletea"`.

```go
const previewText = "Reading is faster when the first half of every word is bold. " +
	"Your eyes fixate on the bold letters and your brain completes the rest, " +
	"so long sentences like this one feel shorter than they are."
```

**`func boldPrefixLength(n int) int`** — returns `(n + 1) / 2` (this is
`ceil(n/2)`, identical to `bold_prefix_length` in `src/halfbold/build.py`).

**`func halfboldHTML(text string) string`** — walks `text` rune by rune. A
"word" is a maximal run of runes for which `unicode.IsLetter` is true. For
each word of length n it emits `<b>` + the first `boldPrefixLength(n)` letters
+ `</b>` + the remaining letters. Everything else (spaces, punctuation, digits)
passes through unchanged. All text (inside and outside words) goes through
`html.EscapeString`. Single-letter words: n=1 → prefix 1 → `<b>a</b>`.

**`type previewPage struct`** with fields `family string` (the CSS family
name), `regular string` (file path), `bold string` (file path, empty for a
variable font), `half string` (path to the existing `-Half.ttf`, empty if it
does not exist), `label string` (display label).

**`func previewHTML(p previewPage) string`** — returns a complete HTML
document. Required content, in this order:

1. `<!doctype html><meta charset="utf-8"><title>halfbold preview: LABEL</title>`
2. A `<style>` block containing:
   - `@font-face` rules for a family named exactly `halfbold-preview`:
     - if `p.bold == ""` (variable): one rule,
       `src:url("file://REGULAR");font-weight:100 900;`
     - else: two rules, weight `400` → `url("file://REGULAR")`, weight `700`
       → `url("file://BOLD")`.
     Paths go through `html.EscapeString` and must be absolute (they already
     are; `scanFonts` joins the scan dir).
   - `body{font-size:28px;line-height:1.4;max-width:60ch;margin:40px auto;font-family:"halfbold-preview","FAMILY",sans-serif !important}`
     — `"halfbold-preview"` first so the `file://` face is used when it
     loads, and the installed family by name as the fallback.
   - `h1,h2{font-size:14px;font-weight:400;color:#888;margin:32px 0 8px;font-family:system-ui,sans-serif !important}`
   - `.half{font-family:"FAMILY Half",sans-serif !important;font-feature-settings:"calt" 1 !important}`
   - `.plain{font-feature-settings:"calt" 0 !important}` (turns `calt` off
     on the plain and simulated blocks; the maintainer's extension forces it
     on everywhere, and the raw font may carry its own `calt` ligatures)
3. `<h1>LABEL</h1>`
4. `<h2>plain</h2><p class="plain">TEXT</p>` where TEXT is the escaped `previewText`.
5. `<h2>simulated half-bold (first half of each word in the Bold face)</h2><p class="plain">` + `halfboldHTML(previewText)` + `</p>`
6. If `p.half != ""`: `<h2>installed Half font (FAMILY Half, calt on)</h2><p class="half">TEXT</p>`.
   Else: `<h2>installed Half font</h2><p class="plain">not built yet: press enter in the picker to convert this font</p>`.

`FAMILY` and `LABEL` go through `html.EscapeString`. Build with a
`strings.Builder`; no `html/template` needed.

**`func previewPath() string`** — returns
`filepath.Join(os.TempDir(), "halfbold-preview.html")`. One fixed file,
overwritten each time, so previews never pile up.

**`func openArgs(path string) []string`** — returns `[]string{path}` (the argv
for `open`). Trivial, but it keeps the exec call testable like `brewInstallArgs`.

**`type previewDoneMsg struct{ err error }`**

**`func openPreview(p previewPage) tea.Cmd`** — returns a `tea.Cmd` that
writes `previewHTML(p)` to `previewPath()` with `os.WriteFile(path, []byte(html), 0o644)`,
then runs `exec.Command("open", openArgs(path)...).CombinedOutput()`; on either
error return `previewDoneMsg{err: fmt.Errorf("preview: %w", err)}` (wrap the
`open` stderr into the error the way `brew.search` does in `tui/brew.go:93-98`).
On success return `previewDoneMsg{}`.

**Verify**: `go -C tui vet ./...` → exit 0. `go -C tui build -o /dev/null .` → exit 0.

### Step 2: Tests for the pure functions in `tui/preview_test.go`

Write these tests (model after `tui/brew_test.go`):

- `TestBoldPrefixLength`: n=1→1, 2→1, 3→2, 4→2, 7→4, 20→10.
- `TestHalfboldHTMLWrapsFirstHalfOfEachWord`:
  `halfboldHTML("Reading with a")` → `"<b>Read</b>ing <b>wi</b>th <b>a</b>"`.
- `TestHalfboldHTMLLeavesPunctuationAndDigits`:
  `halfboldHTML("ok, 42!")` → `"<b>o</b>k, 42!"`.
- `TestHalfboldHTMLEscapes`: `halfboldHTML("a<b")` → `"<b>a</b>&lt;<b>b</b>"`.
- `TestPreviewHTMLVariableFont`: `previewHTML(previewPage{family:"Inter",label:"Inter",regular:"/f/InterVariable.ttf"})`
  contains `url("file:///f/InterVariable.ttf")` and `font-weight:100 900`;
  because `half == ""` it must NOT contain `class="half"` and MUST contain
  `not built yet`.
- `TestPreviewHTMLPairWithHalf`: `previewPage{family:"Mono",label:"Mono",regular:"/f/Mono-Regular.ttf",bold:"/f/Mono-Bold.ttf",half:"/f/Mono-Half.ttf"}`
  → contains `url("file:///f/Mono-Regular.ttf")`, `url("file:///f/Mono-Bold.ttf")`,
  `font-weight:400`, `font-weight:700`, `class="half"`, `"Mono Half"`, and
  does NOT contain `not built yet`.
- `TestPreviewHTMLEscapesLabel`: label `A&B` → page contains `A&amp;B`, not `A&B<`.
- `TestOpenArgs`: `openArgs("/tmp/x.html")` → `[]string{"/tmp/x.html"}`.
- `TestPreviewPathIsFixedFileInTempDir`: `filepath.Base(previewPath()) == "halfbold-preview.html"`.

**Verify**: `go -C tui test ./... -run 'BoldPrefix|HalfboldHTML|PreviewHTML|OpenArgs|PreviewPath' -v` → all PASS.

### Step 3: Wire the `p` key into `tui/model.go`

1. Add a method on `model`:

   ```go
   func (m model) previewFor(c candidate) previewPage {
   	dir := m.outDir
   	if dir == "" {
   		dir = filepath.Dir(c.regular)
   	}
   	half := outputPath(c, dir)
   	if _, err := os.Stat(half); err != nil {
   		half = ""
   	}
   	return previewPage{
   		family:  familyName(c),
   		label:   c.label,
   		regular: c.regular,
   		bold:    c.bold,
   		half:    half,
   	}
   }
   ```

   Then simplify `startRun` to reuse the same dir logic only if it stays a
   one-line change; otherwise leave `startRun` as is (duplication of three
   lines is acceptable here). Add `"os"` to the imports.

2. In the `tea.KeyMsg` switch, add a `case "p":` directly after `case "s":`,
   mirroring its shape but allowed on both list screens:

   ```go
   		case "p":
   			if (m.screen == screenPick || m.screen == screenCaskPick) && m.list.FilterState() != list.Filtering {
   				selected, ok := m.list.SelectedItem().(item)
   				if !ok {
   					return m, nil
   				}
   				return m, openPreview(m.previewFor(selected.c))
   			}
   ```

   The screen does not change: the browser opens next to the terminal and
   the user keeps browsing the list.

3. Handle the result: add a `case previewDoneMsg:` next to `case runDoneMsg:`:

   ```go
   	case previewDoneMsg:
   		if msg.err != nil {
   			m.err = msg.err
   			m.output = msg.err.Error()
   			m.screen = screenDone
   		}
   		return m, nil
   ```

4. Update the default help line to
   `"enter: convert  p: preview  s: use on web  i: install from Homebrew  /: filter  q: quit"`.

**Verify**: `go -C tui vet ./... && go -C tui test ./...` → exit 0, `ok`.

### Step 4: Model tests in `tui/model_test.go`

Add, modelled on `TestSlotPickEnterUsesDetectedKind`:

- `TestPreviewKeyStaysOnPickScreenAndReturnsCmd`: build `newModel` with one
  candidate, send `p`; assert `m2.screen == screenPick` and the returned
  `tea.Cmd` is non-nil.
- `TestPreviewKeyIgnoredWhileFiltering`: send `/` then `p`; assert the
  returned cmd is nil or the screen is still `screenPick` and
  `m.list.FilterState() == list.Filtering` (the `p` was consumed by the
  filter input). Assert `m2.list.FilterValue() == "p"` — that proves the key
  reached the filter, not the preview.
- `TestPreviewForFindsExistingHalf`: create `t.TempDir()`, write an empty
  file `Inter-Half.ttf` in it, build a model with `outDir` = that dir and a
  candidate `{label:"Inter", regular:"/f/InterVariable.ttf"}`; assert
  `m.previewFor(c).half` equals the temp path. Then a second candidate
  `{label:"Nope", …}` → `half == ""`.
- `TestPreviewDoneErrorShowsDoneScreen`: send `previewDoneMsg{err: errors.New("x")}`
  → `screen == screenDone`, `err != nil`. Send `previewDoneMsg{}` from
  `screenPick` → stays `screenPick`.

**Verify**: `go -C tui test ./... -v -run Preview` → all PASS. Then the full
`go -C tui vet ./... && go -C tui test ./...` → `ok`.

### Step 5: Manual check in the real browser

Run `go run -C tui . -project ..`, move to a font that already has a Half
twin (e.g. `Inter`, whose `Inter-Half.ttf` is in `~/Library/Fonts`), press `p`.

Expected: the default browser opens `file:///…/halfbold-preview.html`
showing three paragraphs. The second has the first half of each word in bold.
The third looks the same as the second (the real Half font). The picker is
still on the list. If the page shows one uniform sans font for everything,
the `!important` rules are missing — fix and re-check.

Then press `p` on a font without a Half twin: the third block reads
`not built yet: press enter in the picker to convert this font`.

Record what you saw (which browser, whether the `file://` face loaded — the
page uses the installed family as fallback so the paragraph renders either
way) in your final report.

**Verify**: `ls -la "$TMPDIR/halfbold-preview.html"` → file exists, size > 1 KB.

### Step 6: README

In `README.md`, "Interactive picker" section, after the sentence about `s`
(the paragraph starting `Each row shows the font's kind`), add:

> Press `p` to preview the highlighted font in your browser: the sample
> paragraph is shown plain, with a simulated half-bold (first half of each
> word in the Bold face), and in the installed Half font when one exists.

**Verify**: `grep -n 'Press `p`' README.md` → one match.

## Test plan

- New: `tui/preview_test.go` (9 tests listed in Step 2) and four model tests
  in `tui/model_test.go` (Step 4).
- Pattern: `tui/brew_test.go` for pure functions, `tui/model_test.go` for
  `Update`-driven tests.
- Verification: `go -C tui test ./...` → `ok`, 13 new tests included
  (`go -C tui test ./... -v 2>&1 | grep -c '^--- PASS'` increases by 13).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `go -C tui vet ./...` exits 0
- [ ] `go -C tui test ./...` prints `ok  	halfbold/tui`
- [ ] `go -C tui build -o /dev/null .` exits 0
- [ ] `grep -c '!important' tui/preview.go` ≥ 4
- [ ] `grep -n 'case "p":' tui/model.go` → one match
- [ ] `grep -n 'Press `p`' README.md` → one match
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest` still pass (no Python touched)
- [ ] `git status --porcelain` lists only files in the in-scope list
- [ ] `plans/README.md` status row for 005 updated

## STOP conditions

Stop and report back (do not improvise) if:

- The excerpts in "Current state" do not match `tui/model.go` / `tui/fonts.go`.
- `open` is not at `/usr/bin/open` (you are not on macOS); this plan assumes macOS.
- In Step 5 the preview paragraphs render in a different font than expected
  even after adding `!important` — report the computed `font-family` from the
  browser's inspector; do not start editing `chrome-extension/`.
- You feel the need to add a field to `candidate` or change `groupCandidates`;
  that is out of scope — report instead.

## Maintenance notes

- The simulated half-bold uses `(n+1)/2`; if `bold_prefix_length` in
  `src/halfbold/build.py` ever changes, update `boldPrefixLength` in
  `tui/preview.go` and its test to match.
- Plan 006 reuses `previewHTML`, `previewPath`, `openArgs`, and
  `previewDoneMsg` for Homebrew casks (Google Fonts–hosted faces). Keep those
  signatures stable, or update 006 before changing them.
- Reviewer checklist: every `font-family` in the generated CSS carries
  `!important`; the `p` key is refused while the list filter is active; the
  Half family name is `familyName(c) + " Half"` (matches `rename_font`).
- Deferred: previewing in the terminal via kitty graphics (needs tmux
  `allow-passthrough`); a `-preview-text` flag to change the sample paragraph.
