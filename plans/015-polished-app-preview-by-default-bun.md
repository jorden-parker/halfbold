# Plan 015: Polish the desktop app, preview every selection by default, serve `halfbold-api` once, and build the frontend with Bun

> **Status**: prototyped on branch `feat/015-polish-preview-bun` (worktree
> `.claude/worktrees/015`) on 2026-09-16, straight from a grilling session.
> This file records the decisions and what shipped, so a reviewer can check
> the branch against it.

## Decisions (maintainer, 2026-09-16)

- **Preview by default**: selecting any row previews it. On the Homebrew tab
  that means the cask is downloaded on select, no Preview button. On launch
  the first installed font is selected.
- **Downloads are cached and prefetched**: `cask-fonts` reuses already
  downloaded files instead of wiping them each call, the cache moved from
  `/tmp/halfbold-app` to `~/Library/Caches/halfbold` so it survives, and
  hovering a Google Fonts row fetches it in the background. Non-Google casks
  still fetch their whole archive on select (hundreds of MB for some), so
  they are not prefetched.
- **Faster**: the maintainer chose Bun's bundler and dev server (no Vite) and
  a fix for the real latency, which was one `uv run` per call (0.3 to 0.8 s).
  The Rust side now keeps one `halfbold-api serve` child and speaks JSON lines
  to it, so Python and fontTools start once per app run.
- **Appearance**: "looks hacked together" was the complaint. Direction is a
  type specimen app: the font is the hero, the chrome is quiet macOS-style
  (segmented control, sidebar, status bar).

## What changed

- `src/halfbold/api.py`: `serve` subcommand (threaded, id-matched replies),
  `cached_cask_fonts`, `default_cache_dir`. Tests in `tests/test_api.py`.
- `app/src-tauri/src/lib.rs`: `Backend` state with a respawning `Server`;
  `api` command routes through it. Unit tests include a real round trip.
- `app/index.html`, `app/src/styles.css`, `app/src/main.ts`: new layout,
  selection keys with `stillSelected` guards after every await, editable
  specimen text persisted in `localStorage`, slot buttons show the active
  slot, status bar carries progress and slots.
- `app/package.json`, `app/src-tauri/tauri.conf.json`: Bun scripts,
  `devUrl` is `http://127.0.0.1:1420` so another dev server on IPv6
  `localhost` cannot hijack the window. Vite config, pnpm lockfile and
  template assets removed.
- `README.md`, `app/README.md`, `CONTEXT.md` (new glossary).

## Verification done

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`
  (74 passed).
- `cargo test --lib` in `app/src-tauri` (5 passed, one spawns Python).
- `bun run build` (tsc clean, 12 KB bundle).
- `bun tauri dev`: Installed tab screenshot checked; empty state and panel
  no longer overlap. Homebrew tab exercised through the API only
  (`cask-fonts font-afacad`: 1.9 s cold, 0.36 s cached).

## Still to check by hand

- Homebrew tab in the running app: select a Google Fonts row and a non-Google
  row, confirm the pending message, then the specimen, then Install.
- Light mode.
- `bun tauri build` and launch the bundled .app.
