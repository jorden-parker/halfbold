# Plan 014: Show each Homebrew cask by its real font name, rendered in its own font, and style Installed rows the same way

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 81080f8..HEAD -- src/halfbold/api.py src/halfbold/brewcask.py tests/test_api.py tests/test_brewcask.py app/src/`
> Plans 011 and 012 must be DONE **and merged** (`git log --oneline | grep
> "app clears the previous preview"` must find commit `81080f8` or its
> equivalent on your branch). Empty diff → proceed. Anything else → compare
> the "Current state" excerpts against the live code; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (additive Python + frontend; one new network source, cached; no change to build/install paths)
- **Depends on**: plans/011-json-api-for-the-app.md, plans/012-tauri-font-app.md
- **Category**: direction
- **Planned at**: commit `81080f8` (tip of `advisor/012-tauri-app`), 2026-09-16

## Why this matters

The Homebrew tab lists raw cask tokens (`font-0xproto`, `font-abril-fatface`).
The maintainer asked for the actual font name instead ("0xProto", "Abril
Fatface"), with each name drawn in that font, so the list itself is the
preview. The same treatment on the Installed tab makes both lists consistent.

Two facts shape the design (probed 2026-09-16):

- `https://formulae.brew.sh/api/cask.json` is one 19 MB JSON (about 0.5 s to
  download) holding every cask with a `name` list, `url`, `url_specs` and
  `artifacts`. All 2597 `font-*` casks have a non-empty `name`. Per-token
  `brew info` would take ~0.5 s each, so the index is the only viable
  source. It is cached on disk for a day.
- Only 508 of those casks come from the google/fonts git repo, where a
  single TTF can be fetched by URL (100–300 KB). The other ~2100 point at
  zips, dmgs or pkgs that can be hundreds of MB, so their rows cannot be
  styled up front. They are styled after the user previews or installs
  them (the app already downloads the fonts then). This is a deliberate
  limit, not something to work around.

## Current state

### Repo facts

- Conventions (`AGENTS.md`): no code comments in any language; Conventional
  Commits; run `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest -q` after Python changes and `cd app && pnpm build` after
  frontend changes. Rust toolchain lives in `/opt/homebrew/opt/rustup/bin`
  (add to `PATH` before any `cargo`/`pnpm tauri` command). This plan does
  not touch Rust.
- The Tauri app lives in `app/`; it calls `halfbold-api` through the Rust
  `api` command (`invoke("api", { args })`) and reads font bytes through
  `read_font`. See `app/src/api.ts`.

### Python — `src/halfbold/brewcask.py`

- `GOOGLE_FONTS_GIT_URL = "https://github.com/google/fonts.git"`.
- `CaskInfo(token, url, branch, only_path, fonts, targets)`.
- `parse_cask_info(data: bytes)` (lines 27–44) parses **`brew info --json=v2`**
  output, which wraps the cask in `{"casks": [...]}`:
  ```python
  def parse_cask_info(data: bytes) -> CaskInfo:
      payload = json.loads(data)
      casks = payload.get("casks") or []
      if not casks:
          raise ValueError("brew info returned no cask")
      cask = casks[0]
      url_specs = cask.get("url_specs") or {}
      artifacts = [a for a in cask.get("artifacts", []) if "font" in a]
      fonts = [a["font"][0] for a in artifacts]
      targets = [a.get("target", "") for a in artifacts]
      return CaskInfo(
          token=cask["token"],
          url=cask.get("url", ""),
          branch=url_specs.get("branch", ""),
          only_path=url_specs.get("only_path", ""),
          fonts=fonts,
          targets=targets,
      )
  ```
  The formulae API returns the **same per-cask object shape** (`token`,
  `name`, `url`, `url_specs`, `artifacts`), just as a bare list, not wrapped.
- `google_fonts_urls(info)` (lines 60–73) returns raw.githubusercontent URLs
  for every non-italic `.ttf` of a Google Fonts cask; `[]` otherwise.
- `download_google_fonts(info, into)` downloads all of them with
  `urllib.request.urlopen(url, timeout=30)` and raises
  `ValueError(f"download failed: {url}: {err.reason}")` on `URLError`.
- `search_font_casks()` runs `brew search --cask font-` and returns tokens.

### Python — `src/halfbold/api.py`

- `CACHE_DIR = Path(tempfile.gettempdir()) / "halfbold-app"`.
- Handler today (lines 88–89):
  ```python
  def casks(args: argparse.Namespace) -> dict:
      return {"casks": search_font_casks()}
  ```
  Registered at lines 147–148 (`casks_parser = subparsers.add_parser("casks")`).
- Errors: `main` catches `(ValueError, TTLibError, OSError)` and prints
  `{"error": ...}` with exit 1.

### Frontend — `app/src/api.ts`

```ts
export function casks() {
  return api<{ casks: string[] }>("casks");
}
```

### Frontend — `app/src/fonts.ts` (whole file)

```ts
import { readFont } from "./api";

const faces = new Map<string, FontFace>();
let counter = 0;

export async function loadFace(path: string): Promise<string> {
  const previous = faces.get(path);
  if (previous) document.fonts.delete(previous);
  const alias = `hb-${++counter}`;
  const face = new FontFace(alias, await readFont(path));
  await face.load();
  document.fonts.add(face);
  faces.set(path, face);
  return alias;
}
```

`loadFace` deliberately reloads every time (the preview must pick up a
rebuilt `-Half.ttf`). List rows need the opposite: load once, reuse.

### Frontend — `app/src/main.ts`

- State: `caskTokens: string[] | null`; selection type
  `{ tab: "brew"; token: string }`.
- `filteredTokens()` filters `state.caskTokens` by substring.
- `renderList()` brew branch (lines 130–151) creates one `<li>` per token with
  `li.textContent = token`, caps at 200 rows plus a `li.more` row.
- `renderBrewDetail(token)` sets `titleEl.textContent = token` and
  `metaEl.textContent = ""`.
- `onPreviewCask(token)` gets `result.candidates` from `caskFonts(token)`;
  `onInstallCask(token)` gets `installResult.candidates` from
  `caskInstall(token)`. Both know each candidate's `regular` path.
- `ensureCasks()` calls `casks()` once and stores `result.casks`.

### Frontend — `app/src/styles.css`

Rows are `#list li { display: flex; gap: 8px; align-items: baseline; … }`
with `.kind`/`.state` spans pushed right by `margin-left: auto` at 11px muted.

### Tests

- `tests/test_brewcask.py`: `ROBOTO_JSON` fixture (brew-info shape),
  `parse_cask_info` tests, `google_fonts_urls` tests, `monkeypatch` on
  `brewcask.subprocess.run` and on module functions.
- `tests/test_api.py`: `main([...])` + `capsys` + `json.loads`; monkeypatches
  `api.CACHE_DIR`, `api.cask_font_dir`, `api.search_font_casks`, etc.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Python tests | `uv run pytest -q` | all pass |
| Lint/format | `uv run ruff check . && uv run ruff format --check .` | exit 0 |
| Frontend typecheck | `cd app && pnpm build` | exit 0 |
| Run app | `export PATH="/opt/homebrew/opt/rustup/bin:$PATH"; cd app && pnpm tauri dev` | window opens |
| Smoke | `uv run halfbold-api casks \| head -c 300` | JSON with `name` fields |
| Smoke | `uv run halfbold-api cask-face font-roboto` | `{"token": "font-roboto", "face": "/…/halfbold-app/faces/font-roboto/Roboto[wdth,wght].ttf"}` |

## Scope

**In scope**:
- `src/halfbold/brewcask.py`, `src/halfbold/api.py`
- `tests/test_brewcask.py`, `tests/test_api.py`
- `app/src/api.ts`, `app/src/fonts.ts`, `app/src/main.ts`, `app/src/styles.css`
- `README.md` (one sentence in the `## App` section)

**Out of scope**:
- `app/src-tauri/**` — no Rust changes; `read_font` already serves any
  `.ttf`/`.otf` path.
- `src/halfbold/cli.py`, `scan.py`, `build.py`, `preview.py`, `web.py`, `tui/`.
- Styling non-Google casks before preview (see "Why this matters").
- Replacing `brew search` in `search_font_casks` — keep it as the fallback.

## Git workflow

- Branch: `advisor/014-cask-names`
- Commits, Conventional Commits, e.g.
  `feat: halfbold-api casks returns font names from the Homebrew index`,
  `feat: app lists casks and installed fonts by name in their own face`.
- Do NOT push or open a PR unless the operator instructed it.

## Contract additions

`casks` now returns:

```json
{"casks": [{"token": "font-0xproto", "name": "0xProto", "google": false},
           {"token": "font-abril-fatface", "name": "Abril Fatface", "google": true}, …]}
```

New `cask-face TOKEN` returns `{"token": "...", "face": "/path/to/Regular.ttf"}`
for a Google Fonts cask (downloaded once into `<CACHE_DIR>/faces/<token>/`),
or `{"token": "...", "face": null}` for any other cask. Unknown token →
`{"error": "unknown cask: TOKEN"}`, exit 1.

## Steps

### Step 1: Refactor `parse_cask_info` and add the index fetch (`brewcask.py`)

1. Split the per-cask parsing out so both `brew info` output and index
   entries share it:
   ```python
   def cask_info_from_payload(cask: dict) -> CaskInfo:
       url_specs = cask.get("url_specs") or {}
       artifacts = [a for a in cask.get("artifacts", []) if "font" in a]
       fonts = [a["font"][0] for a in artifacts]
       targets = [a.get("target", "") for a in artifacts]
       return CaskInfo(
           token=cask["token"],
           url=cask.get("url", ""),
           branch=url_specs.get("branch", ""),
           only_path=url_specs.get("only_path", ""),
           fonts=fonts,
           targets=targets,
       )


   def parse_cask_info(data: bytes) -> CaskInfo:
       payload = json.loads(data)
       casks = payload.get("casks") or []
       if not casks:
           raise ValueError("brew info returned no cask")
       return cask_info_from_payload(casks[0])
   ```
2. Add the index:
   ```python
   import time

   CASK_INDEX_URL = "https://formulae.brew.sh/api/cask.json"
   CASK_INDEX_MAX_AGE = 24 * 60 * 60


   def fetch_cask_index(cache: Path, max_age: float = CASK_INDEX_MAX_AGE) -> list[dict]:
       if cache.exists() and time.time() - cache.stat().st_mtime < max_age:
           return json.loads(cache.read_text())
       try:
           with urllib.request.urlopen(CASK_INDEX_URL, timeout=60) as response:
               data = response.read()
       except URLError as err:
           if cache.exists():
               return json.loads(cache.read_text())
           raise ValueError(f"cask index download failed: {err.reason}") from err
       cache.parent.mkdir(parents=True, exist_ok=True)
       cache.write_bytes(data)
       return json.loads(data)


   def is_google_fonts_cask(cask: dict) -> bool:
       url_specs = cask.get("url_specs") or {}
       return cask.get("url") == GOOGLE_FONTS_GIT_URL and bool(url_specs.get("only_path"))


   def font_cask_entries(index: list[dict]) -> list[dict]:
       entries = []
       for cask in index:
           token = cask.get("token", "")
           if not token.startswith(FONT_CASK_PREFIX):
               continue
           names = cask.get("name") or []
           entries.append(
               {
                   "token": token,
                   "name": ", ".join(names) or token,
                   "google": is_google_fonts_cask(cask),
               }
           )
       return sorted(entries, key=lambda e: e["name"].lower())


   def download_google_face(info: CaskInfo, into: Path) -> Path | None:
       urls = google_fonts_urls(info)
       if not urls:
           return None
       url = urls[0]
       path = into / urllib.parse.unquote(Path(url).name)
       if path.exists():
           return path
       into.mkdir(parents=True, exist_ok=True)
       try:
           with urllib.request.urlopen(url, timeout=30) as response:
               path.write_bytes(response.read())
       except URLError as err:
           raise ValueError(f"download failed: {url}: {err.reason}") from err
       return path
   ```
   `FONT_CASK_PREFIX` already exists further down the file; move the
   constant up near the other module constants so it is defined before use
   (ruff does not care about order for runtime, but keep the file readable).
3. Tests in `tests/test_brewcask.py`:
   - `test_cask_info_from_payload_matches_parse_cask_info`: both paths on
     `ROBOTO_JSON["casks"][0]` give equal `CaskInfo`.
   - `test_font_cask_entries_names_and_google_flag`: index
     `[{"token": "font-b", "name": ["B Font"], "url": GOOGLE_FONTS_GIT_URL, "url_specs": {"only_path": "ofl/b"}}, {"token": "font-a", "name": [], "url": "https://x/a.zip"}, {"token": "not-font", "name": ["X"]}]`
     → `[{"token": "font-b", "name": "B Font", "google": True}, {"token": "font-a", "name": "font-a", "google": False}]`
     (sorted by name, `not-font` dropped, missing name falls back to token).
   - `test_fetch_cask_index_uses_fresh_cache(tmp_path, monkeypatch)`: write
     `[{"token": "font-x"}]` to `cache`; monkeypatch
     `brewcask.urllib.request.urlopen` to raise `AssertionError("network used")`;
     expect the cached list.
   - `test_fetch_cask_index_downloads_when_stale(tmp_path, monkeypatch)`:
     stale cache (`os.utime` to two days ago); fake `urlopen` returning a
     context manager whose `.read()` gives `b'[{"token": "font-y"}]'`; expect
     `font-y` and the cache file rewritten.
   - `test_fetch_cask_index_falls_back_to_stale_cache_offline(tmp_path, monkeypatch)`:
     stale cache + `urlopen` raising `URLError("offline")` → cached list.
   - `test_download_google_face_downloads_first_regular(tmp_path, monkeypatch)`:
     `CaskInfo` for roboto (fonts `["Roboto-Italic[wdth,wght].ttf", "Roboto[wdth,wght].ttf"]`);
     fake `urlopen` records the URL and returns `b"ttf"`; expect path
     `tmp_path / "Roboto[wdth,wght].ttf"` with content `b"ttf"` and the URL
     ending in `Roboto%5Bwdth%2Cwght%5D.ttf`; second call must not hit the
     network (monkeypatch to raise).
   - `test_download_google_face_none_for_other_casks`: non-Google `CaskInfo`
     → `None`.

**Verify**: `uv run pytest -q tests/test_brewcask.py` → all pass. `uv run ruff check . && uv run ruff format --check .` → exit 0.

### Step 2: `casks` returns entries; add `cask-face` (`api.py`)

```python
CASK_INDEX_CACHE = "cask-index.json"


def cask_index() -> list[dict]:
    return fetch_cask_index(CACHE_DIR / CASK_INDEX_CACHE)


def casks(args: argparse.Namespace) -> dict:
    try:
        return {"casks": font_cask_entries(cask_index())}
    except ValueError:
        tokens = search_font_casks()
        return {"casks": [{"token": t, "name": t, "google": False} for t in tokens]}


def cask_face(args: argparse.Namespace) -> dict:
    entry = next((c for c in cask_index() if c.get("token") == args.token), None)
    if entry is None:
        raise ValueError(f"unknown cask: {args.token}")
    face = download_google_face(
        cask_info_from_payload(entry), CACHE_DIR / "faces" / args.token
    )
    return {"token": args.token, "face": None if face is None else str(face)}
```

Register `cask-face` with a `token` positional next to `cask-fonts`. Import
`cask_info_from_payload`, `download_google_face`, `fetch_cask_index`,
`font_cask_entries` from `halfbold.brewcask`.

Tests in `tests/test_api.py` (monkeypatch `api.CACHE_DIR` and
`api.fetch_cask_index` to return a small index):
- `test_casks_returns_names_from_index`: index with two font casks and one
  non-font → `casks` payload has the two entries with `name` and `google`.
- `test_casks_falls_back_to_brew_search`: `api.fetch_cask_index` raises
  `ValueError`, `api.search_font_casks` returns `["font-z"]` → entry
  `{"token": "font-z", "name": "font-z", "google": False}`.
- `test_cask_face_google(monkeypatch)`: index has a Google cask; monkeypatch
  `api.download_google_face` to write a file under the given dir and return
  it → payload `face` is that path and the dir is `CACHE_DIR/faces/<token>`.
- `test_cask_face_non_google`: `face` is `None`.
- `test_cask_face_unknown_token`: exit 1, `error == "unknown cask: font-nope"`.

Update the existing `test_casks_reports_brew_failure`: it must now
monkeypatch `api.fetch_cask_index` to raise `ValueError` **and**
`api.search_font_casks` to raise, and still expect exit 1 with the brew
message.

**Verify**: `uv run pytest -q` → all pass. `uv run halfbold-api casks | python3 -c "import json,sys; c=json.load(sys.stdin)['casks']; print(len(c), c[0])"` → about 2597 entries, first has `name`. `uv run halfbold-api cask-face font-roboto` → a `.ttf` path under `…/halfbold-app/faces/font-roboto/`. `uv run halfbold-api cask-face font-0xproto` → `"face": null`.

### Step 3: Frontend types and cached face loading

`app/src/api.ts`:

```ts
export interface CaskEntry {
  token: string;
  name: string;
  google: boolean;
}

export function casks() {
  return api<{ casks: CaskEntry[] }>("casks");
}

export function caskFace(token: string) {
  return api<{ token: string; face: string | null }>("cask-face", token);
}
```

`app/src/fonts.ts` — rewrite the file so previews still reload every time
while list rows load once per path and always see the newest alias:

```ts
import { readFont } from "./api";

const faces = new Map<string, FontFace>();
const aliases = new Map<string, Promise<string>>();
let counter = 0;

export async function loadFace(path: string): Promise<string> {
  const previous = faces.get(path);
  if (previous) document.fonts.delete(previous);
  const alias = `hb-${++counter}`;
  const face = new FontFace(alias, await readFont(path));
  await face.load();
  document.fonts.add(face);
  faces.set(path, face);
  aliases.set(path, Promise.resolve(alias));
  return alias;
}

export function faceAlias(path: string): Promise<string> {
  let pending = aliases.get(path);
  if (!pending) {
    pending = loadFace(path);
    aliases.set(path, pending);
  }
  return pending;
}
```

`loadFace` (used by previews) replaces the face and records the new alias;
`faceAlias` (used by list rows) reuses whatever alias is current. Rows are
rebuilt by `renderList()`, so they pick up a replaced alias on the next
render.

**Verify**: `cd app && pnpm build` → exit 0.

### Step 4: Lists by name in their own face (`main.ts`, `styles.css`)

1. State: replace `caskTokens: string[] | null` with
   `caskEntries: CaskEntry[] | null` and add
   `caskFaces: Map<string, string | null>` (token → alias, `null` = known
   unavailable) plus `caskFacesPending: Set<string>`.
2. `filteredTokens()` → `filteredCasks(): CaskEntry[]`, matching the query
   against `name` **or** `token`, case-insensitive.
3. Brew rows: build each `<li>` as
   `<span class="name">{name}</span><span class="token">{token}</span>`.
   If `state.caskFaces.get(token)` is an alias, set
   `nameSpan.style.fontFamily = alias`. Selection still stores `token`.
4. Lazy face loading: one module-level
   `IntersectionObserver` on `listEl` (`root: listEl`, `rootMargin: "200px"`).
   Observe every brew `<li>` (store `li.dataset.token`). When a row
   intersects and its entry is `google`, the token is not in `caskFaces`
   and not pending: add to pending, call `caskFace(token)`; on result with a
   `face`, `faceAlias(face)` → `caskFaces.set(token, alias)` and, if the row
   is still in the DOM, set its name span's `fontFamily`; on `null` or error,
   `caskFaces.set(token, null)`. Remove from pending in `finally`. Do **not**
   route these through `run()` — they must not touch `#status` or disable
   buttons. Cap concurrency: keep a simple counter, at most 4 in flight;
   rows beyond that are retried on the next intersection callback
   (`observer.unobserve` only after the token is resolved).
5. After `onPreviewCask` and `onInstallCask` obtain `candidates`, style the
   cask's row from the real file: `faceAlias(candidates[0].regular)` →
   `caskFaces.set(token, alias)`; `renderList()`. This is how non-Google
   casks get their face.
6. `renderBrewDetail(token)`: title = the entry's `name` (fall back to token);
   `metaEl.textContent = token`. Keep `onPreviewCask`'s family list in meta
   after preview.
7. Installed rows: `nameSpan` gets `faceAlias(c.regular)` — set
   `fontFamily` when the promise resolves and the span is still connected
   (`span.isConnected`). Keep the family text as is.
8. `styles.css`: add
   ```css
   #list .name { font-size: 17px; line-height: 1.2; }
   #list .token { font-size: 11px; color: var(--muted); }
   #list li.selected .token { color: rgba(255, 255, 255, 0.85); }
   ```
   and let brew rows wrap the two spans on one line with the token pushed
   right (`margin-left: auto`) like `.kind`.

**Verify**: `cd app && pnpm build` → exit 0. Then `pnpm tauri dev`:
- Homebrew tab shows "0xProto" with `font-0xproto` small at the right;
  typing `abril` in the filter finds "Abril Fatface" and, within a second
  or two, the name is drawn in Abril Fatface (a Google cask).
- Scrolling loads faces for rows that come into view; the status line
  stays empty while that happens.
- Select "0xProto" → title "0xProto", meta `font-0xproto`; press Preview →
  the row name switches to 0xProto's face.
- Installed tab: each row's family name is drawn in that family.

### Step 5: README

In the `## App` section add one sentence: "Homebrew casks are listed by
font name (from the Homebrew formulae index, cached for a day) and Google
Fonts casks are drawn in their own face; other casks pick up their face
after a preview or install."

**Verify**: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q && (cd app && pnpm build)` → exit 0.

## Test plan

Python: the 7 new `test_brewcask.py` tests and 5 new `test_api.py` tests in
Steps 1–2, plus the updated `test_casks_reports_brew_failure`. Frontend:
`pnpm build` typecheck plus the manual checklist in Step 4 (the reviewer
performs it; report it as NOT PERFORMED if you cannot interact with the
window).

## Done criteria

- [ ] `uv run pytest -q` exits 0 with the new tests present
- [ ] `uv run ruff check .` and `uv run ruff format --check .` exit 0
- [ ] `cd app && pnpm build` exits 0
- [ ] `uv run halfbold-api casks` returns objects with `token`, `name`, `google`
- [ ] `uv run halfbold-api cask-face font-roboto` returns a `.ttf` path that exists; `font-0xproto` returns `"face": null`
- [ ] `grep -n "caskTokens" app/src/main.ts` returns nothing
- [ ] `git status --short` shows changes only in the in-scope files
- [ ] `plans/README.md` status row updated

## STOP conditions

- The excerpts above do not match the live code (011/012 not merged, or
  drifted).
- `https://formulae.brew.sh/api/cask.json` is unreachable from the executor
  environment — the Python tests still pass (they are offline), so finish
  Steps 1–5 but report that the smoke commands could not run.
- Styling rows would need a Tauri plugin, CSP change or asset scope — it
  must not; `read_font` already serves cached files.
- You feel the need to change `app/src-tauri/**`.

## Maintenance notes

- The index cache lives in `$TMPDIR/halfbold-app/cask-index.json` (19 MB,
  refreshed daily). If the formulae API changes shape, `font_cask_entries`
  and `cask_info_from_payload` are the only readers.
- Faces are downloaded once per token into `faces/<token>/`; the temp dir
  is wiped on reboot, which is fine.
- Deferred: styling non-Google casks before preview (would need multi-MB
  downloads per row); showing a spinner per row while a face loads.
