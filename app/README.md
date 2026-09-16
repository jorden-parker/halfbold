# halfbold app

Tauri 2 window over `halfbold-api`. Frontend is plain TypeScript, bundled and
served by Bun (`dev.ts` runs `Bun.serve` pinned to 127.0.0.1:1420 with HMR in
dev, `bun build ./index.html` for release). No framework, no Vite. The dev
server is pinned to IPv4 because Tauri's `devUrl` is `http://127.0.0.1:1420`
and a bare `localhost` bind can land on `::1`.

```sh
bun install
PATH=/opt/homebrew/opt/rustup/bin:$PATH bun tauri dev
PATH=/opt/homebrew/opt/rustup/bin:$PATH bun tauri build
```

- `src/main.ts` owns all state and rendering. A selection is identified by
  its key (`installed:<regular path>` or `brew:<token>`); every async render
  checks `stillSelected` after each await so a slow preview never paints over
  a newer selection.
- `src/fonts.ts` turns font files into `FontFace` aliases via the Rust
  `read_font` command.
- `src-tauri/src/lib.rs` keeps one `uv run halfbold-api serve` child per app
  process and matches replies to requests by id; it respawns the child if it
  exits.
