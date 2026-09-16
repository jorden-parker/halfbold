# Plan 012: Build a small Tauri desktop app (`app/`) that lists, previews, converts and installs fonts with real half-bold rendering

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7b9c258..HEAD -- src/halfbold/api.py .gitignore README.md`
> Plan 011 must be DONE (check `plans/README.md`) and
> `uv run halfbold-api web` must print JSON before you start. If any in-scope
> file changed since this plan was written, compare the "Current state"
> excerpts against the live code before proceeding; on a mismatch, treat it
> as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (new toolchain — Rust + Tauri; new top-level directory `app/`; it spawns `uv`, `brew` and writes into `~/Library/Fonts` only through the existing `halfbold-api build` and `cask-install` paths)
- **Depends on**: plans/011-json-api-for-the-app.md
- **Category**: direction
- **Planned at**: commit `7b9c258`, 2026-09-16

## Why this matters

The maintainer asked for "a small web app using tauri or something" that
takes font searching, installation and conversion out of the terminal so
fonts can be **previewed**. A terminal cannot render glyphs; the current
preview (`halfbold --preview`, Pillow drawing a PNG into the kitty graphics
protocol) only simulates the half-bold effect and does not work inside tmux
without passthrough. A WebKit webview renders the real `-Half.ttf` with
`font-feature-settings: "calt"`, exactly as Chrome will show it, next to the
plain source font.

The app is a thin shell: all font logic stays in Python and is reached
through `halfbold-api` (plan 011). Rust does two things only — run that
command and hand font bytes to the webview. The frontend is vanilla
TypeScript + Vite, no framework, so it stays small and readable.

Earlier plans 005/006 (a browser tab preview) were rejected on 2026-09-16
because the maintainer did not want a web page opening in the browser. A
native window is what was asked for now; that rejection does not apply.

## Current state

### Repo facts

- Repo root `/Users/jorden/src/halfbold` (use `git rev-parse --show-toplevel`,
  never hard-code this in code). Python engine in `src/halfbold/`, driven
  with `uv run --project <repo> …`. Go TUI in `tui/` (unchanged by this plan).
- Conventions (`AGENTS.md`): **no code comments** in any language; name
  things well instead. Conventional Commits. After changes run the Python
  checks (`uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest`) even though this plan adds no Python — the pre-commit hook
  in `.githooks/pre-commit` runs them.
- Toolchains present on the maintainer's machine (checked 2026-09-16):
  node 26.6.0, pnpm 10.15.0, bun 1.3.14, go 1.27.1, uv 0.12.1, Homebrew at
  `/opt/homebrew/bin`, Xcode Command Line Tools at
  `/Library/Developer/CommandLineTools`. Rust 1.98.1 via Homebrew rustup at
  `/opt/homebrew/opt/rustup/bin` (keg-only, not on `PATH`) — see Step 0.
- `.gitignore` today:
  ```
  # Python-generated files
  __pycache__/
  *.py[oc]
  build/
  dist/
  wheels/
  *.egg-info

  # Virtual environments
  .venv

  # Go
  tui/halfbold-tui
  tui/tui
  ```
  Note `dist/` and `build/` are already ignored at any depth.

### The backend contract (from plan 011)

`uv run --project <repo> halfbold-api <subcommand> [args]` prints one JSON
object to stdout, exit 0; on failure prints `{"error": "…"}`, exit 1.

Candidate object:
```json
{"family": "Inter", "kind": "sans", "regular": "/…/InterVariable.ttf",
 "bold": null, "output": "/…/Inter-Half.ttf", "built": true, "stale": false}
```

| Subcommand | Args | Returns |
|---|---|---|
| `installed` | `--fonts-dir DIR` (optional) | `{"fonts_dir", "candidates": [candidate…]}` |
| `build` | `REGULAR [BOLD] -o OUTPUT` | `{"output", "letters"}` |
| `preview` | `REGULAR [BOLD]` | `{"family", "kind", "regular", "bold", "half"}` (`half` is a cached temp `-Half.ttf`) |
| `casks` | — | `{"casks": ["font-…", …]}` (about 2600 entries, ~1.5 s) |
| `cask-fonts` | `TOKEN` | `{"token", "candidates": [candidate…]}` (downloaded, not installed) |
| `cask-install` | `TOKEN` | `{"token", "candidates": [candidate…]}` (installed into `~/Library/Fonts`) |
| `web` | `[KIND FAMILY]` | `{"sans": "…", "serif": "…", "mono": "…"}` |

`brew install` can take 10–60 s; `build` 1–5 s; `preview` of a variable
font up to ~10 s (instancing). Every call must run off the UI thread.

### Tauri 2 facts you will rely on

- Scaffold: `pnpm create tauri-app` (vanilla-ts template) creates
  `index.html`, `src/main.ts`, `src/styles.css`, `package.json`
  (`dev`, `build` = `tsc && vite build`, `tauri`), `vite.config.ts`,
  `tsconfig.json`, and `src-tauri/` with `Cargo.toml`, `build.rs`,
  `tauri.conf.json`, `capabilities/default.json`, `icons/`, `src/main.rs`,
  `src/lib.rs` (which registers a sample `greet` command).
- Commands: `#[tauri::command] async fn name(...)` registered via
  `tauri::generate_handler![...]`; call from TS with
  `import { invoke } from "@tauri-apps/api/core"`. `async` commands run on a
  thread pool, so blocking `std::process::Command` inside them does not
  freeze the window.
- Raw bytes: a command returning `tauri::ipc::Response::new(Vec<u8>)`
  arrives in JS as an `ArrayBuffer` (`invoke<ArrayBuffer>(…)`). Confirmed in
  the Tauri v2 docs ("Return Optimized Array Buffer", `develop/calling-rust`).
- A `.app` launched from Finder gets `PATH=/usr/bin:/bin:/usr/sbin:/sbin`;
  `uv` and `brew` live in `/opt/homebrew/bin`. Resolve them explicitly.
- Fonts in the webview: `new FontFace(alias, arrayBuffer)` +
  `document.fonts.add(face)`; then `font-family: alias`. Give each loaded
  file a fresh alias so a rebuilt `-Half.ttf` is never served from cache.

## Commands you will need

| Purpose | Command (run from repo root unless noted) | Expected on success |
|---|---|---|
| Rust present | `cargo --version` | prints `cargo 1.x` |
| Frontend deps | `cd app && pnpm install` | exit 0 |
| Typecheck + bundle | `cd app && pnpm build` | exit 0, `app/dist/` written |
| Rust check | `cargo check --manifest-path app/src-tauri/Cargo.toml` | exit 0 |
| Rust tests | `cargo test --manifest-path app/src-tauri/Cargo.toml` | all pass |
| Run app (dev) | `cd app && pnpm tauri dev` | a window titled "halfbold" opens |
| Bundle | `cd app && pnpm tauri build` | `app/src-tauri/target/release/bundle/macos/halfbold.app` exists |
| Python checks | `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` | exit 0 |

## Suggested executor toolkit

- Tauri v2 docs: https://v2.tauri.app/develop/calling-rust/ (commands, raw
  responses), https://v2.tauri.app/start/create-project/ (scaffold).
- If the `frontend-design` or `geist` skill is available, use it only for
  `styles.css` — keep the DOM structure exactly as specified here.

## Scope

**In scope** (the only files you should create or modify):
- `app/**` (create — the whole Tauri project)
- `.gitignore` (add `app/node_modules/`, `app/src-tauri/target/`)
- `README.md` (new `## App` section; leave other sections alone)

**Out of scope** (do NOT touch):
- `src/halfbold/**`, `tests/**`, `pyproject.toml`, `uv.lock` — if the API is
  missing something, STOP and report; do not patch Python here.
- `tui/**`, `chrome-extension/**`, `scripts/**`.
- Any Tauri plugin beyond what the template installs. No `tauri-plugin-shell`,
  no `tauri-plugin-fs`, no asset-protocol scope — bytes go through
  `read_font`.

## Git workflow

- Branch: `advisor/012-tauri-app`
- Commit per step, Conventional Commits, e.g.
  `feat: scaffold the halfbold desktop app`,
  `feat: app previews the real Half font next to its source`.
- Do NOT push or open a PR unless the operator instructed it.
- `pnpm-lock.yaml` and `src-tauri/Cargo.lock` **are committed**.

## Steps

### Step 0: Confirm the Rust toolchain

Rust was installed on 2026-09-16 with Homebrew's keg-only `rustup`
(`brew install rustup`, then `rustup toolchain install stable` and
`rustup default stable`). Its binaries live in
`/opt/homebrew/opt/rustup/bin`, **not** in `~/.cargo/bin`, and that
directory is not on `PATH` by default. Before every cargo/tauri command in
this plan run:

```sh
export PATH="/opt/homebrew/opt/rustup/bin:$PATH"
```

(fish: `fish_add_path /opt/homebrew/opt/rustup/bin`.) `pnpm tauri …`
inherits the shell's `PATH`, so set it once per shell.

**Verify**: `cargo --version` → `cargo 1.98.1` (or newer); `rustc --version` → `rustc 1.98.1` (or newer).

If `cargo` is still not found: **STOP and report**; do not install anything.

### Step 1: Scaffold `app/`

From the repo root:

```sh
pnpm create tauri-app app --template vanilla-ts --manager pnpm --identifier com.jorden.halfbold --yes
```

If the flags are rejected by the installed `create-tauri-app` version, run
`pnpm create tauri-app` interactively and answer: project name `app`,
identifier `com.jorden.halfbold`, language TypeScript/JavaScript, package
manager pnpm, UI template Vanilla, flavor TypeScript.

Then:

```sh
cd app && pnpm install
```

Edit `app/src-tauri/tauri.conf.json`:
- `"productName": "halfbold"`, `"identifier": "com.jorden.halfbold"`.
- In `app.windows[0]`: `"title": "halfbold"`, `"width": 1180`,
  `"height": 760`, `"minWidth": 900`, `"minHeight": 560`.
- Leave `build.beforeDevCommand` (`pnpm dev`), `build.devUrl`
  (`http://localhost:1420`), `build.beforeBuildCommand` (`pnpm build`) and
  `build.frontendDist` (`../dist`) as generated.

Append to the root `.gitignore`:

```
# Tauri app
app/node_modules/
app/src-tauri/target/
```

**Verify**: `cd app && pnpm build` → exit 0; `cargo check --manifest-path app/src-tauri/Cargo.toml` → exit 0 (first run compiles Tauri; several minutes is normal). `git status --short` shows only `app/` and `.gitignore`.

### Step 2: Replace the Rust side

Overwrite `app/src-tauri/src/lib.rs` with exactly two commands plus helpers.
Delete the template's `greet` and any sample HTML/TS that called it. Keep
`main.rs` as generated (it calls `app_lib::run()` or similar — match the
generated name).

```rust
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::Value;

const HOMEBREW_BIN_DIRS: [&str; 2] = ["/opt/homebrew/bin", "/usr/local/bin"];

fn tool_path(name: &str) -> PathBuf {
    for dir in HOMEBREW_BIN_DIRS {
        let candidate = Path::new(dir).join(name);
        if candidate.exists() {
            return candidate;
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let candidate = Path::new(&home).join(".local/bin").join(name);
        if candidate.exists() {
            return candidate;
        }
    }
    PathBuf::from(name)
}

fn repo_root() -> PathBuf {
    if let Ok(root) = std::env::var("HALFBOLD_REPO") {
        return PathBuf::from(root);
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .join("../..")
        .canonicalize()
        .unwrap_or(manifest_dir)
}

fn api_error(value: &Value, stdout: &str, stderr: &str) -> String {
    match value.get("error").and_then(Value::as_str) {
        Some(message) => message.to_string(),
        None => format!("halfbold-api failed\n{stdout}\n{stderr}"),
    }
}

#[tauri::command]
async fn api(args: Vec<String>) -> Result<Value, String> {
    let output = Command::new(tool_path("uv"))
        .arg("run")
        .arg("--project")
        .arg(repo_root())
        .arg("halfbold-api")
        .args(&args)
        .output()
        .map_err(|err| format!("could not run uv: {err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let value: Value = serde_json::from_str(stdout.trim())
        .map_err(|_| format!("halfbold-api did not return JSON\n{stdout}\n{stderr}"))?;
    if output.status.success() {
        Ok(value)
    } else {
        Err(api_error(&value, &stdout, &stderr))
    }
}

#[tauri::command]
async fn read_font(path: String) -> Result<tauri::ipc::Response, String> {
    let lowered = path.to_lowercase();
    if !(lowered.ends_with(".ttf") || lowered.ends_with(".otf")) {
        return Err(format!("{path} is not a font file"));
    }
    let bytes = std::fs::read(&path).map_err(|err| format!("{path}: {err}"))?;
    Ok(tauri::ipc::Response::new(bytes))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![api, read_font])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn api_error_prefers_json_message() {
        let value: Value = serde_json::from_str(r#"{"error":"boom"}"#).unwrap();
        assert_eq!(api_error(&value, "", ""), "boom");
    }

    #[test]
    fn api_error_falls_back_to_output() {
        let value = Value::Null;
        let message = api_error(&value, "out", "err");
        assert!(message.contains("out") && message.contains("err"));
    }

    #[test]
    fn repo_root_has_pyproject() {
        assert!(repo_root().join("pyproject.toml").exists());
    }
}
```

If the generated template registers `tauri_plugin_opener` (or any plugin)
in `run()`, remove the plugin from `run()`, from `Cargo.toml`, from
`capabilities/default.json` and from `package.json` — this app needs only
`core:default`. Make sure `serde_json` is in `[dependencies]` of
`app/src-tauri/Cargo.toml` (the template adds it; add `serde_json = "1"` if
not).

**Verify**: `cargo test --manifest-path app/src-tauri/Cargo.toml` → 3 tests pass. `cargo check --manifest-path app/src-tauri/Cargo.toml` → exit 0.

### Step 3: Frontend — API client and font loader

Create `app/src/api.ts`:

```ts
import { invoke } from "@tauri-apps/api/core";

export type Kind = "sans" | "serif" | "mono";
export const KINDS: Kind[] = ["sans", "serif", "mono"];

export interface Candidate {
  family: string;
  kind: Kind;
  regular: string;
  bold: string | null;
  output: string;
  built: boolean;
  stale: boolean;
}

export interface Preview {
  family: string;
  kind: Kind;
  regular: string;
  bold: string | null;
  half: string;
}

export type WebFonts = Record<Kind, string>;

async function api<T>(...args: string[]): Promise<T> {
  return invoke<T>("api", { args });
}

export function installed() {
  return api<{ fonts_dir: string; candidates: Candidate[] }>("installed");
}

export function build(c: Candidate) {
  const args = ["build", c.regular];
  if (c.bold) args.push(c.bold);
  return api<{ output: string; letters: number }>(...args, "-o", c.output);
}

export function preview(c: Candidate) {
  const args = ["preview", c.regular];
  if (c.bold) args.push(c.bold);
  return api<Preview>(...args);
}

export function casks() {
  return api<{ casks: string[] }>("casks");
}

export function caskFonts(token: string) {
  return api<{ token: string; candidates: Candidate[] }>("cask-fonts", token);
}

export function caskInstall(token: string) {
  return api<{ token: string; candidates: Candidate[] }>("cask-install", token);
}

export function webFonts(kind?: Kind, family?: string) {
  return kind && family ? api<WebFonts>("web", kind, family) : api<WebFonts>("web");
}

export function readFont(path: string) {
  return invoke<ArrayBuffer>("read_font", { path });
}
```

Create `app/src/fonts.ts`:

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

Every call reloads the file on purpose: a rebuilt `-Half.ttf` must replace
the old face. The previews are small, so the cost is invisible.

**Verify**: `cd app && pnpm build` → exit 0 (may warn that the modules are unused until Step 4).

### Step 4: Frontend — the UI

Replace `app/index.html` body with this structure (keep the generated
`<head>`; the script tag stays `<script type="module" src="/src/main.ts">`):

```html
<header>
  <h1>halfbold</h1>
  <nav>
    <button id="tab-installed" class="tab active">Installed</button>
    <button id="tab-brew" class="tab">Homebrew</button>
  </nav>
  <div id="slots"></div>
</header>
<main>
  <aside>
    <input id="filter" type="search" placeholder="Filter" autocomplete="off" />
    <ul id="list"></ul>
  </aside>
  <section id="detail">
    <p id="empty">Pick a font.</p>
    <div id="panel" hidden>
      <h2 id="title"></h2>
      <p id="meta"></p>
      <div id="actions"></div>
      <p id="status"></p>
      <h3>Half bold</h3>
      <p id="sample-half" class="sample"></p>
      <h3>Plain</h3>
      <p id="sample-plain" class="sample"></p>
    </div>
  </section>
</main>
```

Replace `app/src/main.ts`. Required behaviour, in this order of
implementation:

1. **State**: `tab: "installed" | "brew"`, `candidates: Candidate[]`,
   `caskTokens: string[]`, `selected: Candidate | string | null`,
   `web: WebFonts | null`, `busy: string | null` (label of the running job).
2. **Boot** (`init()`): call `installed()` and `webFonts()` in parallel;
   render the list and the slots line
   (`sans: Inter Half · serif: … · mono: …`). Errors go to `#status`
   as text, never to `alert()`.
3. **List rendering** (`renderList()`): for the Installed tab, one `<li>` per
   candidate matching the filter (case-insensitive substring on `family`):
   family, a `<span class="kind">` with the kind, and a `<span class="state">`
   reading `built`, `stale` or `not built`. For the Homebrew tab, one `<li>`
   per cask token matching the filter, capped at the first 200 matches with a
   trailing `<li class="more">… and N more</li>`. Clicking a row sets
   `selected` and calls `renderDetail()`.
4. **Installed detail**: title = family; meta =
   `kind · Regular + Bold pair` or `kind · variable font`, plus the file
   name(s). Actions:
   - `Build Half font` (label `Rebuild` when `built && stale`; hidden when
     built and fresh) → `build(c)` then reload `installed()` and re-render the
     preview.
   - `Use as sans` / `Use as serif` / `Use as mono` (disabled unless
     `built`) → `webFonts(kind, c.family)`; update the slots line.
   Preview: call `preview(c)`; `loadFace(p.half)` → `#sample-half` gets
   `style.fontFamily = alias; style.fontFeatureSettings = '"calt" 1'`;
   `loadFace(p.regular)` → `#sample-plain` gets `style.fontFamily = alias;
   style.fontWeight = "400"`. Both samples show `SAMPLE_TEXT`:
   > The quick brown fox jumps over the lazy dog. Reading gets faster when the first half of every word is bold, because your eyes only need the start of a word to recognise it.
   (Same text as `src/halfbold/preview.py` `SAMPLE_TEXT`.)
   Note: for a font that already has a built `-Half.ttf` in the fonts folder,
   still preview through `preview(c)` — it renders the cached temp copy, so
   the preview always reflects the current source even when the installed
   Half font is stale.
5. **Homebrew detail**: title = token; actions `Preview` and `Install`.
   - `Preview` → `caskFonts(token)`; take `candidates[0]` and render exactly
     like an Installed preview; meta lists every family found
     (`Roboto (sans) · Roboto Serif (serif)`).
   - `Install` → `caskInstall(token)`; then for each returned candidate call
     `build(c)`; then reload `installed()`, switch to the Installed tab and
     select the first installed family.
6. **Busy handling**: while any API call runs, `busy` holds a label
   (`Building Inter Half…`, `Installing font-roboto…`,
   `Loading casks…`); `#status` shows it and every action button gets
   `disabled`. Clear on finish; on error show `Error: <message>`.
7. **Casks load lazily**: the first click on the Homebrew tab calls
   `casks()` once and caches the tokens.

Keyboard: `↑`/`↓` move the selection within the list, `Enter` on the
Installed tab triggers Build, `/` focuses the filter. Nothing else.

`app/src/styles.css`: replace the template CSS. Layout: `header` as a
flex row; `main` as a two-column grid (`280px 1fr`); `aside` scrolls;
`.sample` at `font-size: 22px; line-height: 1.5; max-width: 60ch`. Respect
`prefers-color-scheme: dark` with a dark background and light text. System
UI font for chrome (`font-family: system-ui`). Nothing else is required —
keep it under ~120 lines.

**Verify**: `cd app && pnpm build` → exit 0 with no TypeScript errors.
Then `cd app && pnpm tauri dev` and check by hand:
- window opens, Installed list shows the same families as
  `uv run halfbold-api installed` (compare counts);
- selecting a family renders two paragraphs in that family, the first with
  bold word starts;
- Homebrew tab lists `font-inter` when `inter` is typed in the filter;
- Preview on a Google Fonts cask (e.g. `font-roboto`) shows the Roboto
  sample within ~15 s.
Close the window; `pnpm tauri dev` exits 0.

### Step 5: Bundle and document

Run `cd app && pnpm tauri build`. The bundle lands at
`app/src-tauri/target/release/bundle/macos/halfbold.app`. Open it with
`open app/src-tauri/target/release/bundle/macos/halfbold.app` and confirm the
Installed list loads (this is the Finder-PATH check for `tool_path`).

Add to `README.md`, directly before `## Develop`:

```markdown
## App

A small Tauri window that lists every convertible font, previews the real
half-bold result next to the plain font, builds the Half twin, installs
Homebrew font casks, and points the Chrome extension's sans/serif/mono slots
at a family. It drives `halfbold-api` under the hood, so the Python package
stays the only place with font logic.

```sh
cd app && pnpm install && pnpm tauri dev      # develop
cd app && pnpm tauri build                    # app/src-tauri/target/release/bundle/macos/halfbold.app
```

Needs Rust (`brew install rustup && rustup toolchain install stable && rustup default stable`,
then put `/opt/homebrew/opt/rustup/bin` on `PATH`), pnpm and `uv`. Set
`HALFBOLD_REPO=/path/to/halfbold` if the built app is moved away from the
repo checkout.
```

**Verify**: `open app/src-tauri/target/release/bundle/macos/halfbold.app` shows the list. `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → exit 0 (nothing Python changed; the hook still runs them).

## Test plan

- Rust: the three unit tests in Step 2 (`cargo test`).
- TypeScript: `pnpm build` (`tsc` strict mode from the template) is the
  gate; no test runner is added.
- Manual: the Step 4 and Step 5 checklists. Record what you saw in the
  status row (e.g. "previewed Inter and font-roboto in dev; .app launched
  from Finder").

## Done criteria

- [ ] `cargo test --manifest-path app/src-tauri/Cargo.toml` passes 3 tests
- [ ] `cd app && pnpm build` exits 0
- [ ] `cd app && pnpm tauri build` produces `app/src-tauri/target/release/bundle/macos/halfbold.app`
- [ ] `grep -rn "greet" app/src app/src-tauri/src` returns nothing
- [ ] `grep -n "tauri-plugin" app/src-tauri/Cargo.toml` returns nothing
- [ ] `git status --short` shows changes only under `app/`, `.gitignore`, `README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `cargo` is missing even with `/opt/homebrew/opt/rustup/bin` on `PATH` (Step 0).
- `pnpm create tauri-app` produces a layout without `src-tauri/src/lib.rs`
  or without `tauri.conf.json` v2 keys (`app.windows`, `build.frontendDist`).
- `invoke<ArrayBuffer>("read_font")` returns something other than an
  `ArrayBuffer` in the running app (check with `instanceof ArrayBuffer` in
  the console) — the Tauri version differs from the docs this plan relied on.
- `halfbold-api` lacks a subcommand listed in the contract table — plan 011
  is incomplete; do not add Python here.
- The dev window opens but every API call fails with "could not run uv":
  report the `PATH` and the output of `ls /opt/homebrew/bin/uv`.
- You need a Tauri plugin or an asset-protocol scope to make fonts load.

## Maintenance notes

- `app/src/api.ts` mirrors the `halfbold-api` JSON contract; change both
  together.
- `tool_path` hard-codes Homebrew's prefixes. If `uv` moves (e.g. installed
  via its own installer to `~/.local/bin`), it is still found; anything else
  needs a new entry.
- Preview builds land in `$TMPDIR/halfbold-app/`; the app never writes to
  `~/Library/Fonts` except through `build` (explicit button) and
  `cask-install`.
- Deferred: an app icon (template placeholder icons are fine for a personal
  tool), a font-size slider, and showing the italic/other styles. Also
  deferred: removing the Go TUI and the terminal preview — plan 013.
- Reviewer focus: the `async fn` on both commands (a sync `api` would freeze
  the window for the duration of `brew install`), and that no code path
  passes user-typed text to a shell — `Command` takes argv, never a string.
