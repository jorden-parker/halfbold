# halfbold Chrome extension

Applies the half-bold fonts built by this repo to every website.

## Install

```sh
./chrome-extension/install.sh
```

Chrome 137+ removed the `--load-extension` flag, and only managed (MDM) Macs can force-install extensions by policy, so the first load is two clicks in `chrome://extensions`. The script opens that page, copies the folder path to the clipboard, and prints the two clicks.

## Reloading

Never needed by hand. `autoreload.js` runs as the background service worker, hashes the extension's own files every 30 seconds, and calls `chrome.runtime.reload()` when they change. Edit `halfbold.css`, wait up to 30 seconds, refresh the page.

## Change the fonts

Edit `halfbold.css`: the three variables at the top name the installed font families. Swap the sans rule's variable to `--halfbold-serif` to read everything in serif.

## Limit to some sites

Edit `matches` in `manifest.json`, e.g. `["https://*.wikipedia.org/*", "https://news.ycombinator.com/*"]`.

## Why the `text-rendering` rule

Some sites (GitHub among them) set `text-rendering: optimizeSpeed`, which makes Chrome skip contextual alternates entirely, so the font renders plain. The extension forces `optimizeLegibility` and `calt` on everywhere.

## Shadow DOM

Some sites render code blocks inside shadow roots (MDN's `<mdn-code-example>`, for one), where page CSS never reaches. `shadow.js` adopts the same stylesheet into every open shadow root it finds, and keeps watching for new ones. Closed shadow roots stay out of reach.
