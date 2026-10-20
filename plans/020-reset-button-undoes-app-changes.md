# Plan 020: The app has a Reset button that puts VS Code and the Chrome slots back, and can also delete every Half font and remove the file watcher

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md`, unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat ec02854..HEAD -- src/halfbold/api.py src/halfbold/scan.py src/halfbold/vscode.py src/halfbold/reset.py src/halfbold/watcher.py tests/test_api.py tests/test_vscode.py tests/test_reset.py tests/test_watcher.py app/index.html app/src/api.ts app/src/main.ts app/src/styles.css app/src/reset.ts app/src/reset.test.ts README.md CONTEXT.md AGENTS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding. On a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (deletes font files and a launchd agent when the option is ticked)
- **Depends on**: none (builds on plan 019's `vscode.py`, already on main)
- **Category**: direction
- **Planned at**: commit `ec02854`, 2026-10-20

## Why this matters

The desktop app (`app/`, Tauri) changes things outside itself:
**Use in browser** and **Choose slot → Use as …** rewrite the Chrome
extension's Slot lines, and **Use in Visual Studio Code** rewrites
`editor.fontFamily` and `editor.fontLigatures` in VS Code's user
`settings.json`. Builds install `<Family> Half` fonts into `~/Library/Fonts`,
and the `com.jorden.halfbold` launchd file watcher rebuilds Half fonts
whenever that folder changes. Nothing in the app undoes any of this. Today
the maintainer has to hand-edit two files, delete fonts in Finder, and run
`launchctl bootout`.

After this plan, a **Reset…** button in the status bar opens a small
confirmation strip:

- **Reset** puts VS Code's two settings and the three Slots back to the values
  they had *before halfbold first changed them*. Settings that did not exist
  before are removed.
- The **Also delete every Half font in ~/Library/Fonts and remove the file
  watcher** checkbox (off by default) also stops and deletes the watcher, and
  only then deletes every Half font. The order matters. If the watcher were
  still loaded, deleting the fonts would trigger `halfbold sync`, which
  rebuilds them within about 30 seconds.

The maintainer chose this scope on 2026-10-20: restore outside changes, and
also offer the full delete, removing (not just pausing) the watcher.

## Current state

Files and their roles:

- `src/halfbold/api.py`: `halfbold-api`, the JSON CLI the app drives. Each
  subcommand is an argparse subparser whose handler returns a dict, printed as
  JSON. A `ValueError`/`OSError`/`subprocess.SubprocessError` becomes
  `{"error": "..."}` with exit 1 (in `serve` mode, `{"ok": false, "error"}`).
  Module-level path constants are the testing seam. Example:
  `CACHE_DIR = default_cache_dir()` at `api.py:49`, monkeypatched in tests as
  `monkeypatch.setattr(api, "CACHE_DIR", cache_dir)` (`tests/test_api.py:53`).
- `src/halfbold/vscode.py`: in-place JSONC editing of VS Code `settings.json`
  (keeps comments). It has `tokens`, `value_end`, `top_level_values`,
  `set_setting`, `get_setting`, `use_in_vscode`. It has no way to *remove* a key yet.
- `src/halfbold/web.py`: `get_web_fonts(css_path) -> dict[Kind, str]` and
  `set_web_font(css_path, kind, family)` read and write the three
  `--halfbold-<kind>: "<family>";` lines in the extension CSS.
- `src/halfbold/scan.py`: `find_installed_half_families(fonts_dir)` finds Half
  fonts by reading each `*.ttf` family name (ends with ` Half`).
- `src/halfbold/settings.py`: `default_settings_path()` is
  `~/Library/Application Support/halfbold/settings.json` on macOS. The new
  originals file goes next to it.
- `scripts/install-watcher.sh`: installs the watcher as launchd label
  `com.jorden.halfbold`, plist `~/Library/LaunchAgents/com.jorden.halfbold.plist`.
  Its own removal hint is
  `launchctl bootout gui/$(id -u)/com.jorden.halfbold && rm $plist`.
- `app/src/api.ts`: typed wrappers. Each calls `api<T>(...args)`, which
  forwards to the long-lived `halfbold-api serve`. The Rust side passes any args
  through, so **no Rust change is needed**.
- `app/src/main.ts`: all UI logic (one file, ~890 lines). `run(label, task)`
  shows a status label, catches errors into the status bar and returns `null`
  on failure. `busy()` is true while any `run` is live. `showNote(msg)` writes a
  success note in the status bar.
- `app/index.html`, `app/src/styles.css`: markup and styles. Colours are
  tokens on `:root`, redefined under `@media (prefers-color-scheme: dark)`.

Important facts verified while planning:

- `api.DEFAULT_CSS` (from `cli.py:15`) is the **git-tracked**
  `chrome-extension/halfbold.css`. Slot changes edit that tracked file, so
  restoring Slots changes `git status` of the repo. That is expected.
- All Half fonts land in `~/Library/Fonts` (`scan.py:235` sets
  `output_dir=fonts_dir`), including those built from system fonts such as
  `Menlo-Half.ttf`.
- The watcher is loaded on the maintainer's machine (`launchctl list` shows
  `com.jorden.halfbold`).
- Tauri's webview does not give you a working `window.confirm()`. Use the
  inline strip in this plan, never `alert`/`confirm`.

Current code you will change (confirm it matches before editing):

`src/halfbold/api.py:304-321`:

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

`src/halfbold/scan.py:185-190`:

```python
def find_installed_half_families(fonts_dir: Path) -> set[str]:
    return {
        info.family
        for path in sorted(fonts_dir.glob("*.ttf"))
        if (info := read_font_info(path)) is not None and is_half_output(info)
    }
```

`app/src/main.ts:591-602` (inside `onUseAs`; you will extract the
`if` block into a helper):

```ts
  state.web = result.web;
  state.candidates = result.fonts.candidates;
  renderSlots();
  renderList();
  if (state.selected?.tab === "installed") {
    const family = state.selected.candidate.family;
    const updated = state.candidates.find((candidate) => candidate.family === family);
    if (updated) state.selected = { tab: "installed", candidate: updated };
    if (state.selected?.tab === "installed") renderInstalledActions(state.selected.candidate);
  }
  showNote(`${c.family} Half saved for browser ${kind === "mono" ? "code" : "text"}.`);
```

`app/index.html:91-94`:

```html
      <footer id="statusbar">
        <span id="status"></span>
        <span id="slots"></span>
      </footer>
```

Repo conventions (from `AGENTS.md` and the user's global rules, all enforced by
hooks):

- **No comments anywhere** in code (Python, TS, CSS, HTML), and no lint
  suppressions. Name things instead.
- Small single-purpose functions, clear names, YAGNI.
- TDD: write the failing test first, then the code.
- Conventional Commits (`feat:`, `fix:`, `docs:`). The `commit-msg` hook rejects
  anything else.
- Domain vocabulary from `CONTEXT.md`: **Slot** = "One of the Chrome
  extension's three roles, sans, serif or mono, each pointing at one installed
  Half font family." **Half font** = the converted output, family name plus
  ` Half`. Use these words in UI text and names.

## Commands you will need

| Purpose | Command (from repo root unless noted) | Expected on success |
|---|---|---|
| Python lint | `uv run ruff check .` | `All checks passed!` |
| Python format | `uv run ruff format --check .` (run `uv run ruff format .` first if you pasted code) | `N files already formatted`, exit 0 |
| Python tests | `uv run pytest -q` | all pass: **173** after this plan (160 before) |
| One test file | `uv run pytest -q tests/test_reset.py` | all pass |
| TS install | `cd app && bun install` | exit 0 |
| TS typecheck | `cd app && bunx tsc --noEmit -p .` | no output, exit 0 |
| TS tests | `cd app && bun test` | `8 pass`, 0 fail (4 before) |
| Fallow | `cd app && npx -y fallow --format json` | `check.total_issues` is **2**, same as before (pre-existing, leave them) |

## Scope

**In scope** (the only files you may modify or create):

- `src/halfbold/vscode.py`: add `remove_setting`
- `src/halfbold/reset.py` (create): record and restore originals
- `src/halfbold/watcher.py` (create): remove the launchd watcher
- `src/halfbold/scan.py`: add `find_installed_half_fonts`
- `src/halfbold/api.py`: record originals in `web`/`vscode`, new `reset` subcommand
- `tests/test_vscode.py`, `tests/test_api.py`: add tests
- `tests/test_reset.py`, `tests/test_watcher.py` (create)
- `app/src/api.ts`, `app/src/main.ts`, `app/index.html`, `app/src/styles.css`
- `app/src/reset.ts`, `app/src/reset.test.ts` (create)
- `README.md`, `CONTEXT.md`, `AGENTS.md`: one short addition each
- `plans/README.md`: your status row only

**Out of scope** (do NOT touch):

- `app/src-tauri/**`: the Rust bridge passes args through, so no change is needed.
- `src/halfbold/cli.py`: the CLI `--sans/--serif/--mono` flags do **not**
  record originals. The button undoes *app* changes, and the CLI is a separate
  tool.
- `chrome-extension/**`: do not edit the CSS by hand, and do not try to remove
  the Chrome extension. Chrome only allows that from `chrome://extensions`. The
  UI text tells the user instead.
- The existing tuning **Reset** (`#reset-tuning`) and **Reset sample text**
  buttons. They stay as they are.
- `~/Library/Caches/halfbold` (preview cache). It is invisible to the system
  and is left alone.
- Do not run the real reset, `launchctl`, or delete anything under `~/Library`
  while developing. Every test uses `tmp_path` and monkeypatching.

## Git workflow

- Branch: `advisor/020-reset-button`
- One commit per step group. Examples from `git log`:
  `feat: write the VS Code editor font into settings.json`,
  `feat: add a vscode halfbold-api subcommand`. Suggested messages:
  `feat: remove a key from VS Code settings.json`,
  `feat: record and restore the values the app changes`,
  `feat: add a reset halfbold-api subcommand`,
  `feat: add a Reset button to the app`,
  `docs: describe the Reset button`.
- End each commit message with the attribution line your operator gives you,
  if any.
- Do NOT push, merge or open a PR unless your operator tells you to.

## Steps

### Step 1: `remove_setting` in `vscode.py` (TDD)

First add these tests to `tests/test_vscode.py`. Extend the import to
`from halfbold.vscode import get_setting, remove_setting, set_setting, use_in_vscode`,
and insert the tests before `test_use_in_vscode_sets_family_and_turns_on_ligatures`.
`WITH_COMMENTS` already exists at the top of that file.

```python
def test_remove_setting_drops_a_middle_key_and_keeps_comments():
    text = remove_setting(WITH_COMMENTS, "editor.fontSize")

    assert "// Editor look" in text
    assert get_setting(text, "editor.fontSize") is None
    assert get_setting(text, "editor.fontFamily") == "Menlo, monospace"


def test_remove_setting_drops_the_last_key_and_its_comma():
    text = '{\n    "a": 1,\n    "b": 2\n}\n'

    assert remove_setting(text, "b") == '{\n    "a": 1\n}\n'


def test_remove_setting_drops_the_first_key():
    text = '{\n    "a": 1,\n    "b": 2\n}\n'

    assert remove_setting(text, "a") == '{\n    "b": 2\n}\n'


def test_remove_setting_empties_a_single_key_object():
    assert json.loads(remove_setting('{"a": [1, {"b": 2}]}', "a")) == {}


def test_remove_setting_ignores_a_missing_key():
    assert remove_setting(WITH_COMMENTS, "editor.tabSize") == WITH_COMMENTS
```

Run `uv run pytest -q tests/test_vscode.py`. It must fail with an ImportError.

Then add this to `src/halfbold/vscode.py`, directly above `def get_setting`.
It cuts the member from its key to its value. If a comma follows, the comma
goes too. Otherwise, the comma before it goes (it was the last member).
Whitespace before the key is trimmed, so no blank line is left, and comments
between members are kept.

```python
def remove_setting(text: str, key: str) -> str:
    _, values = top_level_values(text)
    if key not in values:
        return text
    items = tokens(text)
    value_index = next(
        i for i, item in enumerate(items) if item.start == values[key][0]
    )
    key_index = value_index - 2
    last = value_end(items, value_index)
    start = len(text[: items[key_index].start].rstrip())
    following = items[last + 1]
    if following.text == ",":
        return text[:start] + text[following.end :]
    preceding = items[key_index - 1]
    if preceding.text == ",":
        return (
            text[: preceding.start]
            + text[preceding.end : start]
            + text[items[last].end :]
        )
    return text[:start] + text[items[last].end :]
```

**Verify**: `uv run pytest -q tests/test_vscode.py` → 13 passed (8 before + 5).
`uv run ruff check . && uv run ruff format --check .` → clean.

### Step 2: `reset.py` records and restores originals (TDD)

"Originals" are the values a setting had before the app first changed it.
They are stored in `~/Library/Application Support/halfbold/originals.json`
as `{"vscode": {...}, "web": {...}}`. **Only the first recording per section
counts**, so using the buttons five times still restores the true original.
In the `vscode` section, `null` means "the key did not exist", and restoring
it removes the key.

Create `tests/test_reset.py`:

```python
import json
from pathlib import Path

from test_web import CSS

from halfbold.reset import (
    VSCODE,
    WEB,
    load_originals,
    remember,
    restore_originals,
    vscode_values,
)
from halfbold.web import get_web_fonts, set_web_font


def test_remember_keeps_the_first_values(tmp_path: Path):
    path = tmp_path / "halfbold" / "originals.json"

    remember(path, WEB, {"sans": "First Half"})
    remember(path, WEB, {"sans": "Second Half"})

    assert load_originals(path) == {WEB: {"sans": "First Half"}}


def test_vscode_values_reports_missing_keys_as_none(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"editor.fontFamily": "Menlo"}')

    assert vscode_values(settings) == {
        "editor.fontFamily": "Menlo",
        "editor.fontLigatures": None,
    }


def test_restore_puts_back_vscode_and_slots(tmp_path: Path):
    path = tmp_path / "originals.json"
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{\n    "editor.fontFamily": "Menlo",\n    "editor.tabSize": 2\n}\n'
    )
    remember(path, WEB, get_web_fonts(css))
    remember(path, VSCODE, vscode_values(settings))
    set_web_font(css, "sans", "Pair Half")
    settings.write_text(
        '{\n    "editor.fontFamily": "\'Pair Half\', monospace",\n'
        '    "editor.tabSize": 2,\n    "editor.fontLigatures": true\n}\n'
    )

    restored = restore_originals(path, css, settings)

    assert restored == [VSCODE, WEB]
    assert css.read_text() == CSS
    assert json.loads(settings.read_text()) == {
        "editor.fontFamily": "Menlo",
        "editor.tabSize": 2,
    }
    assert not path.exists()


def test_restore_without_originals_changes_nothing(tmp_path: Path):
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)

    restored = restore_originals(tmp_path / "originals.json", css, tmp_path / "s.json")

    assert restored == []
    assert css.read_text() == CSS
```

Run it. It must fail with ModuleNotFoundError. Then create
`src/halfbold/reset.py`:

```python
import json
from pathlib import Path

from halfbold.settings import default_settings_path
from halfbold.vscode import (
    FONT_FAMILY,
    FONT_LIGATURES,
    get_setting,
    remove_setting,
    set_setting,
)
from halfbold.web import set_web_font

VSCODE = "vscode"
WEB = "web"


def default_originals_path() -> Path:
    return default_settings_path().with_name("originals.json")


def load_originals(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def remember(path: Path, section: str, values: dict) -> None:
    originals = load_originals(path)
    if section in originals:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**originals, section: values}, indent=2) + "\n")


def vscode_values(settings_path: Path) -> dict:
    text = settings_path.read_text() if settings_path.exists() else "{}"
    return {key: get_setting(text, key) for key in (FONT_FAMILY, FONT_LIGATURES)}


def restore_vscode(settings_path: Path, values: dict) -> None:
    if not settings_path.exists():
        return
    text = settings_path.read_text()
    for key, value in values.items():
        if value is None:
            text = remove_setting(text, key)
        else:
            text = set_setting(text, key, value)
    settings_path.write_text(text)


def restore_web(css_path: Path, values: dict) -> None:
    for kind, family in values.items():
        set_web_font(css_path, kind, family)


def restore_originals(path: Path, css_path: Path, settings_path: Path) -> list[str]:
    originals = load_originals(path)
    if VSCODE in originals:
        restore_vscode(settings_path, originals[VSCODE])
    if WEB in originals:
        restore_web(css_path, originals[WEB])
    path.unlink(missing_ok=True)
    return sorted(originals)
```

**Verify**: `uv run pytest -q tests/test_reset.py` → 4 passed. Lint and format clean.

### Step 3: `watcher.py` removes the launchd agent (TDD)

Create `tests/test_watcher.py` (it follows the
`monkeypatch.setattr(brewcask.subprocess, "run", fake_run)` pattern from
`tests/test_brewcask.py:377`):

```python
from pathlib import Path

from halfbold import watcher
from halfbold.watcher import LABEL, remove_watcher


def test_remove_watcher_boots_out_and_deletes_the_plist(monkeypatch, tmp_path: Path):
    plist = tmp_path / f"{LABEL}.plist"
    plist.write_text("<plist/>")
    calls = []
    monkeypatch.setattr(watcher.subprocess, "run", lambda cmd, **_: calls.append(cmd))

    assert remove_watcher(plist) is True

    assert calls[0][:2] == ["launchctl", "bootout"]
    assert calls[0][2].endswith(f"/{LABEL}")
    assert not plist.exists()


def test_remove_watcher_without_plist_does_nothing(monkeypatch, tmp_path: Path):
    calls = []
    monkeypatch.setattr(watcher.subprocess, "run", lambda cmd, **_: calls.append(cmd))

    assert remove_watcher(tmp_path / f"{LABEL}.plist") is False
    assert calls == []
```

Then create `src/halfbold/watcher.py`. `check=False` is deliberate: `bootout`
exits non-zero when the agent is not loaded, and that is fine. The plist is
still deleted, so the watcher does not come back at the next login.

```python
import os
import subprocess
from pathlib import Path

LABEL = "com.jorden.halfbold"


def default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def remove_watcher(plist: Path) -> bool:
    if not plist.exists():
        return False
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        check=False,
    )
    plist.unlink()
    return True
```

**Verify**: `uv run pytest -q tests/test_watcher.py` → 2 passed. Lint and format clean.

### Step 4: `find_installed_half_fonts` in `scan.py`

Replace `find_installed_half_families` (`scan.py:185-190`) with these two
functions. The family set is derived from the new path → family map, so
there is one scan loop:

```python
def find_installed_half_fonts(fonts_dir: Path) -> dict[Path, str]:
    return {
        path: info.family
        for path in sorted(fonts_dir.glob("*.ttf"))
        if (info := read_font_info(path)) is not None and is_half_output(info)
    }


def find_installed_half_families(fonts_dir: Path) -> set[str]:
    return set(find_installed_half_fonts(fonts_dir).values())
```

**Verify**: `uv run pytest -q` → 171 passed (160 + the 11 tests from Steps 1-3;
no behaviour change for existing callers). Lint and format clean.

### Step 5: record originals and add `halfbold-api reset` (TDD)

**5a. Make every API test safe first.** In `tests/test_api.py`, directly after
the import block (after `from halfbold.settings import Settings`), add an
autouse fixture. Without it, the existing `web` and `vscode` tests would
write the maintainer's real `originals.json`, and a buggy reset test could
touch the real watcher plist:

```python
@pytest.fixture(autouse=True)
def isolated_reset_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "ORIGINALS_PATH", tmp_path / "originals.json")
    monkeypatch.setattr(api, "WATCHER_PLIST", tmp_path / "watcher.plist")
```

(`pytest`, `api`, `Path`, `fill_fonts_dir`, `build_all`, `CSS`, `json` and `main`
are already imported in that file.)

**5b. Append these two tests** to the end of `tests/test_api.py`. Half font
files are named `<stem>-Half.ttf`, so use globs and not exact filenames. The
second test proves the watcher is removed while the Half fonts still exist,
that is, *before* they are deleted.

```python
def test_reset_restores_slots_and_vscode(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    vscode_dir = tmp_path / "Code" / "User"
    vscode_dir.mkdir(parents=True)
    settings = vscode_dir / "settings.json"
    settings.write_text('{"editor.fontFamily": "Menlo"}')
    common = ["--fonts-dir", str(fonts)]
    main(["web", "sans", "Pair", "--css", str(css), *common])
    main(["vscode", "Pair", "--settings", str(settings), *common])
    capsys.readouterr()

    result = main(["reset", "--css", str(css), "--settings", str(settings), *common])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["restored"] == ["vscode", "web"]
    assert payload["web"]["sans"] == "Inter Half"
    assert payload["deleted"] == []
    assert json.loads(settings.read_text()) == {"editor.fontFamily": "Menlo"}
    assert list(fonts.glob("*-Half.ttf")) != []


def test_reset_delete_fonts_removes_watcher_then_half_fonts(
    monkeypatch, tmp_path: Path, capsys
):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    events = []

    def fake_remove_watcher(plist: Path) -> bool:
        events.append(("watcher", sorted(p.name for p in fonts.glob("*-Half.ttf"))))
        return True

    monkeypatch.setattr(api, "remove_watcher", fake_remove_watcher)

    result = main(
        [
            "reset",
            "--delete-fonts",
            "--css",
            str(css),
            "--settings",
            str(tmp_path / "settings.json"),
            "--fonts-dir",
            str(fonts),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["watcher_removed"] is True
    assert payload["deleted"] == ["Pair Half", "Var Half"]
    assert events[0][1] != []
    assert list(fonts.glob("*-Half.ttf")) == []
    assert (fonts / "Pair-Regular.ttf").exists()
```

Run `uv run pytest -q tests/test_api.py`. The two new tests fail and every
other test passes.

**5c. Implement in `src/halfbold/api.py`:**

1. Imports. Add these in ruff's sorted position (run
   `uv run ruff check --fix .` afterwards if I001 complains):
   ```python
   from halfbold.reset import (
       VSCODE,
       WEB,
       default_originals_path,
       remember,
       restore_originals,
       vscode_values,
   )
   ```
   Add `find_installed_half_fonts,` to the existing `from halfbold.scan import (...)`
   and add `from halfbold.watcher import default_plist_path, remove_watcher`.
2. Below `CACHE_DIR = default_cache_dir()` (line 49):
   ```python
   ORIGINALS_PATH = default_originals_path()
   WATCHER_PLIST = default_plist_path()
   ```
3. Replace `web` and `vscode` (lines 312-321) and add two functions after
   them. Each records the original **after** the family check passes and
   **before** the write:
   ```python
   def web(args: argparse.Namespace) -> dict:
       if args.kind:
           family = installed_half_family(args.family, args.fonts_dir)
           remember(ORIGINALS_PATH, WEB, get_web_fonts(args.css))
           set_web_font(args.css, args.kind, family)
       return get_web_fonts(args.css)


   def vscode(args: argparse.Namespace) -> dict:
       family = installed_half_family(args.family, args.fonts_dir)
       remember(ORIGINALS_PATH, VSCODE, vscode_values(args.settings))
       return use_in_vscode(args.settings, family)


   def delete_half_fonts(fonts_dir: Path) -> list[str]:
       fonts = find_installed_half_fonts(fonts_dir)
       for path in fonts:
           path.unlink()
       return sorted(set(fonts.values()))


   def reset(args: argparse.Namespace) -> dict:
       restored = restore_originals(ORIGINALS_PATH, args.css, args.settings)
       watcher_removed = args.delete_fonts and remove_watcher(WATCHER_PLIST)
       deleted = delete_half_fonts(args.fonts_dir) if args.delete_fonts else []
       return {
           "restored": restored,
           "deleted": deleted,
           "watcher_removed": watcher_removed,
           "web": get_web_fonts(args.css),
       }
   ```
   Do not reorder the `watcher_removed` and `deleted` lines (see "Why this matters").
4. In `parse_args`, directly before `browser_parser = subparsers.add_parser("browser")`:
   ```python
   reset_parser = subparsers.add_parser("reset")
   reset_parser.add_argument("--delete-fonts", action="store_true")
   reset_parser.add_argument("--css", type=Path, default=DEFAULT_CSS)
   reset_parser.add_argument("--settings", type=Path, default=default_settings_path())
   reset_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
   reset_parser.set_defaults(handler=reset)
   ```
   (`default_settings_path` here is the VS Code one, already imported from
   `halfbold.vscode` in `api.py`. Do not import the settings.py function of
   the same name into `api.py`.)

**Verify**: `uv run pytest -q` → **173 passed**. `uv run ruff check .` →
`All checks passed!`. `uv run ruff format --check .` → exit 0.
`ls ~/Library/Application\ Support/halfbold/originals.json` → "No such file"
(the tests did not touch the real file; if it exists and you did not create
it by using the app, STOP).

### Step 6: `resetSummary` and the `reset` wrapper in the app (TDD)

Add to `app/src/api.ts`, directly above `export function settings(`:

```ts
export interface ResetResult {
  restored: string[];
  deleted: string[];
  watcher_removed: boolean;
  web: WebFonts;
}

export function reset(deleteFonts: boolean) {
  return api<ResetResult>("reset", ...(deleteFonts ? ["--delete-fonts"] : []));
}
```

Create `app/src/reset.test.ts` (modelled on `app/src/sequence.test.ts`):

```ts
import { expect, test } from "bun:test";

import type { ResetResult } from "./api";
import { resetSummary } from "./reset";

const WEB = { sans: "Inter Half", serif: "Source Serif 4 Half", mono: "JetBrainsMono Nerd Font Half" };

function result(overrides: Partial<ResetResult>): ResetResult {
  return { restored: [], deleted: [], watcher_removed: false, web: WEB, ...overrides };
}

test("says when there is nothing to undo", () => {
  expect(resetSummary(result({}))).toBe("Nothing to undo.");
});

test("names each restored place", () => {
  expect(resetSummary(result({ restored: ["vscode", "web"] }))).toBe(
    "Visual Studio Code font restored. Chrome slots restored.",
  );
});

test("counts deleted fonts and points at the extension", () => {
  const summary = resetSummary(result({ deleted: ["Inter Half", "Menlo Half"], watcher_removed: true }));
  expect(summary).toStartWith("File watcher removed. 2 Half fonts deleted;");
  expect(summary).toContain("chrome://extensions");
});

test("uses the singular for one deleted font", () => {
  expect(resetSummary(result({ deleted: ["Inter Half"] }))).toStartWith("1 Half font deleted;");
});
```

Run `cd app && bun test`. It fails because `./reset` is missing. Then create
`app/src/reset.ts`. The extension hint exists because, once the fonts are
gone, the still-loaded extension forces pages onto the generic fallback font:

```ts
import type { ResetResult } from "./api";

const RESTORED_LABELS: Record<string, string> = {
  vscode: "Visual Studio Code font restored.",
  web: "Chrome slots restored.",
};

function deletedLabel(count: number): string {
  return `${count} Half ${count === 1 ? "font" : "fonts"} deleted; remove the halfbold extension in chrome://extensions to give pages their own fonts back.`;
}

export function resetSummary(result: ResetResult): string {
  const parts = result.restored.map((section) => RESTORED_LABELS[section] ?? `${section} restored.`);
  if (result.watcher_removed) parts.push("File watcher removed.");
  if (result.deleted.length > 0) parts.push(deletedLabel(result.deleted.length));
  return parts.length > 0 ? parts.join(" ") : "Nothing to undo.";
}
```

**Verify**: `cd app && bun test` → `8 pass`, `0 fail`.
`cd app && bunx tsc --noEmit -p .` → no output.

### Step 7: the Reset button and confirmation strip

**7a. `app/index.html`**: replace the footer (lines 91-94) with:

```html
      <section id="reset-panel" aria-label="Reset" hidden>
        <p>Put Visual Studio Code and the Chrome slots back the way they were before halfbold changed them?</p>
        <label class="reset-option">
          <input id="reset-delete-fonts" type="checkbox" />
          Also delete every Half font in ~/Library/Fonts and remove the file watcher
        </label>
        <div class="reset-buttons">
          <button id="reset-cancel" type="button">Cancel</button>
          <button id="reset-confirm" class="danger" type="button">Reset</button>
        </div>
      </section>
      <footer id="statusbar">
        <span id="status"></span>
        <span class="statusbar-end">
          <span id="slots"></span>
          <button id="reset-open" class="link" type="button">Reset…</button>
        </span>
      </footer>
```

`renderSlots` only writes inside `#slots`, so wrapping it is safe.

**7b. `app/src/styles.css`**:

- In the light `:root` block, add `  --danger: #c0392b;` after `--accent-fg: #ffffff;`.
- In the dark `:root` block, add `    --danger: #e0645a;` after `--accent-fg: #0f1120;`.
- Change `#status.error { color: #c0392b; }` to `color: var(--danger);`.
- Directly after that `#status.error` rule, add:

```css
.statusbar-end {
  display: flex;
  align-items: center;
  gap: 14px;
}

#statusbar button.link {
  font-size: 11px;
}

#reset-panel {
  padding: 12px 24px;
  border-top: 1px solid var(--hairline);
  font-size: 12px;
}

#reset-panel p { margin: 0 0 8px; }

.reset-option {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
}

.reset-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.reset-buttons button {
  padding: 4px 11px;
  border: 1px solid var(--control-border);
  border-radius: 6px;
  background: var(--control);
}

.reset-buttons button.danger {
  background: var(--danger);
  border-color: var(--danger);
  color: #ffffff;
}
```

Do not give `#reset-panel` a `display` rule. Its `hidden` attribute must keep working.

**7c. `app/src/main.ts`**:

1. In the `./api` import list, add `reset as resetApi,` after `preview,`
   (it mirrors `settings as settingsApi`). After the `./fonts` import, add
   `import { resetSummary } from "./reset";`.
2. After `const resetTuningEl = …` (line 89), add:
   ```ts
   const resetOpenEl = $<HTMLButtonElement>("#reset-open");
   const resetPanelEl = $<HTMLElement>("#reset-panel");
   const resetDeleteFontsEl = $<HTMLInputElement>("#reset-delete-fonts");
   const resetCancelEl = $<HTMLButtonElement>("#reset-cancel");
   const resetConfirmEl = $<HTMLButtonElement>("#reset-confirm");
   ```
3. Directly above `async function onUseAs`, add the extracted helper, and in
   `onUseAs` replace the five-line `if (state.selected?.tab === "installed") { … }`
   block (shown in "Current state") with `refreshSelectedActions();`:
   ```ts
   function refreshSelectedActions() {
     if (state.selected?.tab !== "installed") return;
     const family = state.selected.candidate.family;
     const updated = state.candidates.find((candidate) => candidate.family === family);
     if (updated) state.selected = { tab: "installed", candidate: updated };
     renderInstalledActions(state.selected.candidate);
   }
   ```
4. Directly above `const browserStatusEl = $("#browser-status");` (line 619), add:
   ```ts
   function closeResetPanel() {
     resetPanelEl.hidden = true;
     resetDeleteFontsEl.checked = false;
   }

   async function onReset() {
     if (busy()) return;
     const result = await run("Resetting…", () => resetApi(resetDeleteFontsEl.checked));
     if (!result) return;
     closeResetPanel();
     state.web = result.web;
     renderSlots();
     await reloadInstalled();
     refreshSelectedActions();
     showNote(resetSummary(result));
     scheduleBrowserCheck(0);
   }

   function setupReset() {
     resetOpenEl.addEventListener("click", () => {
       resetPanelEl.hidden = false;
     });
     resetCancelEl.addEventListener("click", closeResetPanel);
     resetConfirmEl.addEventListener("click", () => void onReset());
   }
   ```
5. In `init()`, add `setupReset();` right after `setupTuning();`.

On failure, `run` already shows the error in the status bar and the strip
stays open, so the user can retry or cancel. Do not add extra error handling.

**Verify**: `cd app && bunx tsc --noEmit -p .` → no output. `cd app && bun test`
→ `8 pass`. `cd app && npx -y fallow --format json` → `check.total_issues`
is 2. `grep -n "confirm(\|alert(" app/src/main.ts` → no matches.

### Step 8: docs

- `README.md`: after the VS Code paragraph in `## App` (it ends "…to pick up a
  newly installed font."), add a paragraph:
  > **Reset…** in the status bar puts Visual Studio Code's font settings and
  > the Chrome slots back to how they were before the app first changed them.
  > Tick **Also delete every Half font** to also stop and remove the file
  > watcher and delete every Half font in `~/Library/Fonts`. Re-run
  > `scripts/install-watcher.sh` to get the watcher back.

  In the `halfbold-api` subcommand list (README line ~187, which reads
  `` …`settings`, `web`, `vscode`. Each prints one JSON object… ``), change
  `` `web`, `vscode`. `` to `` `web`, `vscode`, `reset`. ``.
- `CONTEXT.md`: after the **Slot** entry, add:
  > **Originals**:
  > The Visual Studio Code font settings and Slot values recorded the first time the app changes them, so Reset can put them back.
  > _Avoid_: backup, snapshot
- `AGENTS.md`, `## Automation`, first bullet (the watcher): append the
  sentence "The app's Reset with **Also delete every Half font** boots the
  watcher out and deletes its plist before deleting the fonts."

**Verify**: `grep -c "Reset…" README.md` → ≥1. `grep -c "^\*\*Originals\*\*" CONTEXT.md`
→ 1. `grep -c "boots the watcher out" AGENTS.md` → 1.

### Step 9: manual check in the real app (operator or maintainer only)

This step changes real VS Code settings, the tracked extension CSS and
(optionally) real fonts. Do it only if your operator allows it. Otherwise,
report "manual GUI check pending".

1. Back up: `cp ~/Library/Application\ Support/Code/User/settings.json /tmp/vscode-settings.bak`
   and note `git diff --stat chrome-extension/halfbold.css` (should be empty).
2. `uv run halfbold desktop`. Select a mono font and click **Use in Visual
   Studio Code**. Then open **Choose slot** and click **Use as sans**.
3. `cat ~/Library/Application\ Support/halfbold/originals.json` shows `vscode` and `web` sections.
4. Click **Reset…**. The strip appears. Click **Cancel**. The strip hides
   and nothing changes.
5. Click **Reset…** → **Reset** (checkbox off). The status bar reads
   `Visual Studio Code font restored. Chrome slots restored.`.
   `diff /tmp/vscode-settings.bak ~/Library/Application\ Support/Code/User/settings.json`
   is empty. `git diff --stat chrome-extension/halfbold.css` is empty. The
   footer slots show the original families.
6. Click **Reset…** → **Reset** again. The status bar reads `Nothing to undo.`.
7. The delete option is destructive. Run it only with the maintainer's
   explicit OK: tick the checkbox → **Reset**. Then
   `launchctl list | grep halfbold` prints nothing,
   `ls ~/Library/LaunchAgents | grep halfbold` prints nothing, and
   `ls ~/Library/Fonts | grep -- -Half` prints nothing, and still prints
   nothing 60 seconds later. Restore with `scripts/install-watcher.sh` (its
   `RunAtLoad` rebuilds the Half fonts).
8. Dark mode: switch macOS to dark. The strip and the red **Reset** button stay legible.

## Test plan

- `tests/test_vscode.py` (+5): remove a middle key and keep comments; the
  last key and its preceding comma; the first key and its following comma; a
  single-key object with a nested value; a missing key is a no-op.
- `tests/test_reset.py` (new, 4): first recording wins; missing VS Code keys
  record as `None`; full restore of VS Code (value restored, added key
  removed, unrelated key kept) and Slots, and the originals file is deleted;
  restore with no originals is a no-op.
- `tests/test_watcher.py` (new, 2): bootout and plist delete; no plist means
  no `launchctl` call.
- `tests/test_api.py` (+2, plus the autouse isolation fixture): end-to-end
  `web` + `vscode` + `reset` without deleting; `reset --delete-fonts` removes
  the watcher while the fonts still exist, then deletes only Half fonts.
- `app/src/reset.test.ts` (new, 4): the summary text for nothing, restored
  places, deleted plural, and deleted singular.
- Totals: `uv run pytest -q` → 173 passed (160 + 13). `cd app && bun test` → 8 pass.

## Done criteria

ALL must hold:

- [ ] `uv run ruff check .` → `All checks passed!`
- [ ] `uv run ruff format --check .` → exit 0
- [ ] `uv run pytest -q` → 173 passed, 0 failed
- [ ] `cd app && bunx tsc --noEmit -p .` → exit 0, no output
- [ ] `cd app && bun test` → 8 pass, 0 fail
- [ ] `cd app && npx -y fallow --format json` → `check.total_issues` == 2
- [ ] `uv run halfbold-api reset --help` lists `--delete-fonts`, `--css`, `--settings`, `--fonts-dir`
- [ ] `grep -n "confirm(\|alert(" app/src/main.ts` → no matches
- [ ] `git status --short` shows only in-scope files
- [ ] `plans/README.md` row 020 updated (Step 9 result or "manual GUI check pending")

## STOP conditions

Stop and report back (do not improvise) if:

- Any "Current state" excerpt does not match the live code.
- `~/Library/Application Support/halfbold/originals.json` or
  `~/Library/LaunchAgents/com.jorden.halfbold.plist` changes, or a file in
  `~/Library/Fonts` disappears, while you run the automated tests. That means
  a test escaped isolation.
- `remove_setting` cannot pass all five Step 1 tests after two honest
  attempts. Do not swap in a regex or `json.loads`/`json.dumps` round trip.
  That would strip the user's comments, which plan 019 explicitly protects.
- Making the watcher-before-fonts test pass seems to need a different order
  in `reset`, or a sleep.
- The app's Rust side turns out to reject the new `reset` command (for example,
  an allowlist appears in `app/src-tauri/src/lib.rs`).
- You feel the need to change `cli.py`, `chrome-extension/**` or the existing
  tuning Reset.

## Maintenance notes

- **Originals only exist for changes made after this lands.** Changes the
  maintainer made before (for example, the VS Code font set with plan 019's
  button earlier) were never recorded. Reset reports `Nothing to undo.` for
  them, and they must be fixed by hand once.
- Restoring deletes `originals.json`, so the *next* button use records a new
  original. That is intended: after a reset, the current state is the new
  baseline.
- If a future button changes another outside setting (another editor, a
  terminal config), give it its own section in `reset.py` with
  `remember(...)` before the write and a branch in `restore_originals`, plus a
  label in `RESTORED_LABELS` in `app/src/reset.ts`.
- `api.DEFAULT_CSS` is the tracked repo file, so a reset can create or clear
  a `git diff` on `chrome-extension/halfbold.css`. If the CSS ever moves to
  Application Support, nothing here changes, because `--css` is passed through.
- Reviewers: check the order in `api.reset` (watcher before fonts). Check that
  `remember` runs after `installed_half_family` validates the family, so a
  failed request records nothing misleading. Check the autouse fixture in
  `tests/test_api.py`.
- Deferred on purpose: the CLI `--sans/--serif/--mono` flags do not record
  originals. The app cannot remove the Chrome extension, and the UI tells the
  user to do it. Deleted fonts are not restorable except by rebuilding.
