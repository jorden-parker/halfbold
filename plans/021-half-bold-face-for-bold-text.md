# Plan 021: Every Half font ships a plain Bold face, so bold text is drawn bold instead of half-bold plus fake bold

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 00fe501..HEAD -- src/halfbold/build.py src/halfbold/scan.py src/halfbold/api.py src/halfbold/cli.py tests/test_build.py tests/test_scan.py tests/test_api.py README.md AGENTS.md CONTEXT.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `00fe501`, 2026-10-21

## Why this matters

halfbold installs exactly one face per Half font family: `<Family> Half`,
style Regular, weight 400, whose `calt` feature draws the first half of each
word bold. Text that is already bold (`<b>`, `<strong>`, headings,
`font-weight: 700` in Chrome through the extension; bold syntax tokens in VS
Code; bold cells in Ghostty) asks the family for a Bold face. There is none, so
the app synthesizes a fake bold: it smears the Regular outlines thicker. The
half-bold letters (already drawn at the Bold weight) get smeared too, and the
result is so heavy it is hard to read.

The fix is to install a second face in the same family, `<Family> Half Bold`:
the source family's own bold outlines, renamed into the Half family, with **no**
half-bold `calt` rules. Every text engine (CoreText, Chrome, VS Code's
Chromium, Ghostty) then picks that real Bold face for bold text, so bold text
renders as ordinary bold, with no half-bold effect and no synthesized
emboldening. Nothing in the Chrome extension, VS Code settings or terminal
config has to change, because they all already name the family `<Family> Half`.

## Current state

Files involved:

- `src/halfbold/build.py` — builds the Half font. `build_halfbold_font`
  (lines 42–71) loads the plain and bold sources, copies bold letters in as
  `<glyph>.half`, adds `calt`, renames, saves. `rename_font` (lines 238–266)
  and `reset_weight` (lines 269–273) force the output to be the Regular face.
- `src/halfbold/scan.py` — `Candidate.output` (line 71) is the install path;
  `Candidate.is_stale` (line 87) decides whether `halfbold sync` / `build_all`
  rebuilds; `build_all` (around line 340–368) builds every stale Candidate into
  `~/Library/Fonts`. `is_half_output` (line 174) recognises installed Half
  fonts by a family name ending in ` Half`; `find_candidates` skips them and
  `find_installed_half_fonts` (line 185) lists them (Reset deletes those).
- `src/halfbold/api.py` — `build` (line 200) is what the desktop app's
  Convert / Use in browser / Use in Visual Studio Code buttons call, with
  `-o <candidate.output>`. `build_into_cache` (line 131) builds the
  **preview** into `~/Library/Caches/halfbold`; the preview is never installed
  and does **not** need a Bold face.
- `src/halfbold/cli.py` — `main` (line 255–258) is the two-file command
  `halfbold Regular.ttf Bold.ttf [-o out.ttf]`.

Excerpt, `src/halfbold/build.py:42-71`:

```python
def build_halfbold_font(
    regular_path: Path,
    bold_path: Path | None,
    output_path: Path,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or Settings()
    regular, bold = load_font_pair(
        regular_path, bold_path, settings.regular_weight, settings.bold_weight
    )

    letters = word_letter_glyphs(regular, bold)
    ...
    add_calt_feature(regular, fea)
    drop_apple_shaping(regular)
    rename_font(regular)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    regular.recalcBBoxes = False
    regular.save(output_path)
    return letters.names
```

Excerpt, `src/halfbold/build.py:90-110` (`load_font_pair`): when `bold_path`
is `None` the regular path is a variable font and both faces are instanced
from it with `instance_at_weight(open_font(regular_path), weight)`; otherwise
both files are opened with `open_font` and checked with
`require_truetype_outlines`.

Excerpt, `src/halfbold/build.py:238-273`:

```python
def rename_font(font: TTFont) -> None:
    name_table = font["name"]
    family = name_table.getBestFamilyName()
    base_family = " ".join(part for part in family.split() if part != "Variable")
    new_family = f"{base_family} {STYLE_SUFFIX}"
    postscript = f"{new_family.replace(' ', '')}-{PLAIN_STYLE}"
    names = {
        1: new_family,
        16: new_family,
        2: PLAIN_STYLE,
        17: PLAIN_STYLE,
        4: f"{new_family} {PLAIN_STYLE}",
        6: postscript,
        3: f"{postscript};{STYLE_SUFFIX}",
    }
    ...
    reset_weight(font)


def reset_weight(font: TTFont) -> None:
    os2 = font["OS/2"]
    os2.usWeightClass = PLAIN_WEIGHT
    os2.fsSelection = (os2.fsSelection & ~(FS_BOLD | FS_ITALIC)) | FS_REGULAR
    font["head"].macStyle &= ~(MAC_BOLD | MAC_ITALIC)
```

Constants at `src/halfbold/build.py:20-28`: `BOLD_SUFFIX = ".half"`,
`STYLE_SUFFIX = "Half"`, `PLAIN_STYLE = "Regular"`, `PLAIN_WEIGHT = 400`,
`FS_ITALIC = 0x01`, `FS_BOLD = 0x20`, `FS_REGULAR = 0x40`, `MAC_BOLD = 0x01`,
`MAC_ITALIC = 0x02`.

Excerpt, `src/halfbold/scan.py:70-91`:

```python
    @property
    def output(self) -> Path:
        stem = self.family.replace(" ", "")
        return (self.output_dir or self.regular.parent) / f"{stem}-{STYLE_SUFFIX}.ttf"
    ...
    def is_stale(self) -> bool:
        if not self.output.exists():
            return True
        built = self.output.stat().st_mtime
        return any(p.stat().st_mtime > built for p in self.sources)
```

Excerpt, `src/halfbold/api.py:200-208`:

```python
def build(args: argparse.Namespace) -> dict:
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    settings = load_settings()
    letters = build_halfbold_font(args.regular, args.bold, output, settings)
    return {
        "output": str(output),
        "letters": len(letters),
        "settings": settings.as_dict(),
    }
```

`src/halfbold/cli.py:255-258` does the same and prints
`wrote {output} ({len(letters)} letter glyphs bolded)`.

Domain vocabulary (`CONTEXT.md`), use these words in names:

- **Half font**: "The converted output of a Candidate, installed next to the
  original under the family name plus ` Half`, always named Regular at weight
  400 whichever Faces built it." (this definition changes in Step 6)
- **Face**: one font file of a family at one weight and style.
- **Plain weight**, **Bold weight**: "The weights the plain and the bold letters
  are drawn at. A variable font is instanced at them; a static family snaps
  each to its nearest Face."

Call the new file the **Half Bold face**.

Conventions (from `AGENTS.md` and the maintainer's global preferences):

- No comments of any kind in code, including lint suppressions. Name things
  instead. Ruff's `ERA` rule catches commented-out code.
- Small functions doing one thing; match the style of `build.py` (top-level
  functions, module constants in CAPS, `Path` everywhere).
- TDD: write the failing test first, then the smallest change.
- Tests build tiny synthetic fonts with `make_font` in `tests/conftest.py`;
  fixtures `font_pair` (`Test-Regular.ttf` stem 100, `Test-Bold.ttf` stem 200),
  `multi_weight_family`, and `fill_fonts_dir` in `tests/test_scan.py` (a static
  `Pair` family plus a variable `Var` font). Exemplar test:
  `tests/test_build.py::test_half_font_is_regular_whichever_face_built_it`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `uv run pytest -q` | all pass (173 passed at `00fe501`, more after this plan) |
| One test file | `uv run pytest -q tests/test_build.py` | all pass |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | exit 0 |

## Scope

**In scope** (the only files you should modify):

- `src/halfbold/build.py`
- `src/halfbold/scan.py`
- `src/halfbold/api.py`
- `src/halfbold/cli.py`
- `tests/test_build.py`, `tests/test_scan.py`, `tests/test_api.py`
- `README.md`, `AGENTS.md`, `CONTEXT.md` (doc lines only, Step 6)

**Out of scope** (do NOT touch):

- `chrome-extension/` — the stylesheet already names the family; Chrome picks
  the Bold face on its own. Plan 017 rewrites this area separately.
- `src/halfbold/vscode.py`, `src/halfbold/web.py` — they set family names only.
- `build_into_cache` / `preview_half` in `api.py` — the preview is drawn by the
  app in Regular only and is never installed. Do not write a Bold face there.
- The half-bold rules (`build_feature_code`, `start_rules`, `count_rules`) —
  which letters get bolded is unchanged by this plan.
- Italic faces — still ignored, as today.
- `app/` (TypeScript / Rust) — no app change is needed: the app calls
  `halfbold-api build`, which gains the Bold face automatically.

## Git workflow

- Branch: `advisor/021-half-bold-face`
- Conventional Commits, enforced by `.githooks/commit-msg`. Examples from
  `git log`: `feat: add a reset halfbold-api subcommand`,
  `refactor: map installed Half fonts to their paths`.
- Do NOT push or open a PR.

## Steps

### Step 1: `rename_font` can name a face Regular or Bold

Write the failing test first, in `tests/test_build.py`, calling `rename_font`
directly (import `rename_font` and the new `BOLD_STYLE` from `halfbold.build`):

```python
def test_rename_as_bold_makes_the_half_bold_face(font_pair: tuple[Path, Path]):
    font = TTFont(font_pair[1])
    rename_font(font, BOLD_STYLE)
    name = font["name"]
    assert name.getDebugName(1) == "Test Half"
    assert name.getDebugName(2) == "Bold"
    assert name.getDebugName(4) == "Test Half Bold"
    assert name.getDebugName(6) == "TestHalf-Bold"
    assert name.getDebugName(16) == "Test Half"
    assert name.getDebugName(17) == "Bold"
    assert font["OS/2"].usWeightClass == 700
    assert font["OS/2"].fsSelection & 0x20
    assert not font["OS/2"].fsSelection & 0x40
    assert font["head"].macStyle & 0x01
```

Then change `build.py`:

- Add constants `BOLD_STYLE = "Bold"` and `BOLD_WEIGHT_CLASS = 700` next to
  `PLAIN_STYLE` / `PLAIN_WEIGHT`.
- Give `rename_font` a `style: str = PLAIN_STYLE` parameter and use it
  wherever `PLAIN_STYLE` is used inside the function today (names 2, 17, 4, 6).
- Replace `reset_weight(font)` with a function that sets Regular or Bold flags
  according to `style`. For Bold: `usWeightClass = 700`;
  `fsSelection = (fsSelection & ~(FS_REGULAR | FS_ITALIC)) | FS_BOLD`;
  `macStyle = (macStyle & ~MAC_ITALIC) | MAC_BOLD`. Regular keeps today's
  behaviour exactly. A small dict or two tiny functions keyed by style is fine;
  no comments.

Verify: `uv run pytest -q tests/test_build.py` → all pass, including the
existing `test_half_font_is_regular_whichever_face_built_it` and
`test_rename_gives_half_font_its_own_postscript_and_full_names`.

### Step 2: `build_bold_face` writes the Half Bold face

Failing tests first, in `tests/test_build.py`:

```python
def test_bold_face_is_the_bold_source_without_half_glyphs(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-HalfBold.ttf"
    build_bold_face(regular, bold, out)

    font = TTFont(out)
    assert font["name"].getBestFamilyName() == "Test Half"
    assert font["name"].getDebugName(2) == "Bold"
    assert not any(g.endswith(BOLD_SUFFIX) for g in font.getGlyphOrder())
    assert font["hmtx"]["a"][0] == 300
```

(`hmtx` width 300 is the Bold fixture's advance: `make_font` sets advance =
stem + 100 and the bold stem is 200.) Add a second test using the variable
fixture from `tests/conftest.py` (`make_variable_font`; read its signature in
`conftest.py`) that calls `build_bold_face(variable_path, None, out,
Settings(bold_weight=700))` and asserts the output has no `fvar` table and
names style `Bold`. Also assert the bold face keeps the source's own
ligatures: with `ligature_font_pair`, the output's `GSUB` still has a `liga`
feature.

Then implement in `build.py`:

- `load_bold_source(regular_path, bold_path, bold_weight) -> TTFont`: if
  `bold_path is None`, check the variable font as `load_font_pair` does today
  (`require_truetype_outlines`, `fvar` present) and return
  `instance_at_weight(open_font(regular_path), bold_weight)`; otherwise
  `open_font(bold_path)` + `require_truetype_outlines`. Refactor
  `load_font_pair` to call it for the bold half so the logic lives once.
- `build_bold_face(regular_path, bold_path, output_path, settings=None) -> None`:
  load the bold source, `rename_font(font, BOLD_STYLE)`, `mkdir` the parent,
  set `recalcBBoxes = False` (as `build_halfbold_font` does), save. Do not add
  `calt`, do not drop Apple shaping tables, do not copy glyphs.
- `bold_face_path(output_path: Path) -> Path`: returns
  `output_path.with_name(f"{output_path.stem}Bold{output_path.suffix}")`, so
  `Inter-Half.ttf` → `Inter-HalfBold.ttf`. This name deliberately does not
  match the `*-Half.ttf` glob some tests use.

Verify: `uv run pytest -q tests/test_build.py` → all pass.

### Step 3: Installing a Half font also installs its Half Bold face

Failing tests first:

- `tests/test_scan.py`: extend or add next to
  `test_build_all_skips_up_to_date_and_ignores_own_output`: after
  `build_all(fonts)`, `(fonts / "Pair-HalfBold.ttf").exists()` and
  `(fonts / "Var-HalfBold.ttf").exists()`; the second `build_all` still reports
  everything `up to date`; `{c.family for c in find_candidates(fonts)}` is still
  `{"Pair", "Var"}` (the Bold face must not become a Candidate).
- `tests/test_scan.py`: a Candidate whose `-Half.ttf` exists but whose
  `-HalfBold.ttf` is missing is stale: build once, delete
  `Pair-HalfBold.ttf`, run `build_all`, assert a `built` line mentions
  `Pair-Half` and the Bold face exists again. (This is also how existing
  installs get upgraded by the watcher's `halfbold sync`.)
- `tests/test_api.py`: the `build` subcommand with `-o <dir>/X-Half.ttf` also
  writes `<dir>/X-HalfBold.ttf`. Find the existing `build` subcommand test in
  `tests/test_api.py` (`grep -n '"build"' tests/test_api.py`) and follow it.
- `tests/test_build.py::test_cli_defaults_output_next_to_regular`: also assert
  `regular.with_name("Test-Regular-HalfBold.ttf").exists()`.

Then implement:

- `scan.py`: add `Candidate.bold_face_output` property returning
  `bold_face_path(self.output)`. In `is_stale`, return `True` when either
  output is missing; compare source mtimes against the older of the two
  outputs. In `build_all`, after `build_halfbold_font(...)`, call
  `build_bold_face(candidate.regular, candidate.bold, candidate.bold_face_output, settings)`
  inside the same `try`.
- `api.py` `build` and `cli.py` `main`: after `build_halfbold_font`, call
  `build_bold_face(args.regular, args.bold, bold_face_path(output), settings)`.
  Add `"bold_face": str(bold_face_path(output))` to the `api.build` payload.
  Leave the CLI's printed line unchanged.

If you find a fourth call site that **installs** fonts (writes into a fonts
directory), it needs the same call; list it in your report.

Verify: `uv run pytest -q` → all pass.

### Step 4: Reset deletes the Half Bold faces too

The Bold face's family is `<Family> Half`, so `find_installed_half_fonts`
should already list it and Reset's **Also delete every Half font** should
already delete it. Prove it: in
`tests/test_api.py::test_reset_delete_fonts_removes_watcher_then_half_fonts`,
after the reset assert `not list(fonts.glob("*-HalfBold.ttf"))`, and that
`payload["deleted"]` is still `["Pair Half", "Var Half"]` (families, no
duplicates).

Verify: `uv run pytest -q tests/test_api.py` → all pass. If this test fails
without a code change, STOP (see STOP conditions).

### Step 5: Lint and format

Verify: `uv run ruff check .` → `All checks passed!`;
`uv run ruff format --check .` → exit 0; `uv run pytest -q` → all pass.

### Step 6: Docs

- `CONTEXT.md`: change the **Half font** definition to say the family is
  installed as two Faces: the Regular, which carries the half-bold effect, and
  the **Half Bold face**, the source's plain bold outlines with no half-bold
  rules, so already-bold text is drawn as ordinary bold. Add a **Half Bold
  face** entry in the same format as the others (`**Term**:` line, one
  sentence, `_Avoid_:` line; suggest avoiding "bold companion", "bold variant").
- `AGENTS.md`, "How it works": add one bullet after the `rename_font` bullet:
  `build_bold_face` writes `<stem>-HalfBold.ttf` next to every installed Half
  font, the Bold source renamed into the Half family (subfamily `Bold`,
  `usWeightClass` 700, `fsSelection` BOLD), with no `calt` rules, so apps pick
  it for bold text instead of synthesizing bold over half-bold letters. The
  app's preview is built without it.
- `README.md`: near line 87 (the paragraph on plain and bold weights), one or
  two sentences saying bold text uses the Half Bold face and is drawn plain
  bold, at the Bold weight.

Verify: `grep -n "Half Bold face" CONTEXT.md AGENTS.md README.md` → at least one
hit per file.

## Test plan

New tests (all in existing files, following `make_font` fixtures):

- `test_build.py`: rename as Bold; Bold face from a static pair (no `.half`
  glyphs, bold advance widths, names); Bold face from a variable font (no
  `fvar`, style Bold); Bold face keeps `liga`; CLI writes the Bold face.
- `test_scan.py`: `build_all` writes both files, stays idempotent, the Bold
  face is never a Candidate; a missing Bold face makes the Candidate stale.
- `test_api.py`: `build` writes the Bold face and reports it; Reset deletes it.

## Done criteria

- `uv run pytest -q` → all pass, at least 8 more tests than 173.
- `uv run ruff check .` → `All checks passed!`
- `uv run ruff format --check .` → exit 0.
- `git diff --stat 00fe501..HEAD` lists only in-scope files.
- `grep -rn "build_bold_face" src/halfbold` shows calls in `scan.py`, `api.py`,
  `cli.py` and none in `build_into_cache`.
- Manual check for the maintainer (report as pending, do not block on it):
  run `uv run halfbold sync` (or click **Convert** in the app), restart Chrome,
  open a page with `<b>` text and confirm bold words look ordinary bold, not
  half-bold-plus-heavier; in Font Book, `<Family> Half` lists two faces.

## STOP conditions

- `read_font_info` / `is_half_output` does **not** treat the Bold face as a
  Half output (it shows up as a Candidate, or Reset does not delete it). Report
  which name ID `read_font_info` reads before changing `scan.py` detection.
- A test shows `copy_bold_glyphs` or `build_halfbold_font` mutates the bold
  `TTFont` in a way that would matter if the Bold face reused it. (This plan
  loads the bold source separately to avoid that; if you are tempted to share
  the loaded object, stop and ask.)
- Any existing test changes meaning (not just gains an assertion) to pass.
- A verification fails twice after a reasonable fix attempt.

## Maintenance notes

- Build time roughly doubles for variable fonts (the bold instance is made
  twice). Acceptable; if it matters later, `build_halfbold_font` could return
  the loaded bold instance, but only after confirming it is not mutated.
- Chrome and VS Code cache the installed font list; after the first install of
  Bold faces the maintainer may need to restart them once.
- Plan 017 (Chrome converts page web fonts to Half) will build Half fonts for
  web faces; it should reuse `build_bold_face` for the same reason.
- If the Bold weight setting is below 600, bold text is drawn at that lighter
  weight, since the Half Bold face is the Bold-weight source. That is the
  family's definition of bold in halfbold and is intended.
