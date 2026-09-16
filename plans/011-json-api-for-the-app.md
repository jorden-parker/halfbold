# Plan 011: Expose font scanning, preview builds, Homebrew search/install and slot switching as a JSON command (`halfbold-api`) for the desktop app

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7b9c258..HEAD -- src/halfbold/ tests/ pyproject.toml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (additive Python: one new module, one new console script, three small helper functions; no existing behaviour changes)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `7b9c258`, 2026-09-16

## Why this matters

The maintainer wants a small desktop app (plan 012, Tauri) that replaces the
terminal picker: search Homebrew font casks, install them, convert fonts to
their half-bold twins, and — the real point — *see* every font rendered
before and after conversion. A webview renders real fonts with `calt`
applied, which the terminal preview (`--preview`, Pillow + kitty graphics)
can only simulate.

The app needs a stable, machine-readable way to drive the Python engine.
Today every capability is either printed as prose by `halfbold` (`cli.py`)
or lives only in the Go TUI (`tui/brew.go`: cask search and install). This
plan adds one console script, `halfbold-api`, whose subcommands print exactly
one JSON document to stdout. Plan 012's Rust side shells out to it. Nothing
in the existing CLI, TUI or extension changes.

## Current state

### Repo facts

- Python 3.14 project managed by `uv`; package in `src/halfbold/`; tests in
  `tests/` (pytest, fixtures in `tests/conftest.py`).
- Conventions from `AGENTS.md`: **no code comments** (ruff `ERA` rejects
  commented-out code; name things well instead); Conventional Commits
  (`feat:`, `fix:`, `chore:`); after any change run
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` and
  fix everything reported. Only TrueType (`glyf`) fonts are supported.
- Ruff config (`pyproject.toml`): line length 88, rules `E F I UP B SIM ERA`,
  target `py314`. Imports are sorted by ruff `I` — run `uv run ruff format .`
  and `uv run ruff check --fix .` before committing.
- No `CONTEXT.md` or `docs/adr/` exist. Nothing to honor there.

### Files that matter

- `pyproject.toml` — one console script today:
  ```toml
  [project.scripts]
  halfbold = "halfbold.cli:main"
  ```
- `src/halfbold/scan.py` — `Candidate` (family, regular, bold, kind; `.output`
  property = `<FamilyNoSpaces>-Half.ttf` next to the regular; `.is_stale()`),
  `read_font_info`, `find_candidates(fonts_dir)`,
  `candidates_from_paths(paths)`, `KINDS = ("sans", "serif", "mono")`,
  `Kind` Literal.
- `src/halfbold/build.py` — `build_halfbold_font(regular, bold, output, ...)`
  returns the list of bolded letter glyph names; `STYLE_SUFFIX = "Half"`.
- `src/halfbold/preview.py` — terminal preview. Its `preview_files` (lines
  195–205) shows how a single file (plus optional bold) becomes a `Candidate`:
  ```python
  def preview_files(
      regular: Path, bold: Path | None, *, png: Path | None, wait: bool
  ) -> list[str]:
      info = read_font_info(regular)
      if info is None:
          raise ValueError(f"{regular} is not a TrueType font")
      family = " ".join(p for p in info.family.split() if p != "Variable")
      candidate = Candidate(family, regular, bold, info.kind)
      return preview_images([candidate], png=png, wait=wait)
  ```
  **Do not modify `preview.py`**; copy the three lines that build the
  candidate into the new module.
- `src/halfbold/brewcask.py` — `CaskInfo` dataclass (token, url, branch,
  only_path, fonts), `parse_cask_info(bytes)`, `cask_info(token)` (runs
  `brew info --cask --json=v2 TOKEN`), `cask_font_dir(token, into)` which
  downloads/extracts a cask's TTFs into `into` without installing.
  `parse_cask_info` today (lines 25–40):
  ```python
  def parse_cask_info(data: bytes) -> CaskInfo:
      payload = json.loads(data)
      casks = payload.get("casks") or []
      if not casks:
          raise ValueError("brew info returned no cask")
      cask = casks[0]
      url_specs = cask.get("url_specs") or {}
      fonts = [a["font"][0] for a in cask.get("artifacts", []) if "font" in a]
      return CaskInfo(
          token=cask["token"],
          url=cask.get("url", ""),
          branch=url_specs.get("branch", ""),
          only_path=url_specs.get("only_path", ""),
          fonts=fonts,
      )
  ```
  The subprocess error pattern used throughout the file:
  ```python
  except subprocess.CalledProcessError as err:
      stderr = err.stderr.decode() if err.stderr else str(err)
      raise ValueError(f"brew info failed: {stderr.strip()}") from err
  ```
- `src/halfbold/web.py` — `set_web_font(css_path, kind, family)` rewrites the
  `--halfbold-<kind>: "…";` line in `chrome-extension/halfbold.css` and
  returns `f"{kind:<6} {family}"`. The CSS head it edits:
  ```css
  :root {
    --halfbold-sans: "Inter Half";
    --halfbold-serif: "Source Serif 4 Half";
    --halfbold-mono: "JetBrainsMono Nerd Font Half";
  }
  ```
- `src/halfbold/cli.py` — `DEFAULT_FONTS_DIR = Path.home() / "Library" / "Fonts"`
  and `DEFAULT_CSS = Path(__file__).resolve().parents[2] / "chrome-extension" / "halfbold.css"`.
  Import both from here; do not redefine them.
- Go TUI reference for the install flow you are porting (`tui/brew.go`
  lines 53–74): after `brew install --cask TOKEN` it runs `brew info` and maps
  each font artifact to its installed path — the artifact's `target` when
  present, else `<fontsDir>/<basename of font>`:
  ```go
  for _, a := range info.Casks[0].Artifacts {
      if len(a.Font) == 0 { continue }
      if a.Target != "" { paths = append(paths, a.Target); continue }
      paths = append(paths, filepath.Join(fontsDir, filepath.Base(a.Font[0])))
  }
  ```
  and its search (`tui/brew.go` lines 17–19, 31–43): `brew search --cask font-`,
  keep non-empty trimmed lines that start with `font-`.

### Test conventions

- `tests/conftest.py` provides `make_font(path, family, style, stem)`,
  `make_variable_font(path, family)`, and fixtures `font_pair`,
  `variable_font`.
- `tests/test_scan.py::fill_fonts_dir(fonts_dir)` creates a folder with a
  Pair (Regular+Bold+Italic), a Lonely Regular and a `Var Variable` variable
  font. Reuse it (`from test_scan import fill_fonts_dir`, as `test_web.py`
  does).
- `tests/test_brewcask.py` fakes `brew` by monkeypatching
  `subprocess.run` / module functions; model the brew tests on it.
- CLI tests call `main([...])` and read `capsys.readouterr().out`.

## Commands you will need

| Purpose   | Command                           | Expected on success |
|-----------|-----------------------------------|---------------------|
| Install   | `uv sync`                         | exit 0              |
| Tests     | `uv run pytest -q`                | all pass            |
| Lint      | `uv run ruff check .`             | exit 0, "All checks passed!" |
| Format    | `uv run ruff format --check .`    | exit 0              |
| Smoke     | `uv run halfbold-api installed`   | one JSON object on stdout |

## Scope

**In scope** (the only files you should modify):
- `src/halfbold/api.py` (create)
- `src/halfbold/brewcask.py` (add `targets` to `CaskInfo`, add
  `search_font_casks`, `install_cask`, `installed_font_paths`)
- `src/halfbold/web.py` (add `get_web_fonts`)
- `pyproject.toml` (add the `halfbold-api` script)
- `tests/test_api.py` (create)
- `tests/test_brewcask.py`, `tests/test_web.py` (add tests for the new helpers)
- `README.md` (one short paragraph under "Develop")

**Out of scope** (do NOT touch, even though they look related):
- `src/halfbold/cli.py`, `src/halfbold/preview.py`, `src/halfbold/scan.py`,
  `src/halfbold/build.py` — the app consumes them; plan 013 decides what to
  retire.
- `tui/` — untouched; plan 013 removes it.
- `chrome-extension/` — only ever edited through `set_web_font`.
- `uv.lock` beyond what `uv sync` regenerates for the new script (no new
  dependencies are added by this plan).

## Git workflow

- Branch: `advisor/011-json-api`
- Conventional Commits, e.g. `feat: add halfbold-api JSON command for the desktop app`
  (matching `feat: preview a Homebrew font cask in the terminal` in `git log`).
- Do NOT push or open a PR unless the operator instructed it.

## The contract (read before Step 1)

`halfbold-api <subcommand> [args]` prints **exactly one JSON object** to
stdout and exits 0. On any handled failure it prints `{"error": "<message>"}`
to stdout and exits 1. Nothing else ever goes to stdout (uv's own chatter
goes to stderr, which is fine).

A **candidate object** (used by several subcommands) is:

```json
{
  "family": "Inter",
  "kind": "sans",
  "regular": "/Users/x/Library/Fonts/InterVariable.ttf",
  "bold": null,
  "output": "/Users/x/Library/Fonts/Inter-Half.ttf",
  "built": true,
  "stale": false
}
```

`bold` is a path string for a Regular+Bold pair and `null` for a variable
font. `output` is `Candidate.output`; `built` is `output.exists()`; `stale` is
`Candidate.is_stale()`.

Subcommands:

| Subcommand | Args | Result |
|---|---|---|
| `installed` | `--fonts-dir DIR` (default `DEFAULT_FONTS_DIR`) | `{"fonts_dir": "...", "candidates": [candidate…]}` from `find_candidates` |
| `build` | `REGULAR [BOLD] [-o OUTPUT]` | builds the Half font; `{"output": "...", "letters": 52}` (default output = `<regular stem>-Half.ttf` next to the input, same rule as `cli.py`) |
| `preview` | `REGULAR [BOLD]` | builds (or reuses) a Half font in the cache dir; `{"family", "kind", "regular", "bold", "half"}` where `half` is the cached `-Half.ttf` path |
| `casks` | none | `{"casks": ["font-abril-fatface", …]}` from `brew search --cask font-` |
| `cask-fonts` | `TOKEN` | downloads the cask without installing (`cask_font_dir`) into `<cache>/casks/<TOKEN>/`; `{"token": "...", "candidates": [candidate…]}` |
| `cask-install` | `TOKEN --fonts-dir DIR` | `brew install --cask TOKEN`; `{"token": "...", "candidates": [candidate…]}` for the fonts it installed |
| `web` | `[KIND FAMILY] --css PATH --fonts-dir DIR` | with KIND+FAMILY first sets the slot (same "Half" suffix and installed-check rule as `cli.py` lines 158–169); always returns `{"sans": "Inter Half", "serif": "...", "mono": "..."}` read back from the CSS |

Cache dir: `Path(tempfile.gettempdir()) / "halfbold-app"` (constant
`CACHE_DIR`). `preview` writes `<CACHE_DIR>/<FamilyNoSpaces>-Half.ttf` and
skips the build when that file is newer than every source file. Preview
builds never write into the fonts folder.

## Steps

### Step 1: Add `get_web_fonts` to `web.py`

Append to `src/halfbold/web.py`:

```python
def get_web_fonts(css_path: Path) -> dict[Kind, str]:
    text = css_path.read_text()
    fonts: dict[Kind, str] = {}
    for kind in KINDS:
        match = re.search(rf'^\s*--halfbold-{kind}:\s*"([^"]*)";$', text, re.MULTILINE)
        if match is None:
            raise ValueError(f"{css_path} has no --halfbold-{kind} line")
        fonts[kind] = match.group(1)
    return fonts
```

Import `KINDS` alongside `Kind` from `halfbold.scan`.

Add to `tests/test_web.py`:

```python
def test_get_web_fonts_reads_all_slots(tmp_path: Path):
    css_path = tmp_path / "halfbold.css"
    css_path.write_text(CSS)

    assert get_web_fonts(css_path) == {
        "sans": "Inter Half",
        "serif": "Source Serif 4 Half",
        "mono": "JetBrainsMono Nerd Font Half",
    }
```

and a `test_get_web_fonts_missing_line_raises` using the `incomplete_css`
string already in that file (expect `pytest.raises(ValueError)`).

**Verify**: `uv run pytest -q tests/test_web.py` → all pass (2 new).

### Step 2: Extend `brewcask.py` with search, install and installed paths

1. Add `targets: list[str]` as the last field of `CaskInfo` and fill it in
   `parse_cask_info`:
   ```python
   artifacts = [a for a in cask.get("artifacts", []) if "font" in a]
   fonts = [a["font"][0] for a in artifacts]
   targets = [a.get("target", "") for a in artifacts]
   ```
   Update every `CaskInfo(...)` construction in `tests/test_brewcask.py`
   to pass `targets=[]` (or the right list) — search the file for
   `CaskInfo(` first.
2. Add:
   ```python
   FONT_CASK_PREFIX = "font-"


   def search_font_casks() -> list[str]:
       try:
           result = subprocess.run(
               ["brew", "search", "--cask", FONT_CASK_PREFIX],
               capture_output=True,
               check=True,
           )
       except subprocess.CalledProcessError as err:
           stderr = err.stderr.decode() if err.stderr else str(err)
           raise ValueError(f"brew search failed: {stderr.strip()}") from err
       return parse_font_cask_tokens(result.stdout.decode())


   def parse_font_cask_tokens(text: str) -> list[str]:
       tokens = [line.strip() for line in text.splitlines()]
       return [t for t in tokens if t.startswith(FONT_CASK_PREFIX)]


   def install_cask(token: str) -> None:
       try:
           subprocess.run(
               ["brew", "install", "--cask", token],
               capture_output=True,
               check=True,
           )
       except subprocess.CalledProcessError as err:
           stderr = err.stderr.decode() if err.stderr else str(err)
           raise ValueError(f"brew install failed: {stderr.strip()}") from err


   def installed_font_paths(info: CaskInfo, fonts_dir: Path) -> list[Path]:
       paths = []
       for font, target in zip(info.fonts, info.targets, strict=True):
           path = Path(target) if target else fonts_dir / Path(font).name
           if path.exists():
               paths.append(path)
       return paths
   ```
3. Tests in `tests/test_brewcask.py`:
   - `test_parse_font_cask_tokens_keeps_only_font_prefix`: input
     `"==> Casks\nfont-roboto\n  font-inter \nnot-a-font\n\n"` → `["font-roboto", "font-inter"]`.
   - `test_parse_cask_info_targets`: `ROBOTO_JSON` now yields
     `info.targets == ["/Users/x/Library/Fonts/Roboto[wdth,wght].ttf"]`.
   - `test_installed_font_paths_falls_back_to_fonts_dir(tmp_path)`: a
     `CaskInfo` with `fonts=["A.ttf", "B.ttf"]`, `targets=["", str(tmp_path / "sub" / "B.ttf")]`;
     create both files; expect both paths returned; delete `A.ttf` → only B.
   - `test_search_font_casks_reports_brew_failure(monkeypatch)`: monkeypatch
     `brewcask.subprocess.run` to raise `CalledProcessError(1, "brew", stderr=b"boom")`;
     expect `ValueError` matching `brew search failed: boom`.

**Verify**: `uv run pytest -q tests/test_brewcask.py` → all pass.

### Step 3: Create `src/halfbold/api.py`

Structure (argparse subparsers; each handler returns a dict; `main` prints
it):

```python
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTLibError

from halfbold.brewcask import (
    cask_font_dir,
    cask_info,
    install_cask,
    installed_font_paths,
    search_font_casks,
)
from halfbold.build import STYLE_SUFFIX, build_halfbold_font
from halfbold.cli import DEFAULT_CSS, DEFAULT_FONTS_DIR
from halfbold.scan import (
    KINDS,
    Candidate,
    candidates_from_paths,
    find_candidates,
    find_installed_half_families,
    read_font_info,
)
from halfbold.web import get_web_fonts, set_web_font

CACHE_DIR = Path(tempfile.gettempdir()) / "halfbold-app"


def candidate_payload(candidate: Candidate) -> dict:
    return {
        "family": candidate.family,
        "kind": candidate.kind,
        "regular": str(candidate.regular),
        "bold": None if candidate.bold is None else str(candidate.bold),
        "output": str(candidate.output),
        "built": candidate.output.exists(),
        "stale": candidate.is_stale(),
    }


def candidate_from_files(regular: Path, bold: Path | None) -> Candidate:
    info = read_font_info(regular)
    if info is None:
        raise ValueError(f"{regular} is not a TrueType font")
    family = " ".join(p for p in info.family.split() if p != "Variable")
    return Candidate(family, regular, bold, info.kind)


def preview_half(candidate: Candidate, cache_dir: Path | None = None) -> Path:
    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    half = cache_dir / candidate.output.name
    if half.exists():
        built = half.stat().st_mtime
        if all(p.stat().st_mtime <= built for p in candidate.sources):
            return half
    build_halfbold_font(candidate.regular, candidate.bold, half)
    return half
```

Handlers (each takes the parsed `args` namespace):

- `installed(args)`: `{"fonts_dir": str(args.fonts_dir), "candidates": [candidate_payload(c) for c in find_candidates(args.fonts_dir)]}`.
- `build(args)`: `output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")`;
  `letters = build_halfbold_font(args.regular, args.bold, output)`;
  return `{"output": str(output), "letters": len(letters)}`.
- `preview(args)`: `c = candidate_from_files(args.regular, args.bold)`;
  return `{"family": c.family, "kind": c.kind, "regular": str(c.regular), "bold": …, "half": str(preview_half(c))}`.
- `casks(args)`: `{"casks": search_font_casks()}`.
- `cask_fonts(args)`: `into = CACHE_DIR / "casks" / args.token`;
  `shutil.rmtree(into, ignore_errors=True)`; `into.mkdir(parents=True)`;
  `cask_font_dir(args.token, into)`;
  `cands = candidates_from_paths(sorted(into.rglob("*.ttf")))`; if empty
  raise `ValueError(f"no Regular + Bold pair or variable TrueType font in {args.token}")`;
  return `{"token": args.token, "candidates": [...]}`.
- `cask_install(args)`: `install_cask(args.token)`;
  `paths = installed_font_paths(cask_info(args.token), args.fonts_dir)`;
  return `{"token": args.token, "candidates": [candidate_payload(c) for c in candidates_from_paths(paths)]}`.
- `web(args)`: if `args.kind`:
  ```python
  family = args.family
  if not family.endswith(f" {STYLE_SUFFIX}"):
      family = f"{family} {STYLE_SUFFIX}"
  ```
  then if `family not in find_installed_half_families(args.fonts_dir)` raise
  `ValueError(f"{family!r} is not installed in {args.fonts_dir}")`;
  `set_web_font(args.css, args.kind, family)`. Always return
  `get_web_fonts(args.css)`.

Parser: `argparse.ArgumentParser(prog="halfbold-api")`, `subparsers =
parser.add_subparsers(dest="command", required=True)`; every subparser gets
`set_defaults(handler=<function>)`. `web` takes `kind` and `family` as
`nargs="?"` positionals (`kind` restricted with `choices=KINDS`); reject
`kind` without `family` via `parser.error`. `--fonts-dir` (default
`DEFAULT_FONTS_DIR`, `type=Path`) on `installed`, `cask-install`, `web`;
`--css` (default `DEFAULT_CSS`, `type=Path`) on `web`; `-o/--output`
(`type=Path`) on `build`; `regular`/`bold` positionals `type=Path`, `bold`
with `nargs="?"`.

```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = args.handler(args)
    except (ValueError, TTLibError, OSError) as err:
        print(json.dumps({"error": str(err)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Subcommand names use hyphens on the command line (`cask-fonts`,
`cask-install`); handler functions use underscores.

**Verify**: `uv run ruff check . && uv run ruff format --check .` → exit 0.

### Step 4: Register the console script

In `pyproject.toml`:

```toml
[project.scripts]
halfbold = "halfbold.cli:main"
halfbold-api = "halfbold.api:main"
```

Run `uv sync`.

**Verify**: `uv run halfbold-api installed | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['candidates']), 'candidates')"`
→ prints a count and exits 0 (the count depends on the machine; 0 is fine on
a machine without fonts). `uv run halfbold-api web` → one JSON object with
`sans`, `serif`, `mono` keys.

### Step 5: Tests for `api.py`

Create `tests/test_api.py`, calling `main([...])` and parsing
`capsys.readouterr().out` with `json.loads`. Cases:

1. `test_installed_lists_candidates_with_flags(tmp_path, capsys)`:
   `fill_fonts_dir(tmp_path / "fonts")`; `main(["installed", "--fonts-dir", …]) == 0`;
   families are `["Pair", "Var"]` (sorted); every candidate has
   `built is False` and `stale is True`; `Var` has `bold is None`.
2. `test_build_writes_half_font(font_pair, tmp_path, capsys)`: run `build`
   with `-o tmp_path/"Out-Half.ttf"`; exit 0; the file exists; `letters == 26`.
3. `test_preview_caches_half_in_cache_dir(font_pair, tmp_path, capsys, monkeypatch)`:
   `monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")` — note
   `preview_half` must read the module attribute at call time for this to
   work, so pass `cache_dir=CACHE_DIR` **not** as a default parameter value
   evaluated at import; use `cache_dir: Path | None = None` and resolve
   `cache_dir or CACHE_DIR` inside the function. Run `preview` twice; the
   returned `half` path exists under the cache dir and its mtime is
   unchanged between runs (`os.stat` before/after); then `os.utime` the
   regular source to the future and run again → mtime changes.
4. `test_preview_rejects_non_font(tmp_path, capsys)`: a `.ttf` file
   containing `b"nope"`; exit 1; output is `{"error": …}` containing
   "not a TrueType font".
5. `test_cask_fonts_downloads_into_cache(monkeypatch, tmp_path, capsys)`:
   monkeypatch `api.CACHE_DIR` and `api.cask_font_dir` with a fake that
   writes a `make_font` pair into `into`; result has one candidate `Test`.
6. `test_cask_install_returns_installed_candidates(monkeypatch, tmp_path, capsys)`:
   monkeypatch `api.install_cask` to a no-op recorder, `api.cask_info` to
   return a `CaskInfo` whose fonts/targets point at a pair created with
   `make_font` inside `tmp_path`; expect the pair as one candidate and the
   recorder called with the token.
7. `test_web_sets_slot_and_reads_back(tmp_path, capsys)`: write the CSS from
   `test_web.CSS` to `tmp_path/"halfbold.css"`; `fill_fonts_dir`; run
   `build_all(fonts_dir)` (from `halfbold.scan`) so `Pair Half` exists; run
   `web serif Pair --css … --fonts-dir …` → exit 0 and `serif == "Pair Half"`;
   run `web serif Nope …` → exit 1 with `error` mentioning `Nope Half`.
8. `test_casks_reports_brew_failure(monkeypatch, capsys)`: monkeypatch
   `api.search_font_casks` to raise `ValueError("brew search failed: x")`;
   exit 1; `error == "brew search failed: x"`.

**Verify**: `uv run pytest -q` → all pass (8 new in `test_api.py`).

### Step 6: README note

Under `## Develop` in `README.md`, after the command block, add one
paragraph:

> `uv run halfbold-api <subcommand>` is the JSON interface the desktop app
> (`app/`) drives: `installed`, `build`, `preview`, `casks`, `cask-fonts`,
> `cask-install`, `web`. Each prints one JSON object; failures print
> `{"error": …}` and exit 1.

**Verify**: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → exit 0.

## Test plan

Covered in Steps 1, 2 and 5. Pattern files: `tests/test_web.py` (CSS
fixture), `tests/test_brewcask.py` (brew fakes), `tests/test_scan.py`
(`fill_fonts_dir`, CLI `main` + `capsys`).

## Done criteria

- [ ] `uv run pytest -q` exits 0 with the new tests in `tests/test_api.py`,
      `tests/test_brewcask.py`, `tests/test_web.py` passing
- [ ] `uv run ruff check .` and `uv run ruff format --check .` exit 0
- [ ] `uv run halfbold-api web` prints one JSON object with keys `sans`,
      `serif`, `mono` and exits 0
- [ ] `uv run halfbold-api preview /nonexistent.ttf` prints `{"error": …}`
      and exits 1 (no traceback)
- [ ] `git diff --stat main -- src/halfbold/cli.py src/halfbold/preview.py src/halfbold/scan.py src/halfbold/build.py tui/ chrome-extension/` is empty
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The excerpts in "Current state" do not match the live code.
- `uv sync` fails or `halfbold-api` is not on the path after Step 4.
- `parse_cask_info` cannot be extended with `targets` without breaking an
  existing test in a way the listed edit doesn't cover.
- You feel the need to modify `cli.py`, `preview.py` or `tui/` — that is
  plan 013's job.

## Maintenance notes

- The JSON shapes above are the contract with `app/src/api.ts` (plan 012).
  Any rename here must be mirrored there.
- `preview_half` caches by mtime in the OS temp dir; macOS clears
  `$TMPDIR` on reboot, which is the intended lifetime.
- `cask-install` relies on `brew info` reporting `target`; the Go TUI used
  the same assumption, so behaviour matches.
- Deferred: a `--json` flag on the main `halfbold` CLI. Rejected because its
  argparse is mode-flag shaped and every mode would need a JSON twin.
