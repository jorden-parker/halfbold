# Plan 010: Preview a Homebrew font cask in the terminal before installing it (`halfbold --preview-cask`, `p` in the TUI's cask list)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat <SHA where plan 009 was merged>..HEAD -- src/halfbold/ tests/ tui/ README.md`
> (Plans 008 and 009 must be DONE first; take the merge commit from
> `plans/README.md`.) If any in-scope file changed since then, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW–MED (downloads a cask archive into Homebrew's own cache via `brew fetch`, or a few TTFs from GitHub into a temp dir; extracts into a temp dir; mounts `.dmg` read-only with `hdiutil`; installs nothing)
- **Depends on**: plans/008-terminal-font-preview.md (`preview_images`, `candidates_from_paths`, `--wait` semantics) and plans/009-tui-preview-key.md (`previewArgs` naming, `previewDoneMsg`)
- **Category**: direction
- **Planned at**: commit `56a59d9`, 2026-09-16

## Why this matters

The TUI's Homebrew list (`i`) shows ~2600 `font-*` cask tokens by name only.
To see whether a font is worth installing the user has to install it, which
drops a dozen files into `~/Library/Fonts`. The maintainer wants to preview a
cask "also from homebrew", in the terminal (no browser — plan 006's
homepage/Google-Fonts-CSS approach was rejected for that reason).

Two download paths cover nearly every font cask, verified on 2026-09-16:

1. **Google Fonts casks** (the majority; e.g. `font-roboto`,
   `font-source-serif-4`) declare `url "https://github.com/google/fonts.git"`
   with `url_specs: {"branch": "main", "only_path": "ofl/roboto"}` and
   artifacts like `Roboto[wdth,wght].ttf`. `brew fetch` would do a sparse
   git clone — slow. Instead fetch each artifact file directly from
   `https://raw.githubusercontent.com/google/fonts/<branch>/<only_path>/<file>`
   (returned HTTP 200 for `ofl/roboto/Roboto%5Bwdth,wght%5D.ttf`).
2. **Everything else** (`font-inter` → `Inter-4.1.zip`,
   `font-jetbrains-mono` → `JetBrainsMono-2.304.zip`, `font-hack-nerd-font`
   → `Hack.tar.xz`, `font-sf-mono` → `SF-Mono.dmg`): `brew fetch --cask
   TOKEN` downloads into Homebrew's cache without installing, and
   `brew --cache --cask TOKEN` prints the cached file's path (it prints the
   path even before the download; e.g.
   `~/Library/Caches/Homebrew/downloads/<sha>--Inter-4.1.zip`). Extract
   `.zip` / `.tar.*` with the standard library (`tarfile` handles `.xz`),
   a bare `.ttf`/`.otf` as-is, and `.dmg` via `hdiutil attach -readonly`.

Then plan 008's `candidates_from_paths` + `preview_images` render whatever
convertible TrueType fonts are inside. Casks that ship only `.otf`, `.ttc`
or an installer `.pkg` (SF Mono) get a clear "nothing to preview" message —
those are also the casks `halfbold` could not convert anyway.

## Current state

### Repo facts

- Python 3.14 + `uv`; package `src/halfbold/`; conventions: no code
  comments, Conventional Commits, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run pytest` must pass (`AGENTS.md`).
- Go TUI in `tui/`; `go -C tui vet ./... && go -C tui test ./...` must pass.
- `tui/brew.go` already runs `brew search`, `brew install`, `brew info
  --cask --json=v2` and parses `artifacts[].font` / `.target` with
  `parseCaskFontTargets` (lines 44–77). This plan does **not** reuse the Go
  parser: the whole cask-preview flow lives in Python so it is also a CLI
  feature (`halfbold --preview-cask TOKEN`) and the TUI just executes it,
  matching plan 009.

### After plan 008, `src/halfbold/preview.py` provides

- `preview_images(candidates, *, png, wait) -> list[str]` — renders up to 3
  candidates to the terminal (kitty graphics) or PNGs, handles `--wait`.
- `preview_candidates(target_dir, *, png, wait)` — `candidates_from_paths(sorted(target.rglob("*.ttf")))` then `preview_images`.
- `src/halfbold/scan.py`: `candidates_from_paths(paths) -> list[Candidate]`.

### After plan 008, `src/halfbold/cli.py` has

`--preview` (store_true, uses positional `regular [bold]`), `--png PATH`,
`--wait`, with mutual-exclusion checks in `parse_args` and a `if
args.preview:` branch in `main` that prints returned lines and returns 0, or
prints a `ValueError` and returns 1.

### After plan 009, `tui/run.go` has

```go
func (r runner) previewArgs(c candidate) []string { … "--preview", c.regular, …, "--wait" }
func (r runner) preview(c candidate) tea.Cmd { return tea.ExecProcess(exec.Command("uv", …), func(err error) tea.Msg { return previewDoneMsg{err: err} }) }
```

and `tui/model.go` handles `previewDoneMsg` (error → `screenDone`; success
→ no change).

### `tui/model.go` — the Homebrew list

- `screenBrewPick` shows `m.brewList` of `caskItem{token}` (lines 45–49).
- Enter on it (lines 193–202) installs:

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

- `screenBrewPick` view (line 318) is `m.brewList.View()` with no help line.

### `brew info --cask --json=v2 TOKEN` shape (fields this plan reads)

```json
{"casks": [{
  "token": "font-roboto",
  "url": "https://github.com/google/fonts.git",
  "url_specs": {"branch": "main", "only_path": "ofl/roboto"},
  "artifacts": [{"font": ["Roboto[wdth,wght].ttf"], "target": "…"}, …]
}]}
```

Non-git casks: `"url": "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"`,
`"url_specs": {}` (or absent), artifacts `{"font": ["fonts/ttf/JetBrainsMono-Bold.ttf"]}`.
`url_specs` may be missing entirely — treat as `{}`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `uv run pytest -q` | all pass |
| Lint/format | `uv run ruff check . && uv run ruff format --check .` | clean |
| Go | `go -C tui vet ./... && go -C tui test ./...` | `ok` |
| Cask JSON | `brew info --cask --json=v2 font-roboto` | JSON as above |
| Cache path | `brew --cache --cask font-inter` | a path ending in `--Inter-4.1.zip` |
| Fetch | `brew fetch --cask font-inter` | `Downloaded to: …` (or `Already downloaded`) |
| Manual | `uv run halfbold --preview-cask font-roboto` | image in the terminal |

## Scope

**In scope**:
- `src/halfbold/brewcask.py` (create) — cask metadata, download, extraction
- `src/halfbold/cli.py` — `--preview-cask TOKEN`
- `tests/test_brewcask.py` (create)
- `tui/run.go`, `tui/run_test.go` — `previewCaskArgs`, `previewCask`
- `tui/model.go`, `tui/model_test.go` — `p` on the Homebrew list, help line
- `README.md` — one sentence each in the picker and CLI sections

**Out of scope**:
- `src/halfbold/preview.py`, `scan.py`, `build.py` — consume only.
- `tui/brew.go` — the install flow stays as is; do not refactor its JSON
  parsing to share with Python.
- Installing anything, writing into `~/Library/Fonts`, or touching
  Homebrew's cache beyond what `brew fetch` does itself.
- Casks whose download is a `.pkg`, `.exe`, `.ttc` or non-Google git repo:
  report "nothing to preview", do not implement.

## Git workflow

- Branch: `advisor/010-preview-homebrew-cask-in-terminal`
- Conventional Commits, e.g. `feat: preview a Homebrew font cask in the terminal`
- Do not push or open a PR unless told to.

## Steps

### Step 1: `src/halfbold/brewcask.py` — metadata and download

```python
@dataclass(frozen=True)
class CaskInfo:
    token: str
    url: str
    branch: str
    only_path: str
    fonts: list[str]


def parse_cask_info(data: bytes) -> CaskInfo: ...
def cask_info(token: str) -> CaskInfo: ...
def google_fonts_urls(info: CaskInfo) -> list[str]: ...
def download_google_fonts(info: CaskInfo, into: Path) -> list[Path]: ...
def fetch_cask_archive(token: str) -> Path: ...
def extract_fonts(archive: Path, into: Path) -> list[Path]: ...
def cask_font_dir(token: str, into: Path) -> Path: ...
```

- `parse_cask_info` — `json.loads`; take `casks[0]`; `url_specs = cask.get("url_specs") or {}`;
  `fonts = [a["font"][0] for a in cask["artifacts"] if "font" in a]`
  (the `font` list has one entry per artifact in every cask seen). Empty
  `casks` → `ValueError(f"brew info returned no cask for {token}")`.
- `cask_info` — `subprocess.run(["brew", "info", "--cask", "--json=v2", token], capture_output=True, check=True)`;
  on `CalledProcessError` raise `ValueError(f"brew info failed: {stderr.strip()}")`.
- `google_fonts_urls` — only when `info.url == "https://github.com/google/fonts.git"`
  (exact) and `info.only_path`: return
  `f"https://raw.githubusercontent.com/google/fonts/{info.branch or 'main'}/{info.only_path}/{urllib.parse.quote(font)}"`
  for each font in `info.fonts` whose lowercased name ends with `.ttf` and
  does not contain `italic`. Any other git URL → `[]`.
- `download_google_fonts` — `urllib.request.urlopen(url, timeout=30)` each,
  write to `into / Path(font).name`; return the paths. Wrap `URLError` in
  `ValueError(f"download failed: {url}: {err.reason}")`.
- `fetch_cask_archive` — run `brew fetch --cask TOKEN` (`check=True`,
  stderr captured into the `ValueError` on failure), then
  `brew --cache --cask TOKEN` and return `Path(stdout.strip())`. If that path
  does not exist afterwards raise `ValueError(f"brew fetch left no file at {path}")`.
- `extract_fonts(archive, into)` by suffix (lowercased):
  - `.ttf` / `.otf`: copy into `into`, return `[copy]`.
  - `.zip`: `zipfile.ZipFile.extractall(into)` **after** checking every
    member name has no `..` component and is not absolute (raise
    `ValueError("unsafe archive member")`), same for `.tar`, `.tar.gz`,
    `.tgz`, `.tar.xz`, `.txz` via `tarfile.open(archive).extractall(into, filter="data")`
    (`filter="data"` is the safe extraction filter in Python ≥ 3.12; it
    rejects traversal by itself, so the manual check is only needed for zip).
  - `.dmg`: `mount = into / "dmg"`, `hdiutil attach -nobrowse -readonly -mountpoint <mount> <archive>`,
    copy every `*.ttf`/`*.otf` found under `mount` into `into / "fonts"`,
    then `hdiutil detach <mount>` in a `finally`. A `.pkg`-only image yields
    no fonts.
  - Anything else: `ValueError(f"cannot preview {archive.name}: unsupported download format")`.
  Return `sorted(into.rglob("*.ttf"))`.
- `cask_font_dir(token, into)` — the orchestration: `info = cask_info(token)`;
  if `google_fonts_urls(info)`: download into `into`; elif `info.url.endswith(".git")`:
  raise `ValueError(f"{token} is a git-based cask that is not on Google Fonts; install it to preview")`;
  else `extract_fonts(fetch_cask_archive(token), into)`. Return `into`.

Prints are the CLI's job; this module raises `ValueError` for every user-facing failure.

**Verify**: `uv run ruff check . && uv run ruff format --check .` → clean.

### Step 2: `--preview-cask` in `src/halfbold/cli.py`

```python
    parser.add_argument(
        "--preview-cask",
        metavar="TOKEN",
        help="Download a Homebrew font cask without installing it and preview it",
    )
```

Exclusion rules: `--preview-cask` cannot be combined with `regular`,
`--all`, `--preview` or `--sans/--serif/--mono`; `--png`/`--wait` are
allowed with it (extend the existing "`--png and --wait need --preview`"
check to accept either preview mode).

In `main`, next to the `--preview` branch:

```python
    if args.preview_cask:
        with tempfile.TemporaryDirectory(prefix="halfbold-cask-") as tmp:
            try:
                print(f"fetching {args.preview_cask} …", flush=True)
                fonts_dir = cask_font_dir(args.preview_cask, Path(tmp))
                lines = preview_candidates(fonts_dir, png=args.png, wait=args.wait)
            except ValueError as err:
                print(err)
                return 1
        for line in lines:
            print(line)
        return 0
```

`preview_candidates` raises `ValueError("no Regular + Bold pair or variable TrueType font in …")`
when the archive has nothing convertible — that is the "nothing to preview"
message; prefix it in this branch with the token: catch, then
`print(f"{args.preview_cask}: {err}")`.

Note the temp dir must outlive `preview_candidates` because `--wait` reads
stdin while the fonts are still needed — hence the `with` around both calls.

**Verify**:
- `uv run halfbold --preview-cask font-roboto --png /tmp/roboto.png` → `fetching font-roboto …`, `wrote /tmp/roboto.png`; the PNG shows Roboto half-bold.
- `uv run halfbold --preview-cask font-inter --png /tmp/inter.png` → downloads (or reuses) the zip, `wrote /tmp/inter.png`.
- `uv run halfbold --preview-cask font-sf-mono --png /tmp/x.png` → exit 1, `font-sf-mono: no Regular + Bold pair …`.
- `uv run halfbold --preview-cask font-roboto --all` → argparse error.

### Step 3: Tests in `tests/test_brewcask.py`

No network, no `brew`: test the pure pieces and monkeypatch the rest.

1. `test_parse_cask_info_google` — feed the JSON from "Current state";
   assert `only_path == "ofl/roboto"`, `branch == "main"`, `fonts == ["Roboto[wdth,wght].ttf"]` (plus the italic one if you include it).
2. `test_parse_cask_info_without_url_specs` — JSON with no `url_specs` key → `only_path == ""`, no error.
3. `test_google_fonts_urls_skips_italic_and_encodes_brackets` — fonts
   `["Roboto-Italic[wdth,wght].ttf", "Roboto[wdth,wght].ttf"]` → exactly one
   URL ending in `/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf`.
4. `test_google_fonts_urls_empty_for_other_git` — `url = "https://github.com/x/y.git"` → `[]`.
5. `test_extract_zip_returns_ttfs(tmp_path, font_pair)` — zip the fixture
   pair under `fonts/ttf/`, extract, assert two `.ttf` paths returned.
6. `test_extract_zip_rejects_traversal(tmp_path)` — zip with member
   `../evil.ttf` → `ValueError` matching `unsafe`.
7. `test_extract_tar_xz(tmp_path, variable_font)` — `.tar.xz` with the
   variable font → one path.
8. `test_extract_unknown_suffix(tmp_path)` — `x.exe` → `ValueError` matching `unsupported`.
9. `test_cask_font_dir_uses_google_download(monkeypatch, tmp_path, variable_font)` —
   monkeypatch `cask_info` to return a Google `CaskInfo` and
   `download_google_fonts` to copy the fixture in; assert the returned dir
   contains it and `fetch_cask_archive` was not called (monkeypatch it to
   raise).
10. `test_cli_preview_cask_png(monkeypatch, tmp_path, variable_font, capsys)` —
    monkeypatch `halfbold.cli.cask_font_dir` to copy the fixture into the
    given dir; `main(["--preview-cask", "font-x", "--png", str(tmp_path / "o.png")]) == 0`
    and the PNG exists.
11. `test_cli_preview_cask_rejects_other_modes` — `SystemExit` for
    `["--preview-cask", "font-x", "--all"]`.

Skip a `.dmg` test (needs `hdiutil`); cover it manually in Step 6.

**Verify**: `uv run pytest -q` → all pass, 11 new.

### Step 4: `previewCaskArgs` / `previewCask` in `tui/run.go`

```go
func (r runner) previewCaskArgs(token string) []string {
	return []string{"run", "--project", r.project, "halfbold", "--preview-cask", token, "--wait"}
}

func (r runner) previewCask(token string) tea.Cmd {
	return tea.ExecProcess(exec.Command("uv", r.previewCaskArgs(token)...), func(err error) tea.Msg {
		return previewDoneMsg{err: err}
	})
}
```

Test `TestRunnerPreviewCaskArgs` in `tui/run_test.go` like the others.

**Verify**: `go -C tui test ./... -run PreviewCask` → passes.

### Step 5: `p` on the Homebrew list in `tui/model.go`

Extend the `case "p":` from plan 009:

```go
		case "p":
			switch {
			case (m.screen == screenPick || m.screen == screenCaskPick) && m.list.FilterState() != list.Filtering:
				selected, ok := m.list.SelectedItem().(item)
				if !ok {
					return m, nil
				}
				m.chosen = selected.c
				return m, m.runner.preview(selected.c)
			case m.screen == screenBrewPick && m.brewList.FilterState() != list.Filtering:
				selected, ok := m.brewList.SelectedItem().(caskItem)
				if !ok {
					return m, nil
				}
				m.caskToken = selected.token
				return m, m.runner.previewCask(selected.token)
			}
```

Give `screenBrewPick` a help line in `View`:

```go
	case screenBrewPick:
		return m.brewList.View() + "\n" + helpStyle.Render("enter: install  p: preview  /: filter  esc: back  q: quit")
```

and change its `SetSize` in the `WindowSizeMsg` case from `msg.Height-2` to
`msg.Height-3` so the help line fits (the pick screen already uses `-3`).

The `previewDoneMsg` handler from plan 009 already covers errors: a failed
`--preview-cask` exits 1, its message was printed on the terminal by the
child, and the TUI shows `preview failed: exit status 1` on `screenDone`.
That is acceptable; `esc`/enter returns to the font list (existing
behaviour of `screenDone`). Do not add a new screen.

Tests in `tui/model_test.go`:

- `TestPreviewKeyOnBrewListReturnsCmd` — set `m.screen = screenBrewPick`,
  `m.brewList.SetItems([]list.Item{caskItem{token: "font-roboto"}})`, send
  `p`; assert `caskToken == "font-roboto"`, `screen == screenBrewPick`, cmd non-nil.
- `TestPreviewKeyOnBrewListIgnoredWhileFiltering` — after `/`, `p` leaves `caskToken` empty.

**Verify**: `go -C tui vet ./... && go -C tui test ./...` → `ok`.

### Step 6: Manual check

Ghostty pane inside tmux, `tmux set -g allow-passthrough on`:

```sh
uv run halfbold --preview-cask font-roboto            # Google path, ~1 s
uv run halfbold --preview-cask font-hack-nerd-font    # tar.xz path, download once
uv run halfbold --preview-cask font-sf-mono           # dmg path → "no Regular + Bold pair …"
go run -C tui . -project ..                           # i, filter "roboto", p, enter
```

Confirm `ls ~/Library/Fonts | grep -i roboto` prints nothing afterwards
(nothing installed) and `mount | grep -i sf-mono` is empty (dmg detached).

### Step 7: README

- Picker section, after the plan 009 sentence about `p`: `In the Homebrew list, \`p\` previews the cask before installing it (Google Fonts casks fetch only the needed files; other casks are downloaded to Homebrew's cache with \`brew fetch\`).`
- CLI `--preview` section, add the line `uv run halfbold --preview-cask font-roboto` to the code block with a comment-free trailing sentence: `\`--preview-cask TOKEN\` downloads the cask without installing it.`

**Verify**: `grep -c "preview-cask" README.md` → 2.

## Test plan

See Step 3 (Python) and Steps 4–5 (Go). Pattern files:
`tests/test_scan.py` (monkeypatch + `main([...])`), `tui/run_test.go`,
`tui/model_test.go`.

## Done criteria

- [ ] `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` exit 0; 11 new Python tests present
- [ ] `go -C tui vet ./... && go -C tui test ./...` exit 0; 3 new Go tests present
- [ ] `uv run halfbold --preview-cask font-roboto --png /tmp/r.png` exits 0 and writes the PNG
- [ ] `grep -rn "brew install\|--cask.*install" src/halfbold/brewcask.py` → no matches (never installs)
- [ ] `grep -rn "webbrowser\|\"open\"" src/halfbold/brewcask.py src/halfbold/cli.py tui/run.go` → no matches
- [ ] `git status` shows changes only in in-scope files
- [ ] `plans/README.md` row 010 updated

## STOP conditions

- `brew info --cask --json=v2 font-roboto` no longer has `url_specs.only_path`
  or the `url` differs from `https://github.com/google/fonts.git` — Homebrew
  changed the cask format; report before adapting.
- `brew --cache --cask font-inter` prints a directory or something other
  than the archive path.
- `raw.githubusercontent.com` returns non-200 for a Google font in Step 2.
- `hdiutil detach` fails in the `.dmg` manual check (leaves a mount) — report
  the mount point rather than retrying with `-force`.
- The `case "p":` block in `model.go` does not match plan 009's shape.
- Anything needs a change in `preview.py` or `scan.py` — those belong to 008.

## Maintenance notes

- Google Fonts casks are the only git casks handled; if Homebrew moves
  those casks to release archives, the `google_fonts_urls` branch becomes
  dead code and `fetch_cask_archive` covers them.
- `brew fetch` leaves the archive in `~/Library/Caches/Homebrew/downloads`;
  a later `brew install --cask` reuses it, so previewing then installing
  downloads once. `brew cleanup` removes it.
- Nerd Font archives are large (10–100 MB); the `fetching …` line is the
  only progress indicator because `brew fetch` output is captured. If that
  feels too silent, stream `brew fetch` stderr instead of capturing it.
- Reviewer focus: the zip member check and `tarfile` `filter="data"` are
  the only guards against archive path traversal; keep them.
