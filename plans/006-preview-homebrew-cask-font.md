# Plan 006: Press `p` on a Homebrew cask to preview the font before installing it

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat <SHA where plan 005 was merged>..HEAD -- tui/ README.md`
> (Plan 005 must be DONE first; take its merge commit from `plans/README.md`.)
> If any in-scope file changed since then, compare the "Current state"
> excerpts against the live code before proceeding; on a mismatch, treat it
> as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (additive Go code inside `tui/`; runs `brew info` (read-only) and `open`; nothing is installed)
- **Depends on**: plans/005-preview-installed-font-in-browser.md (must be DONE and merged; this plan calls `previewHTML`, `previewPath`, `openArgs`, `previewDoneMsg` from `tui/preview.go`)
- **Category**: direction
- **Planned at**: commit `56a59d9`, 2026-09-16 (written before 005 landed; the 005 symbols are specified in 005 Step 1 and re-listed below)

## Why this matters

The Homebrew list in the picker (`i` key) shows ~2600 cask tokens by name
only. To see whether a font is worth installing the user has to install it,
which also writes a dozen files into `~/Library/Fonts`. The maintainer asked
to preview a font "also from homebrew".

Downloading the cask archive without installing was rejected: a sample of 44
`font-*` casks on 2026-09-16 used eight download formats (`.zip`, bare `.ttf`,
`.tar.xz`, `.tar.gz`, `.dmg`, `.exe`, git checkouts…). Not worth it.

Instead, `brew info --cask --json=v2 TOKEN` (~1 s, works for uninstalled
casks) returns the cask's `homepage`. In that same sample 30 of 44 casks had a
`https://fonts.google.com/specimen/<Family>` homepage. For those, Google
Fonts serves the family over its CSS API, so the **same three-paragraph
preview page from plan 005** can render it — no download, no install. For
every other cask the TUI opens the homepage in the browser, which is the best
free preview available. Verified 2026-09-16 in the maintainer's Chrome: a
`<link>` to `https://fonts.googleapis.com/css2?family=Sofia+Sans:wght@400;700&display=swap`
rendered the simulated half-bold paragraph correctly; `family=Righteous:wght@400;700`
(Righteous has no 700) still returned HTTP 200 and rendered with a
synthesized bold; an unknown family returns HTTP 400 (the page then falls
back to `sans-serif`, which is acceptable for a preview).

## Current state

### Repo facts

- Go module `halfbold/tui` in `tui/` (`go 1.27.1`, Bubble Tea v1.3.10,
  Bubbles v1.0.0). Run everything with `go -C tui …` from the repo root.
- Conventions (from `AGENTS.md`): **no code comments**; Conventional Commits;
  after changes run `go -C tui vet ./... && go -C tui test ./...` and fix
  everything reported.
- macOS only; `/usr/bin/open URL` opens a URL in the default browser.
- The maintainer's Chrome extension forces `font-family … !important` on
  every page. Plan 005's `previewHTML` already emits `!important` on all its
  `font-family` rules; reuse it, do not write new CSS.

### Symbols from plan 005 (in `tui/preview.go`, must exist before you start)

```go
type previewPage struct {
	family  string
	regular string
	bold    string
	half    string
	label   string
}
func previewHTML(p previewPage) string
func previewPath() string
func openArgs(path string) []string
type previewDoneMsg struct{ err error }
func openPreview(p previewPage) tea.Cmd
```

`previewHTML` writes `@font-face` rules for a family named `halfbold-preview`
from `p.regular` / `p.bold` (`file://` URLs) and sets
`font-family:"halfbold-preview","<family>",sans-serif !important` on `body`.
For a Google-hosted font there is no local file, so this plan adds one field
and one `<link>` (Step 2).

### Files (all in `tui/`)

- `brew.go` — `brewInfoArgs(token)` returns
  `[]string{"info", "--cask", "--json=v2", token}`. `caskInfo` decodes only
  `token` and `artifacts` from the JSON (`tui/brew.go:44-54`):

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
  ```

  `brew.search()` / `brew.install()` (`tui/brew.go:91-125`) are the exemplars
  for running `brew` in a `tea.Cmd` and turning an `*exec.ExitError`'s stderr
  into the error message.

  Verified JSON shape (`brew info --cask --json=v2 font-sofia-sans`):
  `{"casks":[{"token":"font-sofia-sans","name":["Sofia Sans"],"homepage":"https://fonts.google.com/specimen/Sofia+Sans", …}]}`.
  `name` is a list (some casks list two names; use the first).

- `model.go` — `screenBrewPick` shows `m.brewList` of `caskItem{token}`.
  Enter installs (`tui/model.go:193-202`):

  ```go
  			case screenBrewPick:
  				if m.brewList.FilterState() != list.Filtering {
  					selected, ok := m.brewList.SelectedItem().(caskItem)
  					if !ok {
  						return m, nil
  					}
  					m.caskToken = selected.token
  					m.screen = screenBrewInstalling
  					return m, tea.Batch(m.spinner.Tick, m.brew.install(m.caskToken, m.fontsDir))
  				}
  ```

  `brewSearchMsg` handling shows how a brew error lands on `screenDone`
  (`tui/model.go:245-251`). `screenBrewPick`'s view is just `m.brewList.View()`
  (`tui/model.go:320-321`); the Bubbles list renders its own help line, so the
  `p` key is documented by editing the list's `AdditionalShortHelpKeys` **or**
  by appending a `helpStyle` line as the default screen does — pick the
  latter for consistency with `screenPick`.

- `brew_test.go` — `TestParseCaskFontTargetsUsesTarget` shows the pattern:
  a JSON literal as `[]byte`, call the parser, `reflect.DeepEqual`.

## Commands you will need

| Purpose | Command                                  | Expected on success |
|---------|------------------------------------------|---------------------|
| Vet     | `go -C tui vet ./...`                    | exit 0              |
| Tests   | `go -C tui test ./...`                   | `ok  	halfbold/tui` |
| Build   | `go -C tui build -o /dev/null .`         | exit 0              |
| Run TUI | `go run -C tui . -project ..`            | picker appears      |
| Probe   | `brew info --cask --json=v2 font-sofia-sans \| head -c 400` | JSON with `"homepage":"https://fonts.google.com/specimen/Sofia+Sans"` |

## Scope

**In scope** (the only files you should modify):
- `tui/brew.go`, `tui/brew_test.go`
- `tui/preview.go`, `tui/preview_test.go` (one new field + one branch, see Step 2)
- `tui/model.go`, `tui/model_test.go`
- `README.md` (one sentence in "Interactive picker")

**Out of scope** (do NOT touch):
- `src/halfbold/**`, `tests/**`, `chrome-extension/**`.
- `tui/fonts.go`, `tui/run.go`, `tui/main.go`.
- Downloading or extracting cask archives (`brew fetch`, unzip). Rejected, see above.
- Changing what Enter does on `screenBrewPick`.

## Git workflow

- Branch: `advisor/006-preview-homebrew-cask`
- Conventional Commits, e.g. `feat: tui previews a Homebrew font cask with p`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Parse `name` and `homepage` in `tui/brew.go`

1. Extend `caskInfo`'s inner struct with
   `Name []string `json:"name"`` and `Homepage string `json:"homepage"``.
   Existing `parseCaskFontTargets` keeps working unchanged.

2. Add:

   ```go
   type caskPreview struct {
   	token    string
   	name     string
   	homepage string
   }

   func parseCaskPreview(data []byte) (caskPreview, error)
   ```

   Unmarshal into `caskInfo`; error `"brew info returned no cask"` when
   `Casks` is empty (same message as `parseCaskFontTargets`); `name` is
   `Name[0]` when present, else the token.

3. Add the pure URL helpers:

   ```go
   const googleSpecimenPrefix = "https://fonts.google.com/specimen/"

   func googleFontsFamily(homepage string) (string, bool)
   ```

   Returns the path segment right after the prefix (up to the next `/`, `?`
   or `#`), with `+` replaced by a space, and `true`; otherwise `"", false`.
   Examples: `https://fonts.google.com/specimen/Sofia+Sans` → `"Sofia Sans", true`;
   `https://fonts.google.com/specimen/Noto+Sans+Elbasan?query=x` → `"Noto Sans Elbasan", true`;
   `https://fonts.google.com/earlyaccess` → `"", false`; `https://rsms.me/inter/` → `"", false`.

   ```go
   func googleFontsCSSURL(family string) string
   ```

   Returns `"https://fonts.googleapis.com/css2?family=" + url.QueryEscape(family) + ":wght@400;700&display=swap"`
   — but `url.QueryEscape` turns a space into `+`, which is what the API
   expects, and leaves `:`, `@`, `;` as `%3A`, `%40`, `%3B`. The API accepts
   those escaped or not; to keep the URL readable, escape only the family
   part and append the literal `:wght@400;700&display=swap`. Test:
   `googleFontsCSSURL("Sofia Sans")` → `https://fonts.googleapis.com/css2?family=Sofia+Sans:wght@400;700&display=swap`.

4. Add the message and command:

   ```go
   type brewPreviewMsg struct {
   	preview caskPreview
   	err     error
   }

   func (brew) info(token string) tea.Cmd
   ```

   Runs `exec.Command("brew", brewInfoArgs(token)...).Output()`; on error,
   wrap stderr like `brew.search` does and return
   `brewPreviewMsg{err: fmt.Errorf("brew info failed: %w", err)}`; else
   `parseCaskPreview` and return the result (with `token` set).

**Verify**: `go -C tui vet ./...` → exit 0.

### Step 2: Let `previewHTML` load a Google-hosted family

In `tui/preview.go`:

1. Add field `cssURL string` to `previewPage`.
2. In `previewHTML`, when `p.cssURL != ""`: emit
   `<link rel="stylesheet" href="ESCAPED_URL">` right after the `<title>`
   and **before** `<style>`, and emit **no** `@font-face` rules (there are no
   local files). The `body` rule stays as is — with no `halfbold-preview`
   face defined, the browser falls through to `"<family>"`, which the Google
   stylesheet defines.
3. When `p.cssURL == ""` behaviour is unchanged.

Add to `tui/preview_test.go`:

- `TestPreviewHTMLGoogleFontsUsesLinkNotFontFace`:
  `previewHTML(previewPage{family:"Sofia Sans",label:"Sofia Sans",cssURL:"https://fonts.googleapis.com/css2?family=Sofia+Sans:wght@400;700&display=swap"})`
  contains `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sofia+Sans:wght@400;700&amp;display=swap">`
  and does NOT contain `@font-face`.

**Verify**: `go -C tui test ./... -run PreviewHTML -v` → all PASS (the 005 tests still pass).

### Step 3: Wire `p` on the Homebrew list in `tui/model.go`

1. Add a screen `screenBrewInfo` to the `screen` const block (after
   `screenSlotPick`).
2. Extend the existing `case "p":` (added by plan 005) with a second branch:

   ```go
   			if m.screen == screenBrewPick && m.brewList.FilterState() != list.Filtering {
   				selected, ok := m.brewList.SelectedItem().(caskItem)
   				if !ok {
   					return m, nil
   				}
   				m.caskToken = selected.token
   				m.screen = screenBrewInfo
   				return m, tea.Batch(m.spinner.Tick, m.brew.info(m.caskToken))
   			}
   ```

3. Add `screenBrewInfo` to the `spinner.TickMsg` case list and to the `busy`
   expression in `case "q":` (so `q` does not quit mid-fetch).
4. Handle `brewPreviewMsg`:

   ```go
   	case brewPreviewMsg:
   		m.screen = screenBrewPick
   		if msg.err != nil {
   			m.err = msg.err
   			m.output = msg.err.Error()
   			m.screen = screenDone
   			return m, nil
   		}
   		if family, ok := googleFontsFamily(msg.preview.homepage); ok {
   			return m, openPreview(previewPage{
   				family: family,
   				label:  msg.preview.name + " (" + msg.preview.token + ")",
   				cssURL: googleFontsCSSURL(family),
   			})
   		}
   		return m, openURL(msg.preview.homepage)
   ```

   Add to `tui/preview.go`:

   ```go
   func openURL(target string) tea.Cmd
   ```

   which runs `exec.Command("open", openArgs(target)...)` and returns
   `previewDoneMsg{err}` exactly like `openPreview`'s second half — factor
   the shared "run open, wrap error" into a small unexported helper so the
   two do not duplicate it.

   `previewDoneMsg` with an error already lands on `screenDone` (005); a
   successful one is a no-op, so the user is back on the cask list.

5. `View` for `screenBrewInfo`:
   `fmt.Sprintf("%s brew info --cask %s …\n", m.spinner.View(), m.caskToken)`.
6. `View` for `screenBrewPick`: change to
   `m.brewList.View() + "\n" + helpStyle.Render("enter: install and convert  p: preview  /: filter  esc: back  q: quit")`
   and reduce the list height by one to make room: in the
   `tea.WindowSizeMsg` case, `m.brewList.SetSize(msg.Width, msg.Height-3)`
   (currently `-2`).

**Verify**: `go -C tui vet ./... && go -C tui test ./...` → `ok`.

### Step 4: Tests

`tui/brew_test.go`:

- `TestParseCaskPreviewReadsNameAndHomepage`: JSON
  `{"casks":[{"token":"font-sofia-sans","name":["Sofia Sans"],"homepage":"https://fonts.google.com/specimen/Sofia+Sans"}]}`
  → `caskPreview{token:"font-sofia-sans", name:"Sofia Sans", homepage:"https://fonts.google.com/specimen/Sofia+Sans"}`.
- `TestParseCaskPreviewFallsBackToToken`: `name` absent → `name == token`.
- `TestParseCaskPreviewRejectsEmptyCasks`.
- `TestGoogleFontsFamily`: the four examples from Step 1.3.
- `TestGoogleFontsCSSURL`: the example from Step 1.3.

`tui/model_test.go`:

- `TestBrewPickPreviewKeyFetchesInfo`: build a model, set
  `m.screen = screenBrewPick`, `m.brewList.SetItems([]list.Item{caskItem{token:"font-x"}})`,
  send `p` → `screen == screenBrewInfo`, `caskToken == "font-x"`, cmd non-nil.
- `TestBrewPreviewMsgGoogleOpensPreviewPage`: from `screenBrewInfo`, send
  `brewPreviewMsg{preview: caskPreview{token:"font-x", name:"X", homepage:"https://fonts.google.com/specimen/X"}}`
  → `screen == screenBrewPick`, cmd non-nil.
- `TestBrewPreviewMsgErrorShowsDone`: `brewPreviewMsg{err: errors.New("boom")}` → `screenDone`.

**Verify**: `go -C tui test ./... -v -run 'CaskPreview|GoogleFonts|BrewPick|BrewPreview'` → all PASS; full `go -C tui vet ./... && go -C tui test ./...` → `ok`.

### Step 5: Manual check

`go run -C tui . -project ..`, press `i`, wait for the list, type `/sofia`,
Enter to close the filter, move to `font-sofia-sans`, press `p`. Expected: a
spinner for about a second, then the browser opens the preview page titled
`halfbold preview: Sofia Sans (font-sofia-sans)` with three paragraphs in
Sofia Sans; the third block reads `not built yet`. The TUI is back on the
cask list. Then filter `/inter`, pick `font-inter`, press `p`: the browser
opens `https://rsms.me/inter/`.

Report which browser opened and whether the Google-hosted paragraph rendered
in the right font (compare with the specimen page if unsure).

### Step 6: README

In `README.md`, "Interactive picker", extend the `i` paragraph with:

> Press `p` on a cask to preview it first: Google Fonts families open in the
> same preview page (served by Google, nothing installed); other casks open
> their homepage.

**Verify**: `grep -c 'Press `p`' README.md` → `2`.

## Test plan

- 5 new tests in `tui/brew_test.go`, 1 in `tui/preview_test.go`, 3 in
  `tui/model_test.go` (Step 4). Pattern: existing tests in those files.
- `go -C tui test ./...` → `ok`, 9 more `--- PASS` lines than before.

## Done criteria

- [ ] `go -C tui vet ./...` exits 0
- [ ] `go -C tui test ./...` prints `ok  	halfbold/tui`
- [ ] `grep -n 'screenBrewInfo' tui/model.go` → ≥ 4 matches (const, key, tick, view)
- [ ] `grep -c 'Press `p`' README.md` → `2`
- [ ] `grep -rn 'brew fetch\|unzip' tui/` → no matches
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest` still pass
- [ ] `git status --porcelain` lists only in-scope files
- [ ] `plans/README.md` status row for 006 updated

## STOP conditions

Stop and report if:

- Plan 005 is not DONE, or `tui/preview.go` lacks any symbol listed under
  "Symbols from plan 005".
- `brew info --cask --json=v2 font-sofia-sans` does not return a `homepage`
  under `fonts.google.com/specimen/` (Homebrew changed its JSON or the cask
  moved).
- The `case "p":` block from plan 005 is shaped differently from the excerpt
  in 005 Step 3, so the second branch does not slot in cleanly.
- You are tempted to download the cask archive to preview non-Google fonts —
  that is out of scope; report the idea instead.

## Maintenance notes

- Google's `css2` API silently serves the closest weight when 700 is
  missing; the browser synthesizes bold. Good enough for a preview.
- If Homebrew's cask JSON drops the `homepage` field, `googleFontsFamily`
  returns false for everything and every cask opens an empty URL; a reviewer
  should check `openURL("")` cannot happen — guard with
  `if msg.preview.homepage == ""` → `screenDone` with a clear error.
- Reviewer checklist: `p` refused while the brew list filter is active;
  `q` refused during `screenBrewInfo`; the brew list height shrank by one to
  fit the new help line.
- Deferred: a "preview then install" shortcut from the browser back to the
  TUI; an offline fallback for non-Google casks.
