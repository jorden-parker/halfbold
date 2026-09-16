# halfbold Chrome extension

Applies the half-bold fonts built by this repo to every website.

## Install (unpacked, no store)

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and pick this `chrome-extension` folder.

## Change the fonts

Edit `halfbold.css`: the three variables at the top name the installed font families. Swap the `*` rule's variable to `--halfbold-serif` to read everything in serif. After editing, hit the reload icon on the extension card in `chrome://extensions`.

## Limit to some sites

Edit `matches` in `manifest.json`, e.g. `["https://*.wikipedia.org/*", "https://news.ycombinator.com/*"]`, then reload the extension.
