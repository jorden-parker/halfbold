# Plan 009: Press `p` in the picker to preview the highlighted font inside the terminal

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat <SHA where plan 008 was merged>..HEAD -- tui/ README.md`
> (Plan 008 must be DONE first; take its merge commit from `plans/README.md`.)
> If any in-scope file changed since then, compare the "Current state"
> excerpts against the live code before proceeding; on a mismatch, treat it
> as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (additive Go inside `tui/`; the only side effect is running `uv run halfbold --preview … --wait`, which draws into the terminal and writes nothing to disk)
- **Depends on**: plans/008-terminal-font-preview.md (DONE and merged — this plan shells out to the `--preview --wait` flags it adds)
- **Category**: direction
- **Planned at**: commit `56a59d9`, 2026-09-16 (written before 008 landed; the CLI contract it relies on is spelled out below)

## Why this matters

The picker lists every convertible font but cannot show what any of them
looks like. Plan 008 gives the CLI `halfbold --preview FONT --wait`, which
draws a half-bold sample as a kitty-graphics image in the terminal and waits
for enter. This plan binds it to `p` in the picker so the maintainer can
browse fonts and peek at each one without leaving the TUI. The maintainer
explicitly does not want a browser page.

## Current state

### Repo facts

- Go module `halfbold/tui` in `tui/` (Bubble Tea v1.3.10, Bubbles v1.0.0,
  Lipgloss v1.1.0). Run everything with `go -C tui …` from the repo root.
- Conventions (`AGENTS.md`): **no code comments**; Conventional Commits;
  after changes run `go -C tui vet ./... && go -C tui test ./...` and fix
  everything reported.
- The TUI already shells out to the Python CLI through `runner` in
  `tui/run.go`; every subprocess call has an `args` builder function with
  a unit test in `tui/run_test.go`. Match that.

### CLI contract from plan 008

```
uv run --project <repo> halfbold --preview <regular.ttf> [<bold.ttf>] --wait
```

Draws the image(s) on stdout, prints `enter: back`, blocks until a line
arrives on stdin, deletes the image, exits 0. On a terminal without kitty
graphics it prints `this terminal has no kitty graphics support; wrote
<png path>` instead of drawing, then still waits. Exit 1 with a message on
stdout for a bad font.

### `tui/run.go` (37 lines) — the subprocess wrapper

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

func (r runner) webArgs(kind, family string) []string {
	return []string{"run", "--project", r.project, "halfbold", "--" + kind, family}
}
```

### `tui/model.go` (347 lines)

- `candidate{label, regular, bold, kind}` (in `tui/fonts.go:24`); `bold ==
  ""` means variable font.
- Screens: `screenPick, screenRunning, screenDone, screenBrewLoading,
  screenBrewPick, screenBrewInstalling, screenCaskPick, screenSlotPick`
  (lines 16–25).
- Key handling is one `switch msg.String()` inside `case tea.KeyMsg:`
  (lines 151–231). The `s` key (lines 167–176) is the exemplar for "act on
  the highlighted item when not filtering":

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

- `runDoneMsg{output, err}` (line 51) moves the model to `screenDone`,
  whose view prints `m.output` (red on error) and `enter: back  q: quit`
  (lines 240–244, 329–339).
- Help line for the pick screen (line 325):

```go
		return m.list.View() + "\n" + helpStyle.Render("enter: convert  s: use on web  i: install from Homebrew  /: filter  q: quit")
```

- `tui/model_test.go` drives `Update` with `tea.KeyMsg{Type: tea.KeyRunes,
  Runes: []rune("s")}` and asserts on the returned model — copy that style.

### How to hand the terminal to a child process

Bubble Tea's `tea.ExecProcess(cmd *exec.Cmd, fn func(error) tea.Msg) tea.Cmd`
releases the terminal (leaves the alt screen, restores cooked mode), runs
the command attached to the real stdin/stdout, then re-enters the alt screen
and delivers `fn(err)` as a message. That is exactly what the preview needs:
the image is drawn on the main screen, `--wait` blocks on enter, then the
list comes back. Source: `github.com/charmbracelet/bubbletea@v1.3.10/exec.go`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Vet | `go -C tui vet ./...` | exit 0, no output |
| Tests | `go -C tui test ./...` | `ok  halfbold/tui` |
| Run | `go run -C tui . -project ..` | TUI opens |
| Preview CLI works | `uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf --png /tmp/p.png` | `wrote /tmp/p.png` (proves 008 is present) |

## Scope

**In scope**:
- `tui/run.go` — add `previewArgs` and `preview`
- `tui/run_test.go` — test `previewArgs`
- `tui/model.go` — `p` key, `previewDoneMsg`, help line
- `tui/model_test.go` — key tests
- `README.md` — one sentence in the "Interactive picker" section

**Out of scope**:
- Anything under `src/halfbold/` or `tests/` (Python side is plan 008).
- The Homebrew list (`screenBrewPick`) — plan 010 adds `p` there.
- `tui/brew.go`, `tui/fonts.go`.

## Git workflow

- Branch: `advisor/009-tui-preview-key`
- Conventional Commit, e.g. `feat: tui previews the highlighted font with p`
- Do not push or open a PR unless told to.

## Steps

### Step 1: `previewArgs` and `preview` in `tui/run.go`

```go
func (r runner) previewArgs(c candidate) []string {
	base := []string{"run", "--project", r.project, "halfbold", "--preview", c.regular}
	if c.bold != "" {
		base = append(base, c.bold)
	}
	return append(base, "--wait")
}

func (r runner) preview(c candidate) tea.Cmd {
	return tea.ExecProcess(exec.Command("uv", r.previewArgs(c)...), func(err error) tea.Msg {
		return previewDoneMsg{err: err}
	})
}
```

Add to `tui/run_test.go`, following `TestRunnerArgsPair`:

- `TestRunnerPreviewArgsVariable` → `[]string{"run", "--project", "/repo", "halfbold", "--preview", "/fonts/InterVariable.ttf", "--wait"}`
- `TestRunnerPreviewArgsPair` → the same with the bold path inserted before `--wait`.

**Verify**: `go -C tui test ./... -run Preview` → passes (the message type comes in Step 2; add it first if the build complains).

### Step 2: `p` key in `tui/model.go`

Add the message type next to `runDoneMsg`:

```go
type previewDoneMsg struct{ err error }
```

Add a key case after `"s"`:

```go
		case "p":
			if m.screen == screenPick && m.list.FilterState() != list.Filtering {
				selected, ok := m.list.SelectedItem().(item)
				if !ok {
					return m, nil
				}
				m.chosen = selected.c
				return m, m.runner.preview(selected.c)
			}
```

Handle the result next to `case runDoneMsg:`:

```go
	case previewDoneMsg:
		if msg.err != nil {
			m.err = msg.err
			m.output = "preview failed: " + msg.err.Error()
			m.screen = screenDone
		}
		return m, nil
```

On success nothing changes: the list is still on screen (Bubble Tea
re-enters the alt screen and repaints). Do **not** switch screens or reset
the selection — the user should land back on the row they previewed.

Update the pick-screen help line to:

```go
helpStyle.Render("enter: convert  p: preview  s: use on web  i: install from Homebrew  /: filter  q: quit")
```

`screenCaskPick` (the "cask installed, pick one" list) reuses `m.list`; let
`p` work there too by changing the condition to
`(m.screen == screenPick || m.screen == screenCaskPick)`.

**Verify**: `go -C tui vet ./...` → clean.

### Step 3: Model tests in `tui/model_test.go`

Following `TestSlotPickEscReturnsToList`:

- `TestPreviewKeyKeepsListAndReturnsCmd` — model with one candidate, send
  `p`; the returned model's `screen` is still `screenPick`, `chosen.label`
  is the candidate's label, and the returned `tea.Cmd` is non-nil.
- `TestPreviewKeyIgnoredWhileFiltering` — send `/` then `p`; the returned
  `tea.Cmd` is either nil or the list's own update, and `m.chosen` is
  unchanged (assert `chosen.label == ""`).
- `TestPreviewDoneErrorShowsDoneScreen` — send `previewDoneMsg{err: errors.New("boom")}`;
  `screen == screenDone`, `output` contains `boom`.
- `TestPreviewDoneSuccessStaysOnList` — send `previewDoneMsg{}`; `screen == screenPick`.

**Verify**: `go -C tui test ./...` → `ok`.

### Step 4: Manual check

In a Ghostty pane inside tmux with `tmux set -g allow-passthrough on`:

```sh
go run -C tui . -project ..
```

Highlight a font, press `p`. Expected: the TUI disappears, the preview image
is drawn, `enter: back` shows; press enter; the picker returns with the same
row highlighted and no image residue. Press `q`; the shell prompt is clean
(no leftover image on the main screen). Press `p` on a row while the list is
filtered (`/` then some letters): nothing happens except the filter
receiving the `p`.

### Step 5: README

In the "Interactive picker" section, after the sentence about `s`
(`Press \`s\` on a row …`), add:

> Press `p` to preview the highlighted font: the sample paragraph is drawn
> into the terminal half-bold and plain (see the `--preview` section below
> for terminal requirements); enter brings the picker back.

**Verify**: `grep -n "Press \`p\`" README.md` → one match.

## Test plan

See Steps 1 and 3. Pattern files: `tui/run_test.go`, `tui/model_test.go`.

## Done criteria

- [ ] `go -C tui vet ./... && go -C tui test ./...` exit 0, with the 2 + 4 new tests present
- [ ] `grep -n '"--preview"' tui/run.go` → one match; `grep -n 'case "p":' tui/model.go` → one match
- [ ] `grep -rn "open\b\|webbrowser\|http" tui/run.go tui/model.go` → no new matches (no browser)
- [ ] `git status` shows changes only under `tui/` and `README.md`
- [ ] `plans/README.md` row 009 updated

## STOP conditions

- `uv run halfbold --preview … --png` fails: plan 008 is not merged. Stop.
- `tea.ExecProcess` is not exported by the pinned Bubble Tea (`grep -n "func ExecProcess" $(go env GOMODCACHE)/github.com/charmbracelet/bubbletea@v1.3.10/exec.go` finds nothing).
- The key switch in `model.go` no longer matches the excerpt (a different
  key already uses `p`, or the help string moved).
- After enter, the picker comes back but the image stays painted over it —
  report; the fix belongs in plan 008's `kitty_delete_all`, not here.

## Maintenance notes

- `--wait` is what keeps the child alive long enough to see the image; if
  the CLI flag is renamed, `previewArgs` and its test must follow.
- Because the child owns the terminal, any error text it prints is visible
  directly; the `screenDone` path only fires for a non-zero exit.
- Plan 010 adds a `previewCask` builder next to `previewArgs`; keep the
  naming parallel.
