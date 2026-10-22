# halfbold Chrome extension

Keeps every website's own fonts and swaps each one for its Half version: the
webfonts a site downloads, the installed fonts it names, and Chrome's default
fonts for `sans-serif`, `serif`, `monospace` and unstyled text.

## Desktop setup

Open the desktop app and click **Set up Chrome**. No font needs to be selected.
The app opens Chrome and copies the extension folder path:

1. Enable **Developer mode** in `chrome://extensions` and click **Load unpacked**.
2. Press **Cmd+Shift+G**, paste, and select the folder.

If halfbold is already loaded, click the reload button on its card instead.

The app shows **Chrome connected · converting page fonts (N faces converted,
M unchanged)** once Chrome has the current settings. Changing a setting in the
app (bold share, weights, …) reconverts open pages without refreshing.

## Command-line setup

```sh
./chrome-extension/install.sh
```

## How a page is converted

A Shadow face is a `FontFace` the extension adds to the page under the page's
own family name, built from the converted file. It is added after the page's
own `@font-face` rules, so for the same weight and style Chrome picks it
instead, and it hides an installed font of the same name. No element's
`font-family` is touched, so fallback order, weights, frames and dynamic
content keep working. Turning conversion off deletes the Shadow faces.

- **Webfonts**: the content script reads each `@font-face` rule, including
  cross-origin sheets, which the service worker fetches. For each family the
  page uses, the worker downloads the WOFF2/WOFF/TTF files and the native host
  builds a Half font from the face nearest the plain weight and the face
  nearest the bold weight (or one variable face). Only the plain face is
  shadowed; the page's own bold stays as it is.
- **Installed fonts**: the host builds the Half face and the Half Bold face
  from the installed family. Every other installed face of that family
  (Light, Italic, …) is re-added with `local()`, because shadowing hides them all.
- **Chrome's defaults**: the host installs Half versions of Chrome's default
  families into `~/Library/Fonts`, and the extension sets them through
  `chrome.fontSettings`. Reset clears them again.

Converted files live in `~/Library/Application Support/halfbold/browser/extension/fonts`,
keyed by source bytes and settings, so a font is converted once.

Unchanged, by design or limitation: CFF/OpenType-outline fonts, icon fonts
(mostly Private Use Area characters, or names like *Icons*, *Symbols*,
*Awesome*), families with only one weight, fonts added only through the
JavaScript `FontFace` API, `system-ui` and `-apple-system` (macOS's private
system font), canvas text, Chrome's own pages and protected pages, and closed
shadow roots.

## Connection

Setup registers `com.jorden.halfbold` as a Chrome native messaging host for
this extension only. Chrome starts `python -m halfbold.browser` from this
checkout's environment. The host sends the current configuration (on/off
plus a hash of the Settings) whenever either changes. It converts fonts on
two worker threads, so heartbeats keep flowing, and it gives up on a font
after 60 seconds. Chrome owns the connection, so the desktop app can be
closed while browsing.

Connection status expires after six seconds without a heartbeat. After moving
the checkout or replacing its environment, run **Chrome setup** again.

## Extension development

Run setup again to copy extension code changes to the installed folder, then
click **Reload** on the extension in Chrome. Run `bun test chrome-extension`
for the parsing helpers in `pagefonts-core.js`.

Some sites set `text-rendering: optimizeSpeed` or turn off contextual
alternates. The extension forces `optimizeLegibility` and `calt` so half-bold
text still renders.
