# Plan 007: Give every Half font its own PostScript, full and unique names so it never shadows the source font

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 56a59d9..HEAD -- src/halfbold/build.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (one function in `src/halfbold/build.py`; output fonts change only in their `name` table)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `56a59d9`, 2026-09-16

## Why this matters

On 2026-09-16 the maintainer's terminal (Ghostty, configured with
`font-family = JetBrainsMono Nerd Font`) started rendering every word
half-bold although its config never changed. Cause, confirmed with CoreText:

- `rename_font` in `src/halfbold/build.py` rewrites name IDs 1 and 16
  (family) to `<family> Half`, but it only rewrites IDs 3 (unique ID), 4
  (full name) and 6 (PostScript name) when they *contain the typographic
  family string*. Nerd Fonts use a short legacy name there: ID 16 is
  `JetBrainsMono Nerd Font` but IDs 1/3/4/6 say `JetBrainsMono NF` /
  `JetBrainsMonoNF-Regular`. Nothing matches, so the Half font keeps the
  source font's PostScript and full names.
- macOS treats the PostScript name as the font's identity. With two installed
  files both named `JetBrainsMonoNF-Regular`, CoreText resolved that name to
  the newer file, the Half one:

  ```
  JetBrainsMonoNF-Regular  -> JetBrainsMono Nerd Font Half | JetBrainsMonoNerdFont-Half.ttf
  JetBrainsMono NF Regular -> JetBrainsMono Nerd Font Half | JetBrainsMonoNerdFont-Half.ttf
  JetBrainsMonoNF-Bold     -> JetBrainsMono Nerd Font      | JetBrainsMonoNerdFont-Bold.ttf
  ```

  Ghostty (and any app that resolves the regular face by PostScript or full
  name) therefore got the Half font. Bold stayed correct because no Half file
  claims `JetBrainsMonoNF-Bold`.

Observed state of the installed fonts (`~/Library/Fonts`, 2026-09-16):

```
JetBrainsMonoNerdFont-Regular.ttf  {1: 'JetBrainsMono NF',           4: 'JetBrainsMono NF Regular', 6: 'JetBrainsMonoNF-Regular', 16: 'JetBrainsMono Nerd Font'}
JetBrainsMonoNerdFont-Half.ttf     {1: 'JetBrainsMono Nerd Font Half', 4: 'JetBrainsMono NF Regular', 6: 'JetBrainsMonoNF-Regular', 16: 'JetBrainsMono Nerd Font Half'}
```

Same for the `Mono`, `Propo` and `NL` variants. `Inter-Half.ttf` is fine
because Inter's IDs 1/4/6 do contain `Inter`.

After this plan every Half font carries names that cannot collide with its
source: ID 6 `<Family>Half-<Style>`, ID 4 `<Family> Half <Style>`, ID 3
derived from the new ID 6. Rebuilding with `halfbold --all --force` then
restores the terminal without touching Ghostty's config.

## Current state

- `src/halfbold/build.py` — `rename_font` (`src/halfbold/build.py:134-147`):

  ```python
  def rename_font(font: TTFont) -> None:
      name_table = font["name"]
      family = name_table.getBestFamilyName()
      base_family = " ".join(part for part in family.split() if part != "Variable")
      new_family = f"{base_family} {STYLE_SUFFIX}"
      for record in name_table.names:
          if record.nameID in (1, 16):
              record.string = new_family
          elif record.nameID in (3, 4):
              record.string = record.toUnicode().replace(family, new_family)
          elif record.nameID == 6:
              record.string = record.toUnicode().replace(
                  family.replace(" ", ""), new_family.replace(" ", "")
              )
  ```

  `STYLE_SUFFIX = "Half"` (`build.py:12`). `getBestFamilyName()` prefers ID 16
  over ID 1. `rename_font` is called once from `build_halfbold_font`
  (`build.py:34`) on the instanced regular font, after the `calt` GSUB is
  added.

- `tests/test_build.py:28-40` — `test_build_adds_bold_glyphs_and_calt` ends
  with `assert font["name"].getBestFamilyName() == "Test Half"`. It is the
  only rename assertion.
- `tests/conftest.py:21-34` — `make_font(path, family, style, stem)` builds a
  fixture TTF via `FontBuilder.setupNameTable({"familyName": …, "styleName": …})`,
  which writes IDs 1, 2, 3, 4, 5, 6 (ID 6 = `Family-Style` with spaces
  removed) and no ID 16/17. To reproduce the Nerd Font shape a test must set
  ID 16 explicitly (see Step 1).
- Conventions (`AGENTS.md`): no code comments; Conventional Commits; run
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`
  after changes and fix everything they report; `.githooks/pre-commit` runs
  the same. Only TrueType fonts are supported.
- The `--all` mode (`src/halfbold/cli.py`, `src/halfbold/scan.py`) rebuilds a
  Half font when its source is newer or `--force` is given; it is how the
  maintainer will roll this fix out to installed fonts. Do not change it.

## Commands you will need

| Purpose   | Command                            | Expected on success |
|-----------|------------------------------------|---------------------|
| Tests     | `uv run pytest`                    | all pass            |
| Lint      | `uv run ruff check .`              | `All checks passed!`|
| Format    | `uv run ruff format --check .`     | `N files already formatted` |
| Inspect   | `uv run python -c "from fontTools.ttLib import TTFont; n=TTFont('FILE')['name']; print({i: n.getDebugName(i) for i in (1,3,4,6,16,17)})"` | prints the six names |

## Scope

**In scope**:
- `src/halfbold/build.py` (`rename_font` only)
- `tests/test_build.py`
- `tests/conftest.py` (only if you add a helper for setting ID 16/17; optional)

**Out of scope**:
- `src/halfbold/cli.py`, `src/halfbold/scan.py`, `src/halfbold/web.py`.
- `tui/**`, `chrome-extension/**`.
- Deleting or rebuilding the maintainer's installed fonts. The plan ends
  with the command the maintainer runs; you do not run it.
- Changing the family name scheme (`<family> Half`); the Chrome extension
  and the TUI depend on it.

## Git workflow

- Branch: `advisor/007-half-font-unique-names`
- One commit: `fix: give Half fonts unique PostScript and full names`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Failing test that reproduces the Nerd Font name shape

In `tests/test_build.py` add:

```python
def test_rename_gives_half_font_its_own_postscript_and_full_names(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    for path in (regular, bold):
        font = TTFont(path)
        name = font["name"]
        style = name.getDebugName(2)
        name.setName("Test NF", 1, 3, 1, 0x409)
        name.setName(f"Test NF {style}", 4, 3, 1, 0x409)
        name.setName(f"TestNF-{style}", 6, 3, 1, 0x409)
        name.setName(f"Test NF {style} 1.0", 3, 3, 1, 0x409)
        name.setName("Test Nerd Font", 16, 3, 1, 0x409)
        font.save(path)
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    name = TTFont(out)["name"]
    assert name.getDebugName(16) == "Test Nerd Font Half"
    assert name.getDebugName(1) == "Test Nerd Font Half"
    assert name.getDebugName(6) == "TestNerdFontHalf-Regular"
    assert name.getDebugName(4) == "Test Nerd Font Half Regular"
    assert name.getDebugName(3) != "Test NF Regular 1.0"
    assert "TestNF-Regular" not in {r.toUnicode() for r in name.names}
```

`setName(string, nameID, platformID, platEncID, langID)` with `(3, 1, 0x409)`
is the Windows/Unicode/English record that `getDebugName` and
`getBestFamilyName` read first. `TTFont` is already imported in this test
file; `Path` too.

**Verify**: `uv run pytest tests/test_build.py -k postscript` → 1 failed, on
the `getDebugName(6)` assertion (current value `TestNF-Regular`).

### Step 2: Rewrite `rename_font`

Replace the function body with logic that *derives* IDs 3, 4 and 6 instead
of substring-replacing them:

```python
def rename_font(font: TTFont) -> None:
    name_table = font["name"]
    family = name_table.getBestFamilyName()
    base_family = " ".join(part for part in family.split() if part != "Variable")
    new_family = f"{base_family} {STYLE_SUFFIX}"
    style = name_table.getDebugName(17) or name_table.getDebugName(2) or "Regular"
    postscript = f"{new_family.replace(' ', '')}-{style.replace(' ', '')}"
    full_name = f"{new_family} {style}"
    for record in name_table.names:
        if record.nameID in (1, 16):
            record.string = new_family
        elif record.nameID == 4:
            record.string = full_name
        elif record.nameID == 6:
            record.string = postscript
        elif record.nameID == 3:
            record.string = f"{postscript};{STYLE_SUFFIX}"
```

Notes for the executor:

- Keep the loop over `name_table.names` so every platform/language record is
  rewritten, as today.
- ID 6 must be ASCII with no spaces (OpenType rule); `new_family` comes from
  the source font and could contain non-ASCII — leave that edge case alone,
  every font this tool has met so far is ASCII. Do not add validation.
- ID 3 only needs to be unique per font; `postscript;Half` is enough.
- A variable font instanced at 400 has ID 2 `Regular` (the instancer keeps
  the default-instance names), so `style` resolves to `Regular` there.

**Verify**: `uv run pytest` → all pass, including the new test and the
untouched `test_build_adds_bold_glyphs_and_calt` (family still `Test Half`).

### Step 3: Lint and format

**Verify**: `uv run ruff check .` → `All checks passed!`;
`uv run ruff format --check .` → no files would be reformatted (run
`uv run ruff format .` if it reports any and re-check).

### Step 4: Check a real Nerd Font build without installing it

```sh
uv run halfbold ~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf ~/Library/Fonts/JetBrainsMonoNerdFont-Bold.ttf -o /tmp/JetBrainsMonoNerdFont-Half.ttf
uv run python -c "from fontTools.ttLib import TTFont; n=TTFont('/tmp/JetBrainsMonoNerdFont-Half.ttf')['name']; print({i: n.getDebugName(i) for i in (1,3,4,6,16)})"
```

**Verify**: output is
`{1: 'JetBrainsMono Nerd Font Half', 3: 'JetBrainsMonoNerdFontHalf-Regular;Half', 4: 'JetBrainsMono Nerd Font Half Regular', 6: 'JetBrainsMonoNerdFontHalf-Regular', 16: 'JetBrainsMono Nerd Font Half'}`.
Then `rm /tmp/JetBrainsMonoNerdFont-Half.ttf`. Do **not** write into
`~/Library/Fonts` — that is the maintainer's rollout step below.

## Test plan

- New: `test_rename_gives_half_font_its_own_postscript_and_full_names` in
  `tests/test_build.py` (Step 1), modelled on `test_build_adds_bold_glyphs_and_calt`.
- Existing rename assertion keeps passing.
- `uv run pytest` → all pass.

## Done criteria

- [ ] `uv run pytest` exits 0 with one more test than before
- [ ] `uv run ruff check .` and `uv run ruff format --check .` exit 0
- [ ] `grep -n '\.replace(family' src/halfbold/build.py` → no matches
- [ ] Step 4 prints the expected five names
- [ ] `git status --porcelain` lists only in-scope files
- [ ] `plans/README.md` status row for 007 updated

## Rollout (maintainer, after merge)

```sh
uv run halfbold --all --force
```

rebuilds every installed Half font with the new names. Then quit and reopen
Ghostty (CoreText caches the name → file mapping per process). The terminal
returns to plain `JetBrainsMono Nerd Font`; to read the terminal half-bold on
purpose, set `font-family = JetBrainsMono Nerd Font Half` in the Ghostty
config.

## STOP conditions

- `rename_font` no longer matches the excerpt above.
- After Step 2 the pre-existing assertion `getBestFamilyName() == "Test Half"`
  fails — the family scheme must not change; report instead of adjusting the
  assertion.
- `uv run halfbold` in Step 4 fails for a reason unrelated to names (e.g.
  missing glyphs) — report the error text.

## Maintenance notes

- The TUI (`tui/preview.go` after plan 005) and the Chrome extension address
  the Half font by *family* name (`<family> Half`); this plan does not change
  that, only IDs 3/4/6.
- Reviewer: check that the loop still rewrites every record of IDs 1/16
  (all platforms), and that ID 6 has no spaces.
- Follow-up not in this plan: `halfbold --all` could warn when an installed
  Half font shares a PostScript name with another installed file, catching
  fonts built before this fix.
