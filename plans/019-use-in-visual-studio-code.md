# Plan 019: The app has a "Use in Visual Studio Code" button that makes the selected font's Half the VS Code editor font

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 91e4fc9..HEAD -- src/halfbold/api.py src/halfbold/vscode.py tests/test_api.py tests/test_vscode.py app/src/api.ts app/src/main.ts README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `91e4fc9`, 2026-10-20

## Why this matters

The desktop app (`app/`, Tauri) can build a Half font and send it to Chrome
with **Use in browser**. VS Code has no such button, so the maintainer has to
edit `settings.json` by hand: set `editor.fontFamily`, and also turn on
`editor.fontLigatures`. The second setting is easy to miss. VS Code's default
(`false`) renders the editor with `font-feature-settings: "liga" off, "calt" off`.
That turns off the `calt` feature, which is exactly what Half fonts use to bold
word starts, so the font installs but shows no half-bold effect.

This plan adds one button. It builds the Half font if needed, writes both
settings into the user's VS Code `settings.json` without touching the file's
comments or other settings, and reports success in the status bar.

## Current state

Files and their roles:

- `src/halfbold/api.py` — `halfbold-api`, the JSON command line interface the
  app drives. Each subcommand is an argparse subparser with a handler that
  returns a dict, printed as JSON. Errors raised as `ValueError` become
  `{"error": "..."}` with exit code 1 (and `{"ok": false, "error"}` in `serve` mode).
- `src/halfbold/web.py` — the closest existing pattern: a small module that
  edits a config file (the Chrome extension's CSS) in place, line by line,
  with a regex, and leaves everything else in the file unchanged.
- `app/src/api.ts` — typed TS wrappers. Each one calls `api<T>(...args)`, which
  forwards to `halfbold-api serve`. The Rust side (`app/src-tauri/src/lib.rs`
  `fn api`) passes any args through, so **no Rust change is needed**.
- `app/src/main.ts` — all UI logic. `renderInstalledActions` draws the buttons
  for a font selected on the Installed tab; `onUseAs` is the existing
  "build, then apply" handler to model after.

`src/halfbold/api.py:303-311` (the `web` handler; its family check is what
the new handler needs too):

```python
def web(args: argparse.Namespace) -> dict:
    if args.kind:
        family = args.family
        if not family.endswith(f" {STYLE_SUFFIX}"):
            family = f"{family} {STYLE_SUFFIX}"
        if family not in find_installed_half_families(args.fonts_dir):
            raise ValueError(f"{family!r} is not installed in {args.fonts_dir}")
        set_web_font(args.css, args.kind, family)
    return get_web_fonts(args.css)
```

`src/halfbold/api.py:357-364` (subparser wiring; add the new one right before
`browser_parser`):

```python
    web_parser = subparsers.add_parser("web")
    web_parser.add_argument("kind", nargs="?", choices=KINDS)
    web_parser.add_argument("family", nargs="?")
    web_parser.add_argument("--css", type=Path, default=DEFAULT_CSS)
    web_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
    web_parser.set_defaults(handler=web)

    browser_parser = subparsers.add_parser("browser")
```

`src/halfbold/api.py:38-39` (imports; alphabetical by module):

```python
from halfbold.settings import Settings, load_settings, save_settings
from halfbold.web import get_web_fonts, set_web_font
```

`app/src/api.ts:89-92`:

```ts
export function settings(values?: Partial<Settings>) {
  const args = values ? ["settings", JSON.stringify(values)] : ["settings"];
  return api<{ settings: Settings; defaults: Settings }>(...args);
}
```

`app/src/main.ts:1-19` imports from `./api` (the line `settings as settingsApi,`
sits at line 11, followed by `webFonts,`).

`app/src/main.ts:538-552`:

```ts
function renderInstalledActions(c: Candidate) {
  actionsEl.textContent = "";
  actionsEl.append(makeButton("Use in browser", () => onUseAs(c.kind === "mono" ? "mono" : "sans", c), "primary"));
  actionsEl.append(makeButton(c.built ? "Rebuild Half" : "Build Half", () => onBuild(c)));
  const advanced = document.createElement("details");
  ...
```

`app/src/main.ts:580-604` is `onUseAs`; `main.ts:606` is
`const browserStatusEl = $("#browser-status");`. Helpers you will reuse, all
in `main.ts`: `busy()` (line 132), `run(label, task)` (line 147, shows `label`
while running, shows the error and returns `null` on failure),
`showNote(message)` (line 141), `reloadInstalled()` (line 744, refetches the
font list so the `built` flags update), and `build(c)` from `./api`.

### Facts about VS Code the code relies on (verified by the planner)

- User settings live at `~/Library/Application Support/Code/User/settings.json`
  on macOS and `~/.config/Code/User/settings.json` on Linux.
- The file is **JSONC**: `//` and `/* */` comments and trailing commas are
  legal. Python's `json` cannot read it, and re-serialising would delete the
  user's comments. The plan therefore edits the text in place: it tokenises
  the file, finds the top-level value spans, and swaps or inserts only the
  value it needs.
- Keys inside language blocks such as `"[python]": { "editor.fontFamily": … }`
  are nested, so they are not top-level and must be left alone.
- `editor.fontLigatures`: `false` (the default) turns off `calt`; `true` turns
  on `liga` and `calt`; a string is used as raw `font-feature-settings` and
  leaves `calt` at its browser default (on). So: set it to `true` only when it
  is absent or `false`, and leave `true` or any string alone.
- VS Code reloads `settings.json` on its own when the file changes. A font
  installed while VS Code is running may only appear after
  **Developer: Reload Window**, so the success note says so.

### Conventions (from `AGENTS.md` — follow exactly)

- **No comments anywhere in code**, and no lint suppressions. Ruff's `ERA`
  rule catches commented-out code. Write clear names instead.
- Small functions that do one thing; clear, specific names.
- Domain words (from `CONTEXT.md`): a **Half font** is "the converted output
  of a Candidate, installed next to the original under the family name plus
  ` Half`". Use "Half" for it, not "bionic" or "output font".
- Commits are Conventional Commits (`feat:`, `test:`, `docs:`); the
  `commit-msg` hook rejects anything else. The `pre-commit` hook runs ruff
  format check, ruff check and pytest.

## Commands you will need

| Purpose | Command (from repo root unless noted) | Expected on success |
|---|---|---|
| Python lint | `uv run ruff check .` | `All checks passed!` |
| Python format | `uv run ruff format --check .` | `N files already formatted`, exit 0 |
| Python tests | `uv run pytest -q` | all pass (160 after this plan; 150 before) |
| One test file | `uv run pytest -q tests/test_vscode.py` | all pass |
| TS install | `cd app && bun install` | exit 0 |
| TS typecheck | `cd app && bunx tsc --noEmit -p .` | no output, exit 0 |
| TS tests | `cd app && bun test` | `4 pass`, 0 fail |
| Fallow | `cd app && npx -y fallow --format json` | `check.total_issues` is **2**, the same as before your change (`dev.ts` flagged as unused file, already on main: leave it) |

## Scope

**In scope** (the only files you should modify):

- `src/halfbold/vscode.py` (create)
- `tests/test_vscode.py` (create)
- `src/halfbold/api.py`
- `tests/test_api.py`
- `app/src/api.ts`
- `app/src/main.ts`
- `README.md`
- `plans/README.md` (status row only)

**Out of scope** (do NOT touch):

- `app/src-tauri/**` — Rust passes any API args through; no change needed.
- `app/src/styles.css` and `app/index.html` — the existing `#actions button`
  style already covers the new button.
- `src/halfbold/cli.py` — no `halfbold --vscode` CLI flag; the app is the only
  caller (YAGNI).
- `terminal.integrated.fontFamily` and any other VS Code setting besides
  `editor.fontFamily` and `editor.fontLigatures`. The integrated terminal
  draws with xterm.js, where `calt` support is uncertain. That is deferred.
- VS Code Insiders, VSCodium and Cursor settings paths — deferred.
- The **Brew** tab's actions (`renderBrewDetail`) — only Installed fonts get
  the button.
- The pre-existing fallow finding about `app/dev.ts` (a false positive: it is
  run by `bun run dev.ts`).

## Git workflow

- Branch: `advisor/019-use-in-vscode`
- One commit per step group; examples from `git log`:
  `feat: extract a drawable standalone face from a collection`,
  `docs: describe how collection faces are addressed`.
  Suggested: `feat: write the VS Code editor font into settings.json`,
  `feat: add a vscode halfbold-api subcommand`,
  `feat: add a Use in Visual Studio Code button to the app`,
  `docs: describe the Use in Visual Studio Code button`.
- End each commit message with the `Co-Authored-By` trailer your operator
  gives you, if any.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Write the failing tests for the settings editor

Create `tests/test_vscode.py` with exactly this content (TDD: it fails until
step 2):

```python
import json
from pathlib import Path

import pytest

from halfbold.vscode import get_setting, set_setting, use_in_vscode

WITH_COMMENTS = """{
    // Editor look
    "editor.fontSize": 14,
    /* "editor.fontFamily": "Commented Out" */
    "[python]": {
        "editor.fontFamily": "Language Font"
    },
    "editor.fontFamily": "Menlo, monospace",
}
"""


def test_set_setting_replaces_only_the_top_level_value():
    text = set_setting(WITH_COMMENTS, "editor.fontFamily", "'Pair Half', monospace")

    assert "// Editor look" in text
    assert '/* "editor.fontFamily": "Commented Out" */' in text
    assert '"editor.fontFamily": "Language Font"' in text
    assert '"editor.fontFamily": "\'Pair Half\', monospace",' in text
    assert get_setting(text, "editor.fontFamily") == "'Pair Half', monospace"


def test_set_setting_adds_a_missing_key():
    text = set_setting(WITH_COMMENTS, "editor.fontLigatures", True)

    assert get_setting(text, "editor.fontLigatures") is True
    assert get_setting(text, "editor.fontSize") == 14


def test_set_setting_fills_an_empty_object():
    text = set_setting("{}\n", "editor.fontLigatures", True)

    assert json.loads(text) == {"editor.fontLigatures": True}


def test_set_setting_rejects_a_non_object():
    with pytest.raises(ValueError, match="not a JSON object"):
        set_setting("[]", "editor.fontFamily", "x")


def test_use_in_vscode_sets_family_and_turns_on_ligatures(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{\n    "editor.fontLigatures": false\n}\n')

    result = use_in_vscode(settings, "Pair Half")

    assert json.loads(settings.read_text()) == {
        "editor.fontFamily": "'Pair Half', monospace",
        "editor.fontLigatures": True,
    }
    assert result == {
        "settings": str(settings),
        "font_family": "'Pair Half', monospace",
    }


def test_use_in_vscode_keeps_a_custom_ligature_string(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"editor.fontLigatures": "\'ss01\'"}')

    use_in_vscode(settings, "Pair Half")

    assert get_setting(settings.read_text(), "editor.fontLigatures") == "'ss01'"


def test_use_in_vscode_creates_settings_in_an_existing_folder(tmp_path: Path):
    settings = tmp_path / "settings.json"

    use_in_vscode(settings, "Pair Half")

    assert json.loads(settings.read_text())["editor.fontLigatures"] is True


def test_use_in_vscode_without_vscode_raises(tmp_path: Path):
    settings = tmp_path / "Code" / "User" / "settings.json"

    with pytest.raises(ValueError, match="Visual Studio Code settings folder"):
        use_in_vscode(settings, "Pair Half")
```

**Verify**: `uv run pytest -q tests/test_vscode.py` → fails with
`ModuleNotFoundError: No module named 'halfbold.vscode'`.

### Step 2: Create `src/halfbold/vscode.py`

Create it with exactly this content. The planner ran this exact code through
ruff and pytest at `91e4fc9`.

```python
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FONT_FAMILY = "editor.fontFamily"
FONT_LIGATURES = "editor.fontLigatures"
TOKEN = re.compile(
    r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*.*?\*/|[{}\[\]:,]|[^\s{}\[\]:,"/]+',
    re.DOTALL,
)


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


def default_settings_path() -> Path:
    if sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
    else:
        support = Path.home() / ".config"
    return support / "Code" / "User" / "settings.json"


def tokens(text: str) -> list[Token]:
    return [
        Token(match.group(), match.start(), match.end())
        for match in TOKEN.finditer(text)
        if not match.group().startswith(("//", "/*"))
    ]


def value_end(items: list[Token], index: int) -> int:
    depth = 0
    for position in range(index, len(items)):
        text = items[position].text
        if text in "{[":
            depth += 1
        elif text in "}]":
            depth -= 1
        if depth == 0:
            return position
    raise ValueError("settings.json has an unclosed value")


def top_level_values(text: str) -> tuple[Token, dict[str, tuple[int, int]]]:
    items = tokens(text)
    if not items or items[0].text != "{":
        raise ValueError("settings.json is not a JSON object")
    values: dict[str, tuple[int, int]] = {}
    index = 1
    while index < len(items) and items[index].text != "}":
        if items[index].text == ",":
            index += 1
            continue
        key = json.loads(items[index].text)
        last = value_end(items, index + 2)
        values[key] = (items[index + 2].start, items[last].end)
        index = last + 1
    return items[0], values


def set_setting(text: str, key: str, value: object) -> str:
    opening, values = top_level_values(text)
    encoded = json.dumps(value)
    if key in values:
        start, end = values[key]
        return text[:start] + encoded + text[end:]
    separator = "," if values else "\n"
    insertion = f'\n    "{key}": {encoded}{separator}'
    return text[: opening.end] + insertion + text[opening.end :]


def get_setting(text: str, key: str) -> object:
    _, values = top_level_values(text)
    if key not in values:
        return None
    start, end = values[key]
    return json.loads(text[start:end])


def use_in_vscode(settings_path: Path, family: str) -> dict:
    if not settings_path.parent.is_dir():
        raise ValueError(
            f"Visual Studio Code settings folder not found: {settings_path.parent}"
        )
    text = settings_path.read_text() if settings_path.exists() else "{}\n"
    text = set_setting(text, FONT_FAMILY, f"'{family}', monospace")
    if not get_setting(text, FONT_LIGATURES):
        text = set_setting(text, FONT_LIGATURES, True)
    settings_path.write_text(text)
    return {
        "settings": str(settings_path),
        "font_family": get_setting(text, FONT_FAMILY),
    }
```

How it works, so you can debug it: `tokens` splits the text into strings,
punctuation and bare literals, and drops comments. `top_level_values` walks the
tokens of the outer object as `key : value ,` and records each top-level
value's character span. Nested objects and arrays are skipped whole by
`value_end`, so `"[python]": {...}` is never edited inside. `set_setting`
replaces a span, or inserts a new key just after the opening `{`. It adds a
comma only when other keys follow.

**Verify**: `uv run pytest -q tests/test_vscode.py` → `8 passed`.
Then `uv run ruff check . && uv run ruff format --check .` → both clean.

### Step 3: Add the `vscode` subcommand to `halfbold-api` (test first)

3a. Append these two tests to the end of `tests/test_api.py`. `fill_fonts_dir`,
`build_all`, `json`, `Path` and `main` are already imported there, and the
existing `test_web_sets_slot_and_reads_back` is the structural model:

```python


def test_vscode_sets_editor_font_for_installed_half(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n")

    result = main(
        ["vscode", "Pair", "--settings", str(settings), "--fonts-dir", str(fonts)]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["font_family"] == "'Pair Half', monospace"
    assert json.loads(settings.read_text())["editor.fontLigatures"] is True


def test_vscode_rejects_family_without_half(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n")

    result = main(
        ["vscode", "Pair", "--settings", str(settings), "--fonts-dir", str(fonts)]
    )

    assert result == 1
    assert "Pair Half" in json.loads(capsys.readouterr().out)["error"]
    assert settings.read_text() == "{}\n"
```

**Verify**: `uv run pytest -q tests/test_api.py -k vscode` → 2 failed. argparse
rejects the unknown `vscode` choice and exits with code 2, so pytest reports a
`SystemExit` failure.

3b. In `src/halfbold/api.py`:

1. Add the import between the `settings` and `web` imports:
   `from halfbold.vscode import default_settings_path, use_in_vscode`
2. Pull the family check out of `web` into a shared helper, and add the
   handler. Replace the whole `web` function (lines 303-311) with:

```python
def installed_half_family(family: str, fonts_dir: Path) -> str:
    if not family.endswith(f" {STYLE_SUFFIX}"):
        family = f"{family} {STYLE_SUFFIX}"
    if family not in find_installed_half_families(fonts_dir):
        raise ValueError(f"{family!r} is not installed in {fonts_dir}")
    return family


def web(args: argparse.Namespace) -> dict:
    if args.kind:
        family = installed_half_family(args.family, args.fonts_dir)
        set_web_font(args.css, args.kind, family)
    return get_web_fonts(args.css)


def vscode(args: argparse.Namespace) -> dict:
    family = installed_half_family(args.family, args.fonts_dir)
    return use_in_vscode(args.settings, family)
```

3. In `parse_args`, insert directly before
   `browser_parser = subparsers.add_parser("browser")`:

```python
    vscode_parser = subparsers.add_parser("vscode")
    vscode_parser.add_argument("family")
    vscode_parser.add_argument("--settings", type=Path, default=default_settings_path())
    vscode_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
    vscode_parser.set_defaults(handler=vscode)
```

**Verify**:
- `uv run pytest -q` → all pass (160 total, including the existing
  `test_web_sets_slot_and_reads_back`, which proves the `web` refactor kept
  its behaviour).
- `uv run ruff check . && uv run ruff format --check .` → clean. If the
  format check fails, run `uv run ruff format src/halfbold/api.py
  tests/test_api.py` and re-check. Only in-scope files may change.

### Step 4: Add the TS wrapper in `app/src/api.ts`

Insert directly above `export function settings(values?: Partial<Settings>) {`:

```ts
export function setVscodeFont(family: string) {
  return api<{ settings: string; font_family: string }>("vscode", family);
}

```

**Verify**: `cd app && bun install && bunx tsc --noEmit -p .` → exit 0.

### Step 5: Add the button and handler in `app/src/main.ts`

1. In the `import { ... } from "./api";` block, add `setVscodeFont,` on its
   own line right after `settings as settingsApi,`.
2. In `renderInstalledActions`, insert this line between the
   "Use in browser" line and the "Rebuild Half"/"Build Half" line:

```ts
  actionsEl.append(makeButton("Use in Visual Studio Code", () => onUseInVscode(c)));
```

3. Insert this function directly above
   `const browserStatusEl = $("#browser-status");`:

```ts
async function onUseInVscode(c: Candidate) {
  if (busy()) return;
  const result = await run(`Applying ${c.family} to Visual Studio Code…`, async () => {
    await build(c);
    return setVscodeFont(c.family);
  });
  if (!result) return;
  await reloadInstalled();
  showNote(`${c.family} Half is now the Visual Studio Code editor font. Reload any open VS Code window to see it.`);
}
```

The button is plain (no `"primary"` class). "Use in browser" stays the one
primary action. `run` already shows any error (for example, "Visual Studio
Code settings folder not found: …") in the status bar, so no extra error
handling is needed.

**Verify** (from `app/`):
- `bunx tsc --noEmit -p .` → exit 0
- `bun test` → 4 pass, 0 fail
- `npx -y fallow --format json` → `check.total_issues` is 2 (unchanged)
- `grep -n "Use in Visual Studio Code" src/main.ts` → exactly 1 match

### Step 6: Document it in `README.md`

1. Under `## App`, after the paragraph that ends
   `See [browser setup](chrome-extension/README.md) for upgrades and troubleshooting.`,
   add a blank line and this paragraph:

```markdown
For Visual Studio Code, select a font and click **Use in Visual Studio Code**.
It builds and installs the Half font, sets it as `editor.fontFamily` in your
user `settings.json`, and turns on `editor.fontLigatures` so `calt` runs.
Comments and other settings in the file are kept. Reload open VS Code windows
to pick up a newly installed font.
```

2. In the `halfbold-api` paragraph, change
   `` `cask-face`, `cask-install`, `settings`, `web`. `` to
   `` `cask-face`, `cask-install`, `settings`, `web`, `vscode`. ``

**Verify**: `grep -c "Use in Visual Studio Code" README.md` → `1`;
`grep -n '`web`, `vscode`' README.md` → 1 match.

### Step 7: Manual check in the real app (operator / maintainer)

This step writes to the real VS Code settings. Do it only if your operator
allows it; otherwise report "manual GUI check pending".

1. `cp ~/Library/Application\ Support/Code/User/settings.json /tmp/vscode-settings.bak`
2. `uv run halfbold desktop`. On the Installed tab, select a monospace font,
   for example Menlo, and click **Use in Visual Studio Code**.
3. The status bar shows `Menlo Half is now the Visual Studio Code editor font…`.
   `grep -n "editor.font" ~/Library/Application\ Support/Code/User/settings.json`
   shows `"editor.fontFamily": "'Menlo Half', monospace"` and
   `"editor.fontLigatures": true`.
4. In VS Code, run **Developer: Reload Window**. Identifiers in the editor
   show bold word starts.
5. Restore if wanted:
   `cp /tmp/vscode-settings.bak ~/Library/Application\ Support/Code/User/settings.json`.

## Test plan

- `tests/test_vscode.py` (new, 8 tests): top-level replace keeps comments and
  `[python]` overrides; missing key insert; empty object; non-object error;
  end-to-end `use_in_vscode` turns `false` ligatures to `true`; a ligature
  string is preserved; settings file created when the folder exists; error
  when the VS Code folder is missing. Modeled on `tests/test_web.py`.
- `tests/test_api.py` (+2): success path through `main(["vscode", …])`, and
  rejection of a family whose Half is not installed, with the file left
  unchanged. Modeled on `test_web_sets_slot_and_reads_back`.
- No new TS tests: the UI is thin glue over `run`/`build`, and `app/` only
  unit-tests pure helpers (`sequence.test.ts`).

## Done criteria

ALL must hold:

- [ ] `uv run ruff check .` → `All checks passed!`
- [ ] `uv run ruff format --check .` → exit 0
- [ ] `uv run pytest -q` → all pass, 160 tests
- [ ] `cd app && bunx tsc --noEmit -p .` → exit 0
- [ ] `cd app && bun test` → 0 fail
- [ ] `cd app && npx -y fallow --format json` → `check.total_issues` == 2
- [ ] `grep -nE '^\s*#|\s#\s' src/halfbold/vscode.py tests/test_vscode.py` → no matches (no comments)
- [ ] `uv run halfbold-api vscode Nope --settings /tmp/none/settings.json` → prints `{"error": "'Nope Half' is not installed in …"}`, exit 1
- [ ] `git status --short` lists only in-scope files
- [ ] `plans/README.md` row 019 updated

## STOP conditions

Stop and report back (do not improvise) if:

- The excerpts in "Current state" don't match the live code (for example,
  `web` no longer has the inline family check, or `renderInstalledActions`
  no longer starts with the "Use in browser" button).
- `tests/test_vscode.py` still fails after step 2 with the code copied
  exactly. Report the failure output. Do not change the tests to make them
  pass.
- Fallow's `total_issues` rises above 2 and the new finding is not something
  you can fix by deleting code you added.
- You feel the need to change Rust (`app/src-tauri`), CSS or `cli.py`. The
  plan says none of them need changes; if one does, the plan is wrong.
- In step 7 the real `settings.json` fails to parse with
  `settings.json is not a JSON object` or `has an unclosed value`. Restore the
  backup and report the file's shape (key names only, no values).

## Maintenance notes

- `vscode.py` is a minimal JSONC reader. It handles comments, trailing commas,
  nested objects and arrays, and escaped quotes. It does not handle JSON5
  extras that VS Code also rejects, such as unquoted keys. If a user reports a
  parse error, add a test with their file's shape first.
- The family is written as `'<Family> Half', monospace`, replacing any
  previous `editor.fontFamily`. If the maintainer later wants the old value
  kept as a fallback, change only `use_in_vscode`.
- Deferred on purpose: the integrated terminal font
  (`terminal.integrated.fontFamily`; xterm.js `calt` support needs its own
  check), VS Code Insiders, VSCodium and Cursor paths (each is just a
  different `settings_path`), and an "active" state on the button (would need
  reading `settings.json` at startup, like `webFonts()` does for slots).
- Reviewers: check that `web` still behaves the same after the
  `installed_half_family` extraction (its API test covers it), and that the
  button is not added to the Brew tab.
