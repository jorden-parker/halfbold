# Plan 008: `halfbold --preview FONT` draws a half-bold sample inside the terminal (kitty graphics), never a browser

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 56a59d9..HEAD -- src/halfbold/ tests/ pyproject.toml README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (new module + one CLI mode; no existing behaviour changes except a small refactor of `find_candidates` that keeps its signature)
- **Depends on**: none (plans/007 is independent; run it first anyway, it is P1)
- **Category**: direction
- **Planned at**: commit `56a59d9`, 2026-09-16

## Why this matters

The picker (`tui/`) and the CLI can convert a font, but the only way to see
what its half-bold twin looks like is to build it, install it and open some
app. The maintainer wants to preview a font **inside the terminal** — they
explicitly do not want a browser page (plans 005/006 proposed one and were
rejected for that reason).

The maintainer's terminal is Ghostty 1.3.1, which implements the kitty
graphics protocol, running tmux 3.7b. tmux forwards graphics escape
sequences to Ghostty when `allow-passthrough` is on. So the preview is a PNG
rendered by Python (Pillow) and written to the terminal as a kitty graphics
image. No browser, no font installation, no conversion.

The PNG shows the sample paragraph twice: once **simulated half-bold** (the
first `ceil(n/2)` letters of every word drawn with the Bold face, the rest
with the Regular face — exactly the rule `build.py` compiles into `calt`) and
once plain, for comparison. A variable font is drawn at weight 400 and 700
through Pillow's variation API. Verified on 2026-09-16 with
`~/Library/Fonts/InterVariable.ttf`: Pillow 12.3.0 renders both weights
correctly with no extra native libraries. (Pillow's wheels do **not** ship
libraqm, so OpenType features like `calt` cannot be applied — that is why the
half-bold is simulated from the two faces rather than rendered from the real
Half font. The result is visually the same: same bold glyphs, same
`ceil(n/2)` rule; only kerning across the bold/regular seam is lost.)

This plan delivers the Python engine and the `halfbold --preview` CLI mode.
Plan 009 binds it to `p` in the TUI; plan 010 adds Homebrew casks.

## Current state

### Repo facts

- Python 3.14 project managed by `uv`; package in `src/halfbold/`, entry
  point `halfbold = "halfbold.cli:main"` (`pyproject.toml`). Only runtime
  dependency today: `fonttools>=4.65.0`. Dev deps: pytest, ruff, uharfbuzz.
- Conventions (`AGENTS.md`): **no code comments** (ruff `ERA` rule catches
  commented-out code; keep every other comment out too — name things well
  instead); Conventional Commits; after changes run
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` and
  fix everything reported. ruff config: line length 88, rules
  `E F I UP B SIM ERA`, `plans/` excluded.
- No `CONTEXT.md`, no `docs/adr/`. Nothing to honor there.
- The Go TUI (`tui/`) is **out of scope** for this plan.

### `src/halfbold/cli.py` (143 lines) — argparse CLI

Modes today: positional `regular [bold]`, `--all`, `--sans/--serif/--mono`.
Relevant excerpt (lines 92–107, the mutual-exclusion checks):

```python
    args = parser.parse_args(argv)
    args.web = {kind: getattr(args, kind) for kind in KINDS if getattr(args, kind)}
    if args.web and (args.all or args.regular is not None):
        parser.error(
            "--sans/--serif/--mono cannot be combined with a font file or --all"
        )
    if not args.web and not args.all and args.regular is None:
        parser.error(
            "give a font file, --all to scan the fonts folder, or --sans/--serif/--mono"
        )
    return args
```

`main()` (lines 110–143) dispatches: `if args.web: … return`, `if args.all:
… return`, then the single-font build. Each mode `print`s its result lines
and returns 0/1.

### `src/halfbold/scan.py` (154 lines)

- `Candidate(family, regular, bold, kind)` dataclass (line 19).
- `read_font_info(path) -> FontInfo | None` (line 65): returns `None` for
  fonts without `glyf` (CFF/OTF) or unparsable files.
- `find_candidates(fonts_dir) -> list[Candidate]` (lines 101–131): scans
  `sorted(fonts_dir.glob("*.ttf"))` (non-recursive), skips Half outputs and
  italics, pairs Regular + Bold per family, and takes variable fonts with a
  `wght` axis. Lines 101–108 today:

```python
def find_candidates(fonts_dir: Path) -> list[Candidate]:
    infos = [
        info
        for path in sorted(fonts_dir.glob("*.ttf"))
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_italic(info)
    ]
```

The rest of the function (lines 109–131) only uses `infos`.

### `src/halfbold/build.py` (147 lines)

- `bold_prefix_length(word_length: int) -> int` (line 109) is the
  `ceil(n/2)` rule. **Reuse it** so the preview and the real font agree:

```python
def bold_prefix_length(word_length: int) -> int:
    return math.ceil(word_length / 2)
```

- `REGULAR_WEIGHT = 400`, `BOLD_WEIGHT = 700` (lines 13–14).

### Tests

- `tests/conftest.py` builds tiny box-glyph fonts with `FontBuilder`:
  `make_font(path, family, style, stem)` (static, letters a–z + space) and
  `make_variable_font(path, family)` (one `wght` axis 400–700). Fixtures
  `font_pair` (Regular + Bold) and `variable_font`. These render fine with
  Pillow (plain rectangles).
- `tests/test_variable.py` shows the pattern: call the library function, then
  assert on the result; CLI tests call `main([...])` and read `capsys`.

### Terminal facts (maintainer's machine, 2026-09-16)

- Ghostty 1.3.1 (`~/.config/ghostty/config`, `command = tmux new-session -A -s main`), tmux 3.7b, `TERM=tmux-256color`, `TERM_PROGRAM=tmux`, `TMUX` set.
- `tmux show -g allow-passthrough` → `off`. **Kitty graphics cannot reach
  Ghostty until this is `on`.** Their tmux config is a symlink target in
  another repo (`~/src/workspace/.config/tmux/tmux.conf`); do not edit it —
  the README paragraph in Step 7 tells the user what to add.
- Ghostty exports `GHOSTTY_RESOURCES_DIR` into the environment, and tmux
  panes inherit it; kitty exports `KITTY_WINDOW_ID`. Use those to detect a
  kitty-graphics terminal.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Sync deps | `uv sync` | exit 0 |
| Add Pillow | `uv add pillow` | `pyproject.toml` gains `"pillow>=12"` (or the resolved version) under `dependencies`; `uv.lock` updated |
| Tests | `uv run pytest` | all pass |
| One test file | `uv run pytest tests/test_preview.py -q` | all pass |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `N files already formatted` |
| Manual | `uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf` | image appears in the terminal (see Step 6) |

## Scope

**In scope** (the only files you may modify):
- `src/halfbold/preview.py` (create)
- `src/halfbold/cli.py` (add `--preview`, `--png`, `--wait`)
- `src/halfbold/scan.py` (factor `candidates_from_paths` out of `find_candidates`)
- `tests/test_preview.py` (create)
- `pyproject.toml`, `uv.lock` (Pillow dependency, via `uv add` only)
- `README.md` (one paragraph)

**Out of scope** (do NOT touch):
- `tui/` — plan 009 wires the TUI key.
- `src/halfbold/build.py`, `src/halfbold/web.py`, `chrome-extension/`,
  `scripts/`.
- Homebrew anything — plan 010.
- The user's tmux/ghostty config files.

## Git workflow

- Branch: `advisor/008-terminal-font-preview`
- Conventional Commits, e.g. `feat: preview a font's half-bold look in the terminal`
  (existing examples: `feat: classify fonts as sans, serif or mono`,
  `chore: add improve plans 001-004 and their index`).
- Do not push or open a PR unless told to.

## Steps

### Step 1: Add Pillow

Run `uv add pillow`. It must land under `[project].dependencies` (not the
dev group) because `--preview` is a runtime feature.

**Verify**: `uv run python -c "import PIL, PIL.features as f; print(PIL.__version__, f.check('freetype2'))"` → prints a version `>= 12` and `True`.

### Step 2: Factor `candidates_from_paths` out of `scan.find_candidates`

In `src/halfbold/scan.py` replace lines 101–108 with:

```python
def find_candidates(fonts_dir: Path) -> list[Candidate]:
    return candidates_from_paths(sorted(fonts_dir.glob("*.ttf")))


def candidates_from_paths(paths: list[Path]) -> list[Candidate]:
    infos = [
        info
        for path in paths
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_italic(info)
    ]
```

and keep the rest of the old body (from `candidates: list[Candidate] = []`
to `return candidates`) as the body of `candidates_from_paths`.

**Verify**: `uv run pytest tests/test_scan.py -q` → all pass (unchanged behaviour).

### Step 3: Create `src/halfbold/preview.py`

Public surface (names are load-bearing; plans 009/010 refer to them):

```python
SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog. Reading gets faster when "
    "the first half of every word is bold, because your eyes only need the "
    "start of a word to recognise it."
)
FONT_SIZE = 40
CANVAS_WIDTH = 1400
MARGIN = 40
LINE_HEIGHT = 56


def load_faces(regular: Path, bold: Path | None) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]: ...
def wrap_words(words: list[str], face, max_width: int) -> list[list[str]]: ...
def render_preview(family: str, regular: Path, bold: Path | None) -> Image.Image: ...
def kitty_chunks(png: bytes, columns: int, tmux: bool) -> list[bytes]: ...
def kitty_delete_all(tmux: bool) -> bytes: ...
def supports_kitty_graphics(env: Mapping[str, str]) -> bool: ...
def show_image(image: Image.Image, out: BinaryIO, env: Mapping[str, str], columns: int) -> None: ...
def preview_candidates(paths_or_dir: Path, *, png: Path | None, wait: bool) -> list[str]: ...
```

Implementation notes, in order:

1. **`load_faces`** — `ImageFont.truetype(str(regular), FONT_SIZE)` for
   both. When `bold is None` (variable font) open the regular path twice and
   call `set_variation_by_axes` on each: build the axis list from
   `face.get_variation_axes()`, keeping every axis at its `default` and
   setting the axis whose `name` is `b"Weight"` (or whose index matches the
   `wght` tag — Pillow exposes names, not tags; `b"Weight"` is what Inter,
   Roboto and Source Serif 4 report) to `REGULAR_WEIGHT` / `BOLD_WEIGHT`
   from `halfbold.build`. If no axis is named `Weight`, raise
   `ValueError("variable font has no weight axis")`. A static font passed
   without `bold` (no `fvar`): `get_variation_axes()` raises `OSError` —
   catch it and raise `ValueError(f"{regular} is not a variable font; pass a Bold file as well")`
   to match `build.load_font_pair`'s message.
2. **`wrap_words`** — greedy word wrap by `face.getlength(" ".join(line))`
   against `max_width = CANVAS_WIDTH - 2 * MARGIN`, measured with the
   **bold** face (widest) so half-bold lines never overflow.
3. **`render_preview`** — image `RGB`, white background, black text. Rows:
   - title line in the regular face: `f"{family} — half bold preview"`,
   - blank half line,
   - the wrapped `SAMPLE_TEXT` drawn half-bold: for each word `w`,
     `n = bold_prefix_length(len(w))` (from `halfbold.build`), draw `w[:n]`
     with the bold face, advance by `bold.getlength(w[:n])`, draw `w[n:]`
     with the regular face, advance by `regular.getlength(w[n:]) + regular.getlength(" ")`.
     Punctuation counts as part of the word here, same as the `calt` rules
     treat only letters — good enough for a preview; do not special-case.
   - blank half line,
   - the same wrapped lines drawn plain with the regular face.
   Height = `MARGIN * 2 + LINE_HEIGHT * (2 + 2 * len(lines)) + LINE_HEIGHT`
   (round up; the exact constant is not load-bearing, but every line must
   fit). Return the `Image`.
4. **`kitty_chunks`** — encode the PNG (`image.save(buf, format="PNG")`
   happens in `show_image`) as base64, split into 4096-byte pieces, and
   emit kitty graphics commands: first chunk control data
   `f=100,a=T,q=2,c={columns},m=1`, middle chunks `m=1`, last chunk `m=0`
   (a single chunk uses `f=100,a=T,q=2,c={columns},m=0`). Each command is
   `b"\x1b_G" + control + b";" + payload + b"\x1b\\"`. `q=2` suppresses the
   terminal's reply (a reply would otherwise land on stdin and confuse the
   `--wait` prompt and the TUI). `c=` scales the image to that many cell
   columns; kitty keeps the aspect ratio when only `c` is given. When
   `tmux` is true wrap **each** command as
   `b"\x1bPtmux;" + command.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"`.
5. **`kitty_delete_all`** — `b"\x1b_Ga=d,d=A,q=2\x1b\\"`, tmux-wrapped the
   same way. Called after `--wait` returns so no image is left on the
   main screen once the TUI (plan 009) restores its alt screen.
6. **`supports_kitty_graphics(env)`** — `True` when
   `"GHOSTTY_RESOURCES_DIR" in env or "KITTY_WINDOW_ID" in env or "kitty" in env.get("TERM", "")`.
7. **`show_image`** — save the PNG to a `BytesIO`, `columns = min(columns, 120)`,
   write every chunk from `kitty_chunks(png, columns, tmux="TMUX" in env)`
   to `out`, then write enough newlines to move past the image:
   `rows = ceil(columns * image.height / image.width / 2)` (assumes the
   usual 1:2 cell aspect), then `flush`.
8. **`preview_candidates(target, *, png, wait)`** — `target` is a font file
   or a directory. Directory → `candidates_from_paths(sorted(target.rglob("*.ttf")))`
   (recursive so archive layouts like `fonts/ttf/` work in plan 010); file →
   handled by the CLI (see Step 4), this function only takes the candidate
   list path. Returns report lines (strings) the CLI prints. For each
   candidate (at most 3; say `"… and N more"` after that):
   - `image = render_preview(candidate.family, candidate.regular, candidate.bold)`,
   - if `png` is set: save there (when several candidates, suffix
     `-2`, `-3` before the extension) and report `f"wrote {path}"`,
   - elif `supports_kitty_graphics(os.environ)`: `show_image(image, sys.stdout.buffer, os.environ, shutil.get_terminal_size().columns)`,
   - else: save to `Path(tempfile.gettempdir()) / f"halfbold-preview-{stem}.png"`
     and report `f"this terminal has no kitty graphics support; wrote {path}"`.
     **Never open a browser or any app.**
   After all images, if `wait`: print `"enter: back"` and read one line from
   `sys.stdin`, then write `kitty_delete_all(...)` to stdout and flush.
   Empty candidate list → raise `ValueError(f"no Regular + Bold pair or variable TrueType font in {target}")`.

Keep functions small and pure where possible (`wrap_words`, `kitty_chunks`,
`supports_kitty_graphics` take their inputs explicitly) so the tests in Step
5 need no terminal.

**Verify**: `uv run ruff check . && uv run ruff format --check .` → clean.

### Step 4: Add `--preview` to `src/halfbold/cli.py`

Add three arguments:

```python
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Draw a half-bold sample of REGULAR [BOLD] (or every font in a folder) in the terminal",
    )
    parser.add_argument(
        "--png", type=Path, help="With --preview, write the sample image here instead"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="With --preview, keep the image until enter is pressed (used by the TUI)",
    )
```

Validation, added to `parse_args` next to the existing checks:
`--preview` requires `regular` and rejects `--all` and `--sans/--serif/--mono`
(`parser.error("--preview takes a font file or folder and no other mode")`).
`--png`/`--wait` without `--preview` → `parser.error("--png and --wait need --preview")`.

In `main`, before the `--all` branch:

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
```

Add `preview_files(regular, bold, *, png, wait)` to `preview.py`: it builds
the family name with `read_font_info(regular)` (family, with the word
`Variable` removed like `find_candidates` does) and delegates to the same
per-candidate loop as `preview_candidates` — factor that loop into
`preview_images(candidates, *, png, wait)` used by both. If
`read_font_info` returns `None` raise `ValueError(f"{regular} is not a TrueType font")`.

Keep the mutual-exclusion messages in the same style as the existing ones.

**Verify**:
- `uv run halfbold --preview` → exit 2 with an argparse error mentioning `--preview`.
- `uv run halfbold --preview tests/../pyproject.toml` → exit 1, `… is not a TrueType font`.
- `uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf --png /tmp/inter.png` → `wrote /tmp/inter.png`; open the PNG with the Read tool (or `open /tmp/inter.png` if you are a human): title line, a paragraph with the first half of every word bold, the same paragraph plain.

### Step 5: Tests in `tests/test_preview.py`

Model after `tests/test_variable.py` (library call + assertion; CLI via
`main([...])` + `capsys`). Cases:

1. `test_render_pair_bolds_word_starts(font_pair)` — render with the
   Regular + Bold box fonts (stems 100 vs 200 units, i.e. the bold boxes are
   twice as wide). Assert the image width is `CANVAS_WIDTH`, height > 0, and
   the half-bold paragraph region contains more black pixels than the plain
   region below it (crop the two bands using the row layout from Step 3 and
   compare `sum(1 for p in band.getdata() if p != (255, 255, 255))`).
2. `test_render_variable_uses_two_weights(variable_font)` — same assertion
   with `bold=None`; also assert `load_faces(variable_font, None)` returns two
   faces whose `getlength("a")` differ (700 draws wider boxes than 400 in the
   fixture).
3. `test_static_font_without_bold_is_rejected(font_pair)` — `load_faces(regular, None)` raises `ValueError` matching `not a variable font`.
4. `test_wrap_words_never_exceeds_width` — with the bold box face, every
   wrapped line's `getlength` ≤ `CANVAS_WIDTH - 2 * MARGIN`, and the words
   round-trip (`sum(lines, []) == words`).
5. `test_kitty_chunks_split_and_flags` — feed 10 000 bytes of fake PNG;
   assert 4 commands (base64 of 10 000 bytes is 13 336 chars → 4 chunks),
   the first starts with `b"\x1b_Gf=100,a=T,q=2,c=80,m=1;"`, the last has
   `m=0`, none of the middle ones contain `f=100`.
6. `test_kitty_chunks_tmux_wrapping` — with `tmux=True` every command starts
   with `b"\x1bPtmux;\x1b\x1b_G"` and ends with `b"\x1b\x1b\\\x1b\\"`.
7. `test_supports_kitty_graphics` — `{"GHOSTTY_RESOURCES_DIR": "/x"}` True,
   `{"KITTY_WINDOW_ID": "1"}` True, `{"TERM": "xterm-kitty"}` True,
   `{"TERM": "tmux-256color"}` False.
8. `test_cli_preview_png_writes_file(variable_font, tmp_path, capsys)` —
   `main(["--preview", str(variable_font), "--png", str(tmp_path / "p.png")]) == 0`,
   file exists, stdout contains `wrote`.
9. `test_cli_preview_directory_previews_each_candidate(tmp_path, capsys)` —
   build two families with `make_font`/`make_variable_font` in a
   subdirectory (recursion), run `--preview tmp_path --png out.png`, assert
   `out.png` and `out-2.png` exist.
10. `test_cli_preview_rejects_other_modes(capsys)` —
    `pytest.raises(SystemExit)` for `["--preview", "--all"]` and for
    `["--png", "x.png"]` alone.

**Verify**: `uv run pytest -q` → all pass, 10 new.

### Step 6: Manual check in Ghostty + tmux

This is the only step that needs the maintainer's terminal. Run these in a
Ghostty pane inside tmux:

```sh
tmux set -g allow-passthrough on
uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf
```

Expected: the white preview image appears inline, scaled to at most 120
columns; the shell prompt returns below it. Then:

```sh
uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf --wait
```

Expected: image, then `enter: back`; after pressing enter the image is
removed (`kitty_delete_all`).

If the image does not appear but a burst of base64 text does, passthrough is
off or the wrapping is wrong — check `tmux show -g allow-passthrough` first.
If nothing appears at all and no text either, the terminal swallowed the
sequence: confirm `GHOSTTY_RESOURCES_DIR` is set in that pane (`env | grep GHOSTTY`).

(`tmux set -g` only affects the running server; the README paragraph tells
the maintainer how to make it permanent.)

### Step 7: README

In `README.md`, after the paragraph beginning `Point the Chrome extension at
a different Half font.` (and before `Or let launchd do it.`), add:

> Preview how a font will look half-bold without converting it. The sample
> is drawn as an image straight into the terminal (kitty graphics protocol —
> Ghostty, kitty, WezTerm); anywhere else it is written to a PNG whose path
> is printed:
>
> ```sh
> uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf
> uv run halfbold --preview ~/Library/Fonts            # every convertible font, up to three
> uv run halfbold --preview Inter-Regular.ttf Inter-Bold.ttf --png inter.png
> ```
>
> Inside tmux add `set -g allow-passthrough on` to `tmux.conf` (tmux ≥ 3.3)
> so the image reaches the terminal.

**Verify**: `grep -n "allow-passthrough" README.md` → one match.

## Test plan

See Step 5. Pattern file: `tests/test_variable.py`. Fixtures from
`tests/conftest.py` (`font_pair`, `variable_font`, `make_font`,
`make_variable_font`).

## Done criteria

- [ ] `uv run pytest` exits 0 with the 10 tests from Step 5 present
- [ ] `uv run ruff check .` and `uv run ruff format --check .` exit 0
- [ ] `grep -n '"pillow' pyproject.toml` shows Pillow under `dependencies`
- [ ] `uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf --png /tmp/p.png` exits 0 and the PNG shows a half-bold paragraph above a plain one
- [ ] `grep -rn "webbrowser\|open(" src/halfbold/preview.py` shows no call that launches a browser or `open`
- [ ] `git status` shows changes only in the in-scope files
- [ ] `plans/README.md` row 008 updated

## STOP conditions

- `uv add pillow` fails to resolve on Python 3.14, or
  `PIL.features.check("freetype2")` is `False`.
- `set_variation_by_axes` raises on `InterVariable.ttf` (FreeType built
  without variation support) — report; do not fall back to fontTools
  instancing without asking.
- `find_candidates` in `scan.py` no longer matches the excerpt above.
- Step 6 shows no image even with `allow-passthrough on` and
  `GHOSTTY_RESOURCES_DIR` set — report the exact bytes emitted (`--png` still
  works, so land everything else and mark the row BLOCKED with the reason).
- Any step needs a change under `tui/` or `build.py`.

## Maintenance notes

- `bold_prefix_length` is the single source of the half-word rule; if
  `build.py` ever changes it, the preview follows automatically.
- The kitty encoder assumes 1:2 cell aspect for the newline padding only;
  the image itself keeps its aspect because only `c=` is sent. If previews
  overlap the prompt, that estimate is the place to look (TIOCGWINSZ pixel
  sizes could replace it).
- Plans 009 and 010 call `preview_images`, `preview_candidates`,
  `preview_files` and the `--preview/--wait` flags. Renaming them breaks
  those plans.
- Deferred: rendering the *real* Half font with `calt` applied. Needs
  HarfBuzz shaping (`uharfbuzz` is already a dev dep) plus rasterising glyph
  outlines by glyph id, which Pillow cannot do; not worth it while the
  simulated result is visually identical.
