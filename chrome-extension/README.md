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

## Why the `text-rendering` rule

Some sites (GitHub among them) set `text-rendering: optimizeSpeed`, which makes Chrome skip contextual alternates entirely, so the font renders plain. The extension forces `optimizeLegibility` and `calt` on everywhere.

## Shadow DOM

Some sites render code blocks inside shadow roots (MDN's `<mdn-code-example>`, for one), where page CSS never reaches. `shadow.js` adopts the same stylesheet into every open shadow root it finds, and keeps watching for new ones. Closed shadow roots stay out of reach.
