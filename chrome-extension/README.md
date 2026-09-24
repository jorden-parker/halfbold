# halfbold Chrome extension

Applies locally installed Half fonts to websites, with live updates to open tabs.

## Desktop setup

Open the desktop app, select a font, and click **Use in browser**. The app builds
and installs its Half font and uses it for text (or code for monospace fonts).
**Choose slot** exposes the individual sans, serif and mono slots.

On first use, the app opens Chrome and copies the extension folder path:

1. Enable **Developer mode** in `chrome://extensions` and click **Load unpacked**.
2. Press **Cmd+Shift+G**, paste, and select the folder.

The app shows **Chrome connected · font settings received** after Chrome
acknowledges the current settings. Font switches then update open pages without
refreshing. Chrome's own pages, the Chrome Web Store and other protected pages
cannot be styled. Closed shadow roots are inaccessible.

If upgrading from the older extension, remove the old halfbold entry before
loading this version. The extension now has a stable ID and lives in
`~/Library/Application Support/halfbold/browser/extension`.

## Command-line setup

```sh
./chrome-extension/install.sh
```

This performs the same setup. Existing commands such as
`uv run halfbold --sans "Inter"` also deliver live updates.

## Connection

Setup registers `com.jorden.halfbold` as a Chrome native messaging host for this
extension only. Chrome starts a small Python process that watches the source CSS
and pushes changes within 150 ms of detecting them. The extension caches the
latest stylesheet, updates open tabs and frames, and updates adopted stylesheets
in open shadow roots. No local HTTP server is needed. Chrome owns the connection,
so the desktop app can be closed while browsing.

Connection status expires after six seconds without a heartbeat. It confirms
receipt of settings by the extension, not that every website permits styling.
The helper uses this checkout's Python interpreter and CSS path. After moving the
checkout or replacing its environment, run **Chrome setup** again.

## Extension development

Run setup again to copy extension code changes to the installed folder, then
click **Reload** on the extension in Chrome. Font choices update live; JavaScript
and manifest edits require an extension reload. With a checkout loaded directly,
register the host through setup and reload that extension instead.

Some sites set `text-rendering: optimizeSpeed`, which skips contextual alternates.
The stylesheet forces `optimizeLegibility` and `calt` to preserve half-bold text.
