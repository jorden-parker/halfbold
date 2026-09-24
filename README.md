# halfbold

Turn any Regular + Bold TrueType pair into a bionic-reading font.

```sh
uv run halfbold Inter-Regular.ttf Inter-Bold.ttf -o Inter-Half.ttf
uv run halfbold InterVariable.ttf -o ~/Library/Fonts/Inter-Half.ttf
```

## Everyday commands

Run these from this checkout:

```sh
uv run halfbold rebuild          # rebuild every eligible font using saved settings
uv run halfbold desktop          # launch the desktop app
uv run halfbold sync             # build only missing or stale Half fonts
uv run halfbold list             # show the build plan and each font's kind; write nothing
```

These scan `~/Library/Fonts`. Add `--fonts-dir DIR` to scan another folder,
or `--dry-run` to preview a rebuild. Italics and existing Half fonts are skipped.

For shorter commands from any directory, install once:

```sh
uv tool install --editable .
halfbold rebuild
halfbold sync
halfbold list
```

If `halfbold` is not on your PATH, run `uv tool update-shell` and open a new
terminal. The editable install follows changes in this checkout. Existing
`--all`, `--all --force`, and `--all --dry-run` commands still work.

## Interactive picker

A small Bubble Tea TUI lists the Regular + Bold pairs and variable TrueType fonts in `~/Library/Fonts` and runs `halfbold` on the one you pick:

```sh
go run -C tui . -project ..
```

`-fonts DIR` (repeatable) scans other directories; `-out-dir DIR` writes the `-Half.ttf` somewhere other than next to the source font.

Each row shows the font's kind (`sans`, `serif`, `mono`). Press `s` on a row to make its Half font the Chrome extension's font for that kind (`1`/`2`/`3` pick a different slot); this runs `halfbold --sans/--serif/--mono` and the connected extension updates open pages immediately.

Press `p` to preview the highlighted font: the sample paragraph is drawn into the terminal half-bold and plain (see the `--preview` section below for terminal requirements); enter brings the picker back. In the Homebrew list, `p` previews the cask before installing it (Google Fonts casks fetch only the needed files; other casks are downloaded to Homebrew's cache with `brew fetch`).

Press `i` to install a font from a Homebrew cask (`brew search --cask font-`) without leaving the picker. After `brew install --cask` finishes, the new font is converted straight away; when a cask ships several families you pick one first.

Point the Chrome extension at a different Half font. Each web page slot
(`sans`, `serif`, `mono`) maps to one installed Half family; the connected extension
updates open pages immediately:

```sh
uv run halfbold list                            # shows each family's kind
uv run halfbold --sans "Inter" --mono "JetBrainsMono Nerd Font"
```

Preview how a font will look half-bold without converting it. The sample
is drawn as an image straight into the terminal (kitty graphics protocol —
Ghostty, kitty, WezTerm); anywhere else it is written to a PNG whose path
is printed:

```sh
uv run halfbold --preview ~/Library/Fonts/InterVariable.ttf
uv run halfbold --preview ~/Library/Fonts            # every convertible font, up to three
uv run halfbold --preview Inter-Regular.ttf Inter-Bold.ttf --png inter.png
uv run halfbold --preview-cask font-roboto
```

`--preview-cask TOKEN` downloads the cask without installing it.

Inside tmux add `set -g allow-passthrough on` to `tmux.conf` (tmux ≥ 3.3)
so the image reaches the terminal.

Or let launchd do it. This installs a user agent that watches `~/Library/Fonts` and runs `halfbold sync` whenever anything in it changes, so `brew upgrade`, a Font Book install, or a manual copy all produce Half twins within about 30 seconds:

```sh
scripts/install-watcher.sh
```

Log: `~/Library/Logs/halfbold.log`. The script prints the removal command.

A single variable font is instanced at weight 400 and 700 (`--regular-weight`, `--bold-weight` to change). `--bold-share 0.4` bolds fewer letters per word and `--min-word-length 4` leaves short words plain; without flags, both come from the saved settings file. Output written into `~/Library/Fonts` is installed immediately on macOS.

Fonts from Homebrew work directly:

```sh
brew install --cask font-inter font-source-serif-4
uv run halfbold ~/Library/Fonts/InterVariable.ttf -o ~/Library/Fonts/Inter-Half.ttf
```

Install the output, then turn on contextual alternates (`calt`) in the app. Most apps have it on by default. In CSS: `font-feature-settings: "calt"`. The source font's own OpenType features (coding ligatures such as `->` and `!=`, stylistic sets) are kept.

## App

For browser fonts, select a font and click **Use in browser**. It builds and
installs the Half font, then applies it to browser text (or code for monospace).
First use guides you through loading the Chrome extension. The connection status
confirms when Chrome receives your settings; later font switches update open
pages without refreshing. **Choose slot** exposes the individual slots.
See [browser setup](chrome-extension/README.md) for upgrades and troubleshooting.


A small Tauri window that lists every convertible font, previews the real
half-bold result next to the plain font, builds the Half twin, installs
Homebrew font casks, and points the Chrome extension's sans/serif/mono slots
at a family. It drives `halfbold-api` under the hood, so the Python package
stays the only place with font logic. Homebrew casks are listed by font name
(from the Homebrew formulae index, cached for a day) and Google Fonts casks
are drawn in their own face; other casks pick up their face after a preview
or install. The Homebrew list only shows casks halfbold can convert, judged
from the font file names in the Homebrew index (TrueType, and either a
variable font or a Regular plus Bold pair). Selecting an installed font or a
Google Fonts cask previews it straight away; other casks show a "Download and
preview" button because they ship as whole archives. The sample text is
editable and remembered. Hovering a Google Fonts cask fetches it in the
background, and every download lands in `~/Library/Caches/halfbold`, so a
cask previews once per machine. Sliders above the specimen set the bold
share, the shortest word that gets bolded and, for variable fonts, the plain
and bold weights. They are saved to
`~/Library/Application Support/halfbold/settings.json`, which the CLI and the
launchd watcher read too, so every rebuild uses the same choices.

```sh
uv run halfbold desktop                      # launch from source
cd app && bun tauri build                     # app/src-tauri/target/release/bundle/macos/halfbold.app
```

`halfbold desktop` works from any directory after the editable install above.
It installs app dependencies, finds Rust in common Cargo/Homebrew locations,
and launches the app from this checkout. Keep the terminal open; Ctrl-C stops
the development session. The first launch compiles the app and takes longer.

The app keeps one `halfbold-api serve` process alive and sends it JSON
requests over stdin, so only the first call pays Python start-up.

Needs Rust (`brew install rustup && rustup toolchain install stable && rustup default stable`,
then put `/opt/homebrew/opt/rustup/bin` on `PATH`), Bun (`brew install bun`) and `uv`. Set
`HALFBOLD_REPO=/path/to/halfbold` if the built app is moved away from the
repo checkout.

## Develop

```sh
uv sync
git config core.hooksPath .githooks
uv run pytest
uv run ruff check . && uv run ruff format .
go -C tui vet ./... && go -C tui test ./...
```

`uv run halfbold-api <subcommand>` is the JSON interface the desktop app
(`app/`) drives: `installed`, `build`, `preview`, `casks`, `cask-fonts`,
`cask-face`, `cask-install`, `settings`, `web`. Each prints one JSON object; failures print
`{"error": …}` and exit 1. `serve` reads `{"id", "args"}` lines on stdin and
answers each with `{"id", "ok", "result" | "error"}`, running requests
concurrently.
