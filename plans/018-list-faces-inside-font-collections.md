# Plan 018: The app lists, previews and converts fonts that ship inside `.ttc` collections (Menlo, Times, PT Mono…)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 42e9bbb..HEAD -- src/halfbold/scan.py src/halfbold/build.py src/halfbold/api.py app/src/api.ts tests/conftest.py tests/test_scan.py tests/test_api.py AGENTS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `42e9bbb`, 2026-10-20

## Why this matters

The maintainer searched the app for **Menlo** (VS Code's default editor font on macOS) to make a Half version of it, and got no results. The reason is that the scan only looks at `.ttf` and `.otf` files, but macOS ships Menlo, Times, PT Mono, PT Sans, Gill Sans, Futura, Didot and many others as **TrueType Collections** (`.ttc`): one file that holds several faces. `/System/Library/Fonts` and `/System/Library/Fonts/Supplemental` hold about 100 `.ttc` files with 545 faces, and 446 of those faces use TrueType outlines that halfbold can convert. `/System/Library/Fonts/Menlo.ttc` holds Menlo Regular (400), Bold (700), Italic and Bold Italic, all with a `glyf` table, so it is an ordinary Regular + Bold family once the scan can see inside it. After this plan, those families show up in the app's Installed tab and preview, build and install like any other font.

## Current state

### The idea: a face inside a collection is addressed as `<file>#<index>`

Faces travel as path strings all the way from the scan, through the JSON API, into the Tauri app and back as CLI arguments (`preview --face PATH`, `build REGULAR BOLD`). Rather than change every one of those types, this plan writes a collection face as the collection's path followed by `#` and the face's index in the collection:

```
/System/Library/Fonts/Menlo.ttc#0   ← Menlo Regular
/System/Library/Fonts/Menlo.ttc#1   ← Menlo Bold
```

That string is still a `pathlib.Path` (`Path("/x/Menlo.ttc#1")` works, `.parent` is `/x`, `.stem` is `Menlo`), so `Face.path`, `Candidate.regular`, `Candidate.bold`, the JSON payloads and the app's TypeScript types do not change. Only the few places that **open** or **stat** the file need to split it. Plain `.ttf`/`.otf` paths never contain `.ttc#<digits>`, so they behave exactly as today.

Do **not** extract every collection face to disk during the scan. That was measured on the maintainer's machine: 272 files, 473 MB, 6 seconds. Faces are extracted to a standalone `.ttf` only when the app needs to draw one (step 5).

### Files and roles

- `src/halfbold/scan.py`: finds font files, reads each face's family, style and weight (`FontInfo`), and groups them into `Candidate` families.
- `src/halfbold/build.py`: `load_font_pair` opens the two source faces with `TTFont(path)`.
- `src/halfbold/api.py`: the JSON API the Tauri app calls (`halfbold-api installed|preview|build|…`). It caches preview builds in `CACHE_DIR` (`~/Library/Caches/halfbold` on macOS).
- `app/src/api.ts`: the app's wrapper around the API. `readFont(path)` fetches font bytes from the Rust command `read_font` so the app can draw each row in its own face.
- `app/src-tauri/src/lib.rs:175-185`: the Rust `read_font` accepts only paths ending `.ttf`/`.otf` that sit under the font folders or `~/Library/Caches/halfbold`. **It does not change in this plan.** The app passes it the extracted `.ttf` from the cache instead.
- New: `src/halfbold/collection.py`, which holds the `#<index>` helpers.

### Code as it is today

`src/halfbold/scan.py:69-85` (`Candidate`):

```python
    @property
    def sources(self) -> list[Path]:
        return [p for p in (self.regular, self.bold) if p is not None]
...
    def is_stale(self) -> bool:
        if not self.output.exists():
            return True
        built = self.output.stat().st_mtime
        return any(p.stat().st_mtime > built for p in self.sources)
```

`src/halfbold/scan.py:126-149`:

```python
def read_font_info(path: Path) -> FontInfo | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (path, stat.st_mtime_ns, stat.st_size)
    ...

def load_font_info(path: Path) -> FontInfo | None:
    try:
        font = TTFont(path, lazy=True)
    except TTLibError, OSError:
        return None
```

(`except TTLibError, OSError:` without parentheses is valid on this repo's Python 3.14, PEP 758. Match it.)

`src/halfbold/scan.py:167-172`:

```python
def is_half_output(info: FontInfo) -> bool:
    return info.family.endswith(f" {STYLE_SUFFIX}")


def is_italic(info: FontInfo) -> bool:
    return "italic" in info.style.lower() or "oblique" in info.style.lower()
```

`src/halfbold/scan.py:199-220`, which is what the app's Installed tab calls:

```python
def find_installed_candidates(
    fonts_dir: Path, settings: Settings | None = None
) -> list[Candidate]:
    roots = [fonts_dir]
    if fonts_dir == Path.home() / "Library/Fonts":
        roots.extend(installed_font_dirs())
    paths = dict.fromkeys(
        path
        for root in reversed(roots)
        for path in sorted(root.rglob("*"))
        if path.suffix.lower() in {".ttf", ".otf"}
        and not path.name.startswith("._")
        and path.is_file()
    )
```

`src/halfbold/scan.py:260-269` (`candidates_from_paths`):

```python
    infos = [
        info
        for path in paths
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_italic(info)
    ]
```

`src/halfbold/build.py:81-101`:

```python
def load_font_pair(
    regular_path: Path,
    bold_path: Path | None,
    ...
    if bold_path is None:
        variable = TTFont(regular_path)
        ...
        regular = instance_at_weight(TTFont(regular_path), regular_weight)
        bold = instance_at_weight(TTFont(regular_path), bold_weight)
        return regular, bold
    regular = TTFont(regular_path)
    bold = TTFont(bold_path)
```

`src/halfbold/api.py:105-127`: cache helpers. Follow this pattern in step 5:

```python
def is_fresh(target: Path, sources: list[Path]) -> bool:
    if not target.exists():
        return False
    built = target.stat().st_mtime
    return all(path.stat().st_mtime <= built for path in sources)


def cache_lock(path: Path) -> threading.Lock:
    with CACHE_LOCKS_GUARD:
        return CACHE_LOCKS.setdefault(path, threading.Lock())


def build_into_cache(candidate: Candidate, half: Path, settings: Settings) -> None:
    with cache_lock(half):
        if is_fresh(half, candidate.sources):
            return
        part = half.with_name(f"{half.name}.{os.getpid()}.{threading.get_ident()}.part")
        try:
            build_halfbold_font(candidate.regular, candidate.bold, part, settings)
            os.replace(part, half)
        finally:
            part.unlink(missing_ok=True)
```

`src/halfbold/api.py:242-249`: an existing subcommand that returns a cached file path. Model `face-file` on it:

```python
def cask_face(args: argparse.Namespace) -> dict:
    entry = next((c for c in cask_index() if c.get("token") == args.token), None)
    ...
    return {"token": args.token, "face": None if face is None else str(face)}
```

and its registration in `parse_args` (`src/halfbold/api.py:~310`):

```python
    cask_face_parser = subparsers.add_parser("cask-face")
    cask_face_parser.add_argument("token")
    cask_face_parser.set_defaults(handler=cask_face)
```

`app/src/api.ts:40-46` and `:94-96`:

```ts
async function api<T>(...args: string[]): Promise<T> {
  return invoke<T>("api", { args });
}
...
export function readFont(path: string) {
  return invoke<ArrayBuffer>("read_font", { path });
}
```

### fontTools facts (verified on this repo's venv)

- `TTFont(path, fontNumber=n, lazy=True)` opens face `n` of a `.ttc`. Without `fontNumber`, opening a `.ttc` raises.
- `fontTools.ttLib.sfnt.readTTCHeader(file).numFonts` gives the face count from an open binary file, and raises `TTLibError` if the file is not a collection.
- `TTFont(ttc, fontNumber=n).save(out)` writes a standalone `.ttf` of that face.
- `TTFont` is a context manager (`with TTFont(...) as font:`).
- Tests can build a collection with `TTCollection()`: set `.fonts = [TTFont(a), TTFont(b)]` and call `.save(path)`.

### Conventions (from `AGENTS.md`)

- **No comments at all** in code. Ruff's `ERA` rule catches commented-out code, and a hook rejects comments. Use clear names instead.
- Small functions that do one thing. Match the style of `scan.py`: module-level constants in `UPPER_CASE`, plain functions, `pathlib.Path` everywhere.
- TDD: write the failing test first, then the smallest change that passes it.
- Commit messages are Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`). The `commit-msg` hook rejects anything else.
- Only TrueType (`glyf`) faces are supported. `.otc` (CFF collections) stays unsupported and is not scanned.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Python tests | `uv run pytest -q` | all pass (136 at plan time, plus the new ones) |
| One test file | `uv run pytest -q tests/test_collection.py` | all pass |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | exit 0 |
| TS typecheck | `cd app && bunx tsc --noEmit` | exit 0, no output |
| TS tests | `cd app && bun test` | all pass |
| Dead-code check | `cd app && npx fallow` | no new findings in `src/api.ts` |
| Real-machine smoke | see step 7 | Menlo listed with `#0`/`#1` faces |

## Scope

**In scope** (the only files you should modify):
- `src/halfbold/collection.py` (create)
- `src/halfbold/scan.py`
- `src/halfbold/build.py`
- `src/halfbold/api.py`
- `app/src/api.ts`
- `tests/conftest.py` (add one helper)
- `tests/test_collection.py` (create)
- `tests/test_scan.py`, `tests/test_api.py` (add tests)
- `AGENTS.md` (one bullet under "How it works")
- `plans/README.md` (status row)

**Out of scope** (do NOT touch):
- `app/src-tauri/src/lib.rs`: `read_font` already accepts `.ttf` files under `~/Library/Caches/halfbold`, which is where step 5 puts extracted faces. Teaching Rust to parse TTC headers is unnecessary.
- `find_candidates`, `find_installed_half_families` and `build_all` in `scan.py`, which serve the `halfbold sync` CLI and launchd watcher on `~/Library/Fonts`. Users do not drop `.ttc` files there, and Half output is always `.ttf`.
- `src/halfbold/preview.py` and `cli.py`: the terminal preview is scheduled for removal (plan 013).
- `faces_tag` in `api.py`: `Path("…/Menlo.ttc#1").stem` is `Menlo`, and the weights already keep tags distinct.
- `.otc` and `.dfont` files.

## Git workflow

- Branch: `advisor/018-font-collections`
- One commit per step that leaves the tests green. Message style from `git log`: `feat: resolve the preview face pair from the family`, `fix: keep the font editor sliders from fighting the user`. End each message with the attribution trailer the operator gives you.
- Do NOT push or open a PR.

## Steps

### Step 1: Add the collection helpers (test first)

Add to `tests/conftest.py`, below `make_font`:

```python
def make_collection(path: Path, faces: list[Path]) -> Path:
    collection = TTCollection()
    collection.fonts = [TTFont(face) for face in faces]
    collection.save(path)
    return path
```

(import `TTCollection, TTFont` from `fontTools.ttLib`).

Create `tests/test_collection.py`. Build the faces in a scratch subfolder and the `.ttc` next to it, for example `make_font(tmp_path / "parts" / "Coll-Regular.ttf", "Coll", "Regular", 100)` and a Bold at `weight=700`. Cover:

1. `collection_members(ttc)` returns `[Path(f"{ttc}#0"), Path(f"{ttc}#1")]`.
2. `collection_members` on a plain `.ttf` and on a missing file returns `[]`.
3. `split_member(Path(f"{ttc}#1")) == (ttc, 1)`, and `split_member(plain_ttf) == (plain_ttf, None)`.
4. `source_file(Path(f"{ttc}#1")) == ttc`.
5. `open_font(Path(f"{ttc}#1"))["name"].getDebugName(2) == "Bold"`, and `open_font(plain_ttf)` opens a plain file.

Run it and watch it fail on the import. Then create `src/halfbold/collection.py`:

```python
import re
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.sfnt import readTTCHeader

COLLECTION_SUFFIX = ".ttc"
MEMBER = re.compile(r"(?P<file>.+\.ttc)#(?P<number>\d+)", re.IGNORECASE)


def member_path(collection: Path, number: int) -> Path:
    return Path(f"{collection}#{number}")


def split_member(path: Path) -> tuple[Path, int | None]:
    match = MEMBER.fullmatch(str(path))
    if match is None:
        return path, None
    return Path(match["file"]), int(match["number"])


def source_file(path: Path) -> Path:
    return split_member(path)[0]


def open_font(path: Path, lazy: bool | None = None) -> TTFont:
    file, number = split_member(path)
    if number is None:
        return TTFont(file, lazy=lazy)
    return TTFont(file, fontNumber=number, lazy=lazy)


def collection_members(path: Path) -> list[Path]:
    try:
        with path.open("rb") as file:
            count = readTTCHeader(file).numFonts
    except TTLibError, OSError:
        return []
    return [member_path(path, number) for number in range(count)]
```

**Verify**: `uv run pytest -q tests/test_collection.py` → all pass. `uv run ruff check . && uv run ruff format --check .` → clean.

### Step 2: Read face info and staleness through the helpers

Test first, in `tests/test_scan.py`: build a `.ttc` with Regular (stem 100, weight 400), Bold (stem 200, weight 700) and Italic faces. Then `candidates_from_paths(collection_members(ttc))` should return one candidate whose `family == "Coll"`, `regular == Path(f"{ttc}#0")`, `bold == Path(f"{ttc}#1")`, and `sources == [ttc, ttc]`. Add a second test: `read_font_info(Path(f"{ttc}#1")).style == "Bold"`.

Then change `src/halfbold/scan.py`:
- `read_font_info`: `stat = source_file(path).stat()`. Keep the cache key as `(path, …)` so that each face gets its own cache entry.
- `load_font_info`: `font = open_font(path, lazy=True)`.
- `Candidate.sources`: `return [source_file(p) for p in (self.regular, self.bold) if p is not None]`. `is_stale` and `api.is_fresh` both stat `sources`, so this one change fixes both.
- Import `open_font, source_file` from `halfbold.collection`. If `TTFont` is no longer used in `scan.py`, drop it from the import.

Check: `candidates_from_paths` has `kind = next(i.kind for i in members if i.path == plain.path)`. That still works because each member path is unique, so leave it.

**Verify**: `uv run pytest -q` → all pass.

### Step 3: Scan `.ttc` files in the installed folders, and hide dot-families

Test first, in `tests/test_api.py`, next to `test_installed_discovers_system_fonts_and_builds_into_user_folder` (line ~400) and using the same `monkeypatch` setup (`Path.home` → `tmp_path`, `scan.installed_font_dirs` → `[system]`). Put a Regular + Bold `.ttc` named `Menlo.ttc` with family `Menlo` in `system`. Then `main(["installed", "--fonts-dir", str(fonts)])` should include a candidate with `family == "Menlo"`, `regular == f"{system / 'Menlo.ttc'}#0"`, `bold == f"…#1"`, `output == str(fonts / "Menlo-Half.ttf")`, `built is False` and `stale is True`.

Second test: a `.ttc` whose two faces have family `.Hidden` produces no candidate. macOS uses a leading dot for private system families such as `.ThonburiUI` and `.Muna PUA`, which live only inside collections.

Then, in `src/halfbold/scan.py`:

```python
FONT_SUFFIXES = {".ttf", ".otf", COLLECTION_SUFFIX}


def face_paths(path: Path) -> list[Path]:
    if path.suffix.lower() == COLLECTION_SUFFIX:
        return collection_members(path)
    return [path]


def is_hidden(info: FontInfo) -> bool:
    return info.family.startswith(".")
```

- In `find_installed_candidates`, make the generator iterate `for face in face_paths(path)` after the existing filters, and use `FONT_SUFFIXES` in place of the `{".ttf", ".otf"}` literal.
- In `candidates_from_paths`, add `and not is_hidden(info)` to the `infos` filter.

**Verify**: `uv run pytest -q` → all pass.

### Step 4: Build from collection faces

Test first, in `tests/test_api.py`: using the `.ttc` from step 3, `main(["build", f"{ttc}#0", f"{ttc}#1", "-o", str(out)])` returns 0, and `out` exists with family `Coll Half` (or whatever the source family is plus ` Half`). Also check that `main(["preview", "--face", f"{ttc}#0", "--face", f"{ttc}#1"])`, with `api.CACHE_DIR` monkeypatched to `tmp_path / "cache"` as `test_preview_caches_half_in_cache_dir` (line 47) does, returns a payload whose `half` file exists. A second identical call must leave its mtime unchanged.

Then, in `src/halfbold/build.py` `load_font_pair`, replace each of the five `TTFont(...)` calls on a source path with `open_font(...)` from `halfbold.collection`. Remove `TTFont` from the imports only if nothing else in `build.py` uses it (it is used in type hints, so it most likely stays).

**Verify**: `uv run pytest -q` → all pass.

### Step 5: `halfbold-api face-file PATH` returns a drawable `.ttf`

The app draws each row in its own face by reading the font bytes. Browsers cannot load one face out of a `.ttc`, and the Rust `read_font` refuses non-`.ttf`/`.otf` paths. This step gives the app a standalone file instead.

Test first, in `tests/test_api.py` (monkeypatch `api.CACHE_DIR`):
1. `main(["face-file", f"{ttc}#1"])` prints `{"path": …}`. That file exists under `cache_dir / "collections"`, ends in `.ttf`, and opens with `TTFont` to a face whose style is `Bold`.
2. A second call returns the same path and does not rewrite it (mtime unchanged).
3. `main(["face-file", str(plain_ttf)])` returns the plain path unchanged and writes nothing to the cache.

Then add to `src/halfbold/api.py`, next to `build_into_cache`:

```python
def standalone_face(path: Path) -> Path:
    file, number = split_member(path)
    if number is None:
        return path
    folder = CACHE_DIR / "collections" / file.parent.relative_to(file.anchor)
    target = folder / f"{file.stem}-{number}.ttf"
    if not is_fresh(target, [file]):
        extract_into_cache(path, target)
    return target


def extract_into_cache(path: Path, target: Path) -> None:
    with cache_lock(target):
        if is_fresh(target, [source_file(path)]):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(
            f"{target.name}.{os.getpid()}.{threading.get_ident()}.part"
        )
        try:
            with open_font(path) as font:
                font.save(part)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)


def face_file(args: argparse.Namespace) -> dict:
    return {"path": str(standalone_face(args.path))}
```

Register it in `parse_args` the same way as `cask-face`:

```python
    face_file_parser = subparsers.add_parser("face-file")
    face_file_parser.add_argument("path", type=Path)
    face_file_parser.set_defaults(handler=face_file)
```

Mirroring the collection's own folder under `collections/` keeps two `Menlo.ttc` files in different font folders from overwriting each other.

**Verify**: `uv run pytest -q` → all pass; `uv run ruff check . && uv run ruff format --check .` → clean.

### Step 6: The app reads collection faces through `face-file`

In `app/src/api.ts`, replace `readFont` with:

```ts
const COLLECTION_FACE = /\.ttc#\d+$/i;

async function drawableFile(path: string) {
  if (!COLLECTION_FACE.test(path)) return path;
  return (await api<{ path: string }>("face-file", path)).path;
}

export async function readFont(path: string) {
  return invoke<ArrayBuffer>("read_font", { path: await drawableFile(path) });
}
```

Place `COLLECTION_FACE` with the other module-level declarations near the top if the file has any; otherwise put it just above `drawableFile`. `fonts.ts` keeps keying its caches by the original `#<index>` path, so nothing else in the app changes.

**Verify**: `cd app && bunx tsc --noEmit` → exit 0; `cd app && bun test` → all pass; `cd app && npx fallow` → no findings in `src/api.ts`.

### Step 7: Smoke-check on the real system fonts

```sh
uv run halfbold-api installed | uv run python -c "import json,sys; c=[x for x in json.load(sys.stdin)['candidates'] if x['family']=='Menlo']; print(c[0]['regular'], c[0]['bold'], c[0]['faces_label'])"
```

Expected: `/System/Library/Fonts/Menlo.ttc#0 /System/Library/Fonts/Menlo.ttc#1 plain Regular 400, bold Bold 700`.

```sh
uv run halfbold-api preview --face '/System/Library/Fonts/Menlo.ttc#0' --face '/System/Library/Fonts/Menlo.ttc#1' | head -c 400
uv run halfbold-api face-file '/System/Library/Fonts/Menlo.ttc#0'
```

Expected: both print JSON with no `error` key. The `half` file exists under `~/Library/Caches/halfbold/`, and the `face-file` path exists under `~/Library/Caches/halfbold/collections/System/Library/Fonts/Menlo-0.ttf`.

Also time the scan: `time uv run halfbold-api installed > /dev/null`. Record the before and after times in your report. More than 3 s slower than before is a STOP condition.

If a GUI is available, also run `cd app && bun run tauri dev`, search for `Menlo`, select it, and confirm the row is drawn in Menlo, the half-bold preview renders, and the webview console shows no errors. If no GUI is available, write "manual GUI check pending" in the status row.

### Step 8: Document it

In `AGENTS.md` under "How it works", add one bullet after the static-family bullet:

> - The app also scans TrueType Collections (`.ttc`, e.g. `/System/Library/Fonts/Menlo.ttc`). Each face inside is addressed as `<file>#<index>` everywhere a path is passed (scan, JSON API, app). `collection.open_font` opens it, `Candidate.sources` stats the real file, and `halfbold-api face-file` extracts one face to `~/Library/Caches/halfbold/collections/` so the app can draw it. Families whose name starts with `.` are macOS-private and are skipped.

**Verify**: `git diff --stat` shows only in-scope files.

## Test plan

- `tests/test_collection.py` (new): the 5 helper cases in step 1.
- `tests/test_scan.py`: collection candidate grouping (regular `#0`, bold `#1`, italic skipped, `sources` are the real file) and `read_font_info` on a member.
- `tests/test_api.py`: installed lists the collection family with the right output and staleness; dot-families hidden; `build` and `preview` accept member paths and the preview cache is reused; `face-file` extracts once, reuses the extracted file, and returns plain paths unchanged.
- Patterns to follow: `test_installed_discovers_system_fonts_and_builds_into_user_folder` (test_api.py ~400) for the system-folder monkeypatching, and `test_preview_caches_half_in_cache_dir` (test_api.py:47) for the cache directory.

## Done criteria

- [ ] `uv run pytest -q` exits 0 with at least 12 more tests than the 136 at plan time
- [ ] `uv run ruff check .` and `uv run ruff format --check .` exit 0
- [ ] `cd app && bunx tsc --noEmit` and `cd app && bun test` exit 0
- [ ] `grep -n '{".ttf", ".otf"}' src/halfbold/scan.py` returns nothing inside `find_installed_candidates`
- [ ] Step 7's command prints `/System/Library/Fonts/Menlo.ttc#0 /System/Library/Fonts/Menlo.ttc#1 plain Regular 400, bold Bold 700`
- [ ] `git diff --name-only 42e9bbb` lists only in-scope files
- [ ] `plans/README.md` row 018 updated

## STOP conditions

Stop and report back (do not improvise) if:

- The excerpts in "Current state" don't match the live code.
- `TTFont(..., fontNumber=n, lazy=True)` or `readTTCHeader` behaves differently from the "fontTools facts" above (for example after a fontTools upgrade).
- The `installed` scan gets more than 3 s slower on the real machine (step 7). Report the timing and do not add caching or threading on your own.
- Any Apple `.ttc` makes `installed` fail outright, rather than that one file being skipped. A single bad face should already be skipped by `load_font_info`'s `except`.
- Building Menlo (step 7 preview) raises, for example `is not a TrueType font` or a GSUB compile error. Report the traceback; that is a build problem, not a scan problem.
- The app cannot draw the extracted face because Rust `read_font` rejects it. That would mean `CACHE_DIR` is outside `font_roots()`, and changing `lib.rs` is out of scope.

## Maintenance notes

- A `<file>.ttc#<n>` path is a `Path` that does **not** exist on disk. Any new code that calls `.stat()`, `.exists()`, `open()` or `TTFont()` on a face path must go through `source_file` or `open_font`. Reviewers should grep new code for those calls on `Face.path`, `Candidate.regular` and `Candidate.bold`.
- Apple can reorder faces inside a `.ttc` across OS updates. The `#<index>` addresses are recomputed on every scan, and `Candidate.sources` mtime checks rebuild stale Half fonts, so nothing persists an index across scans. Keep it that way.
- The `collections/` cache grows only with faces the app actually draws (row styling of visible rows plus plain previews). If it ever needs pruning, delete files older than their source, alongside the existing preview cache.
- Deferred: scanning `.ttc` in `halfbold sync` / the launchd watcher (`find_candidates`), and `.otc` (CFF) collections, which halfbold cannot convert anyway.
