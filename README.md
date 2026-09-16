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

Build or refresh Half versions of every eligible font in `~/Library/Fonts` (variable fonts with a weight axis, or Regular + Bold pairs; italics and existing Half fonts are skipped):

```sh
uv run halfbold --all            # builds what is missing or older than its source
uv run halfbold --all --dry-run  # show the plan
uv run halfbold --all --force    # rebuild everything
```

Run it after `brew upgrade` and new or updated fonts get a Half twin.

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
