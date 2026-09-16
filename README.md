# halfbold

Turn any Regular + Bold TrueType pair into a bionic-reading font.

```sh
uv run halfbold Inter-Regular.ttf Inter-Bold.ttf -o Inter-Half.ttf
uv run halfbold InterVariable.ttf -o ~/Library/Fonts/Inter-Half.ttf
```

## Interactive picker

A small Bubble Tea TUI lists the Regular + Bold pairs and variable TrueType fonts in `~/Library/Fonts` and runs `halfbold` on the one you pick:

```sh
go run -C tui . -project ..
```

`-fonts DIR` (repeatable) scans other directories; `-out-dir DIR` writes the `-Half.ttf` somewhere other than next to the source font.

Each row shows the font's kind (`sans`, `serif`, `mono`). Press `s` on a row to make its Half font the Chrome extension's font for that kind (`1`/`2`/`3` pick a different slot); this runs `halfbold --sans/--serif/--mono` and the extension reloads itself within 30 seconds.

Press `p` to preview the highlighted font: the sample paragraph is drawn into the terminal half-bold and plain (see the `--preview` section below for terminal requirements); enter brings the picker back.

Press `i` to install a font from a Homebrew cask (`brew search --cask font-`) without leaving the picker. After `brew install --cask` finishes, the new font is converted straight away; when a cask ships several families you pick one first.

Build or refresh Half versions of every eligible font in `~/Library/Fonts` (variable fonts with a weight axis, or Regular + Bold pairs; italics and existing Half fonts are skipped):

```sh
uv run halfbold --all            # builds what is missing or older than its source
uv run halfbold --all --dry-run  # show the plan
uv run halfbold --all --force    # rebuild everything
```

Point the Chrome extension at a different Half font. Each web page slot
(`sans`, `serif`, `mono`) maps to one installed Half family; the extension
reloads itself within 30 seconds:

```sh
uv run halfbold --all --dry-run                 # shows each family's kind
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
```

Inside tmux add `set -g allow-passthrough on` to `tmux.conf` (tmux ≥ 3.3)
so the image reaches the terminal.

Or let launchd do it. This installs a user agent that watches `~/Library/Fonts` and runs `halfbold --all` whenever anything in it changes, so `brew upgrade`, a Font Book install, or a manual copy all produce Half twins within about 30 seconds:

```sh
scripts/install-watcher.sh
```

Log: `~/Library/Logs/halfbold.log`. The script prints the removal command.

A single variable font is instanced at weight 400 and 700 (`--regular-weight`, `--bold-weight` to change). Output written into `~/Library/Fonts` is installed immediately on macOS.

Fonts from Homebrew work directly:

```sh
brew install --cask font-inter font-source-serif-4
uv run halfbold ~/Library/Fonts/InterVariable.ttf -o ~/Library/Fonts/Inter-Half.ttf
```

Install the output, then turn on contextual alternates (`calt`) in the app. Most apps have it on by default. In CSS: `font-feature-settings: "calt"`.

## Develop

```sh
uv sync
git config core.hooksPath .githooks
uv run pytest
uv run ruff check . && uv run ruff format .
go -C tui vet ./... && go -C tui test ./...
```
