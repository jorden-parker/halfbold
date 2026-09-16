# halfbold

Turn any Regular + Bold TrueType pair into a bionic-reading font.

```sh
uv run halfbold Inter-Regular.ttf Inter-Bold.ttf -o Inter-Half.ttf
```

Install the output, then turn on contextual alternates (`calt`) in the app. Most apps have it on by default. In CSS: `font-feature-settings: "calt"`.

## Develop

```sh
uv sync
git config core.hooksPath .githooks
uv run pytest
uv run ruff check . && uv run ruff format .
```
