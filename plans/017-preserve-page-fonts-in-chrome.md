# Plan 017: Make “Set up Chrome” convert each page's own fonts

Status: TODO

Planned at `783e51f`, 2026-10-06. Priority P1. Effort L. Risk HIGH (font discovery and browser rendering). Depends on the existing browser setup and native messaging implementation, already present at this commit.

Planning scope: targeted investigation, not a repository audit. No implementation or live Chrome verification was performed. Confirmed user requirement: preserve each webpage’s original typefaces, including fonts downloaded by the site, and convert each to its matching Half variant. This plan targets the broadest supported coverage; it cannot promise every font or every Chrome surface.

## Intended result

Click **Set up Chrome** without selecting a font. Complete Chrome's one-time **Load unpacked** step. Ordinary webpages keep their original typefaces, with each convertible face replaced by its corresponding Half font. A page using Inter for body text, Source Serif for headings and a custom downloaded code font retains those three choices. Missing conversions leave the original face intact.

Setup automatically inventories installed fonts and prepares eligible Half fonts. Downloaded fonts are converted on demand and cached locally. Closing the desktop app does not stop conversion. The current sans/serif/mono Slot controls remain available as an explicit **Use chosen fonts** mode; **Preserve website fonts** becomes the setup default. Existing users must be shown the mode change; do not silently discard their saved Slot choices.

The UI must distinguish **Chrome connected**, **Preparing fonts**, and **Active on this page: N faces converted, M unchanged**. Native-host acknowledgement alone is not evidence that a page is rendering Half fonts.

## Coverage contract

| Surface or source | Planned behavior |
| --- | --- |
| Installed TrueType fonts, including readable system locations | Map actual font names to verified Half faces; keep sources untouched. |
| Webfonts in TTF, WOFF and WOFF2 containers | Decode, require `glyf` outlines, find compatible weights/styles, convert and load a document-scoped alias. |
| Generic CSS families and Chrome's default webpage font | Resolve supported defaults through `chrome.fontSettings`; retain script/language distinctions and original fallback order. |
| Dynamic pages, permitted frames and open shadow roots | Apply the same mapping incrementally and reverse it when disabled. |
| Chrome toolbar/tabs, protected pages, closed shadow roots, PDF viewer, canvas text, CFF/CFF2 fonts and unresolved sources | Outside the supported conversion contract; report the reason where observable and preserve appearance. |

Font collections (`.ttc`/`.otc`) and inaccessible system aliases are also initially unsupported. Many system fonts use these forms, so do not label the inventory “all fonts converted.” WOFF2 is a container, not a guarantee of TrueType outlines. A static Regular font without a compatible Bold source cannot produce a faithful Half font. Do not fetch an unrelated family or synthesize a replacement silently.

Preserve weight, italic, stretch, language, Unicode coverage and relevant variable axes. Initially convert the configured plain/bold weight pair in supported styles; leave other face instances unchanged unless a verified matching pair can be produced. Do not assign one regular Half file to the entire 100–900 weight range or synthesize upright text for an italic face. Report this supported-subset boundary in setup details.

## Current state and conventions

`chrome-extension/halfbold.css:19` forces `font-family: var(--halfbold-sans), sans-serif !important`; line 24 forces the mono Slot on code. The serif Slot exists but is not selected by the current page rules. Lines 7–10 replace feature settings globally. These rules prevent detecting original typography after injection.

`chrome-extension/shadow.js` adopts one global stylesheet into the document and open shadow roots. It watches added elements, but not all style/font changes or late shadow attachment. `autoreload.js` connects to the native host, persists `liveStyle`, and broadcasts CSS. It does not discover faces or transport font bytes.

`src/halfbold/browser.py:46` implements `setup_browser`; it copies a fixed four-file extension bundle and a standalone copy of itself to Application Support. Its launcher executes that copied `host.py` with the source CSS path. Moving conversion into imported Python modules therefore requires updating the launcher, not just adding imports to the copied script. Keep the stable manifest key and extension ID.

`native_host` currently watches CSS and handles acknowledgements and heartbeat messages. `read_message` rejects bodies larger than 65,536 bytes. `browser_status` reports freshness and CSS revision, not page coverage. Existing tests in `tests/test_browser.py` demonstrate temporary home directories, binary protocol testing and subprocess shutdown.

`src/halfbold/scan.py:119` already scans the user, local, system and network font roots through `find_installed_candidates`, including nested TTF/OTF paths. It filters out CFF, existing Half fonts and italic faces; no collection support exists. `build_all` instead uses the narrower directory scanner: do not call it and claim the setup covered system fonts.

`src/halfbold/build.py` exposes `build_halfbold_font` and `load_font_pair`. It instances all non-weight axes at defaults and matches bold glyphs by glyph name. Independently subsetted webfonts can use incompatible glyph names, so webfont preparation must normalize the pair by Unicode identity before relying on this builder. Preserve the existing `GSUB`/`GPOS` behavior and camelCase rules.

`app/src/main.ts` contains `setupChrome`, `onUseAs`, and `showBrowserStatus`; `app/src/api.ts` defines their API types. `src/halfbold/api.py` exposes `browser --setup`. `tests/conftest.py` supplies small generated Regular/Bold and variable-font fixtures.

Use the existing domain terms Candidate, Half font, Slot and Settings. Python is managed by uv; the desktop app is plain TypeScript and Tauri with Bun. Source code carries no comments. Use descriptive names. Conventional Commit messages are required if committing; do not push or open a PR without an instruction to do so.

## Files in scope

1. Browser backend: `src/halfbold/browser.py`, `api.py`, `scan.py`; new `browser_fonts.py` and `webfonts.py`; narrowly required normalization changes in `build.py`; `pyproject.toml` and `uv.lock` for webfont decoding dependencies.
2. Extension: `chrome-extension/manifest.json`, `halfbold.css`, `shadow.js`, `autoreload.js`; new focused discovery, mapping and transport modules plus their Bun unit tests.
3. Desktop: `app/src/api.ts`, `main.ts`, `styles.css` and `app/index.html` for mode, preparation and coverage state. Reuse the current design.
4. Verification: `tests/test_browser.py`, `test_api.py`, `test_scan.py`; new `test_browser_fonts.py`, `test_webfonts.py`, `test_browser_acceptance.py`, fixtures under `tests/browser/`, and necessary test dependency metadata.
5. Documentation: root and extension READMEs, `CONTEXT.md` for the new browser mode vocabulary, this plan and `plans/README.md`.

Do not modify unrelated CLI/TUI commands, Homebrew flows, shaping policy, OS font configuration or Chrome profile files. Never overwrite original fonts. Browser-downloaded fonts belong in the cache, not `~/Library/Fonts`.

## Architecture decisions

Use the existing extension → native messaging → Python path. Avoid a localhost HTTP service. Conversion runs in bounded child processes so a slow or invalid font cannot stall heartbeats; the host owns the queue and serializes protocol writes.

Keep a versioned browser configuration separate from the legacy Slot CSS: mode, Settings revision, catalog revision and enabled state. Store configuration atomically under the existing Application Support browser directory. Font outputs live under `~/Library/Caches/halfbold/browser-fonts`, keyed by input bytes, face descriptors, conversion settings and builder version. Deduplicate concurrent work and evict unused entries with a 256 MiB default disk budget. A new configuration generation makes old conversion results ineligible for activation.

Expose native requests for catalog pages, conversion jobs, chunk upload/download, cancellation and page status. Include a protocol version, request ID and generation in every operation. Keep encoded chunk data at most 48 KiB and the entire JSON envelope below the current 64 KiB reader limit; validate actual encoded size. Enforce total input/output, decompression, job-count and time limits separately. Start with 16 MiB compressed input, 64 MiB decoded/output per face, two concurrent workers and a 30-second job timeout; surface oversize/timeouts as unchanged faces. Treat these as configurable implementation limits, not claims about all fonts.

Use extension-owned requests to fetch permitted remote stylesheet/font resources; the Python converter receives bytes or catalog IDs, never arbitrary URLs or page-selected filesystem paths. Validate sender tab/frame and request shape; allow bounded HTTP(S) font discovery, follow redirect permissions, and reject local-file schemes and arbitrary native operations. Do not forward page cookies or authorization headers. Resources needing unavailable credentials remain unchanged. Do not persist page text or browsing history.

### Discovery and mapping

Discover original family stacks and face descriptors before applying any Half rules. A computed `font-family` is a fallback list, not proof of which font rendered each glyph. Use declared `@font-face` records, exact installed-name aliases, and conservative fallback preservation. Do not insert a Half fallback ahead of an earlier unconverted available family. Prioritize a site's declared webfont over a same-named local font of unknown version.

Walk readable CSSOM, including active conditional rules and adopted sheets. When cross-origin CSSOM access is denied, let the worker fetch the linked stylesheet with host permission and parse it as CSS, resolving URLs against the final stylesheet URL. Bound import recursion and preserve weight, style, stretch and `unicode-range`. Do not use regex alone to parse CSS, quoted family lists or nested rules. FontFaceSet provides useful load notifications and descriptors, but does not expose arbitrary original font bytes: programmatic opaque/binary faces must be reported unresolved unless the feasibility test establishes a reliable capture path.

Generate collision-resistant document-scoped aliases and load only converted bytes. Preserve the original face descriptors and subset ranges; where subsets differ, assemble compatible source coverage before conversion or leave that subset unchanged. Normalize glyph identities using Unicode mappings, not raw WOFF glyph-order coincidence. Do not combine unrelated families or styles simply because their weight labels match.

Maintain an explicit record of extension-owned overrides. On class/style/theme changes, remove or suspend owned rules while measuring original styles; never derive the next mapping from already rewritten values. Batch work over affected subtrees, schedule between frames, and avoid full-document scans for every mutation. Observe font loading, stylesheet changes and open-root discovery; a bounded rescan is acceptable for late attached roots. Handle pseudoelement text conservatively without replacing icon fonts. Existing icon exclusions alone are insufficient because icon families are not consistently named.

Apply `calt` only to converted text, merging with existing feature settings and preserving unrelated stylistic sets. Restore original declarations exactly on disable and navigation. Original text nodes, selection, copying, inputs, accessibility and element identity must stay intact. For generic families, use `fontSettings` to read current defaults and match supported script/language cases; use document-level mappings so per-site disable restores the original page. Do not globally change browser defaults as a shortcut for this behavior.

## Execution steps

### 1. Prove font delivery and establish the fixture harness — 4–8 engineering hours

Create a reproducible real-extension harness in `tests/test_browser_acceptance.py` with fixtures under `tests/browser/`. Add opt-in execution through `HALFBOLD_BROWSER_TESTS=1`; ordinary pytest must not alter the user's Chrome profile or install a native host. Use an isolated browser environment capable of loading MV3 extensions, with the correct native-host path for that browser. Add a pytest-playwright development dependency if needed. A T3 preview is useful for inspection but may not load Chrome extensions; do not mistake a DOM-only preview for extension integration testing.

Prove converted font bytes can be received through messaging and loaded with `FontFace(alias, ArrayBuffer, descriptors)` into the document from the extension environment. Verify normal pages, `font-src 'none'`, frames and an open shadow root. If binary FontFace delivery is blocked in a context, record a precise unchanged reason; do not disable site CSP. Demonstrate two distinct font families and original fallback behavior with the current global replacement disabled in the fixture path.

Create unit tests runnable with `bun test chrome-extension` for family parsing, descriptor identity and protocol generation handling. Record browser/version and actual fixture results in this plan before moving on.

Verify: `HALFBOLD_BROWSER_TESTS=1 uv run pytest tests/test_browser_acceptance.py -q` → actual extension tests pass with zero skips; `bun test chrome-extension` → all unit tests pass. STOP if ordinary HTTP pages cannot reliably load the converted faces through this architecture.

### 2. Build an installed-face catalog and reliable conversion service — 8–16 engineering hours

Add the versioned catalog, configuration and native request handling. Reuse `find_installed_candidates` for the existing supported Candidate population; separately report unsupported discovered faces instead of hiding them from counts. Record family, typographic family, full and PostScript aliases without guessing from filenames. Keep file identity private behind catalog IDs. Build supported installed candidates with saved Settings into existing intended user output locations; use cache aliases where needed for descriptor-specific faces. Publish entries only after outputs validate and save atomically.

Make cache invalidation depend on source bytes and Settings, not just output mtimes. Prepare locally installed fonts in the background, with per-face results and retries. Update the native launcher to use a real package entry point with the configured interpreter; test execution outside the repository working directory. Preserve current native heartbeats and the legacy mode. Copy every required extension asset during setup.

Verify: `uv run pytest tests/test_browser.py tests/test_browser_fonts.py tests/test_scan.py tests/test_api.py -q` → pass, including system-root inventory, alias collision, changed Settings, duplicate requests, stale acknowledgements, truncated chunks, timeouts, restart, partial failure and setup rerun.

### 3. Preserve local typography across live pages — 12–20 engineering hours

Implement discovery/mapping and the two browser modes. Remove unconditional Slot CSS injection from preserve mode, including manifest injection; keep it available only in explicit chosen-font mode. Resolve verified local faces and supported generic defaults, then load/map matching Half faces. Preserve original fallback order, style, weight, metrics descriptors and feature settings. Keep bold and italic faces unchanged unless there is a matching converted face; no accidental synthetic replacement.

Apply updates to existing tabs and permitted frames as well as new documents. Handle SPA changes, class/style changes, responsive CSS, font loading and open shadow roots. Prevent feedback loops and discard stale asynchronous work. Add a per-site on/off control and restore page styling immediately when off. Maintain bounded in-memory page coverage and send truthful aggregate status to the app.

Verify: `bun test chrome-extension` and `HALFBOLD_BROWSER_TESTS=1 uv run pytest tests/test_browser_acceptance.py -q` → pass local-font, mixed-family, fallback, icon, feature-preservation, mutation, frame, shadow and disable fixtures. Each positive test must prove the loaded Half alias rendered, using browser font inspection where available plus shaping/visual evidence; computed family strings alone are insufficient.

### 4. Convert downloaded webfonts on demand — 16–32 engineering hours

Implement stylesheet discovery and bounded worker fetches. Add FontTools WOFF2 decoding dependencies explicitly. Normalize downloaded inputs into plain sfnt fonts before calling the builder (clear wrapper flavor on TTF output); check outlines and compatible glyph coverage. Support static Regular/Bold and variable `wght` sources, matching italic pairs when present. For variable sources preserve requested non-weight axes in the prepared instance; unsupported animated/continuous axis combinations remain original. Respect the configured plain/bold weights rather than silently introducing a different shaping policy.

Cache successful conversions by content and descriptors; negative-cache failures for the current generation with an explicit retry. Keep original fonts visible while work is pending. Activate only fully loaded replacements and keep page text readable on disconnect. Persist reusable font bytes in the bounded native cache; do not put large base64 fonts into `chrome.storage.local`. Re-request after worker restart. Authenticated or inaccessible source files, CFF and missing partners stay original with a reason.

Verify: `uv run pytest tests/test_webfonts.py tests/test_shaping.py tests/test_gsub.py -q`, `bun test chrome-extension`, and the browser acceptance command → pass WOFF/WOFF2, two origins, CSS imports, variable/italic, subsets, mismatched glyph names, same CSS family with different bytes, source failure, pending navigation, changed Settings, warm cache and worker restart cases. Generated fixtures should avoid network-dependent public font services.

### 5. Connect “Set up Chrome” and verify the complete user flow — 8–12 engineering hours

Change `browser --setup`, `BrowserStatus`, `setupChrome` and their UI to work without a selected Candidate. Setup registers/copies assets, starts preparation, enables preserve mode and gives the existing manual Chrome loading instructions. Reruns are idempotent and explain extension reload when code changed. Keep existing Slot selections and make `onUseAs` explicitly activate chosen-font mode. Show preparation failures separately from connection and page coverage; provide retry and the per-site toggle without making technical details the main user flow.

Document supported fonts and exclusions in both READMEs. Verify a fresh setup, upgrade from 0.4.0, app closure, Chrome restart, font install/removal and Settings changes. Live updates must not require page refresh for already instrumented pages. An existing tab missing document-start instrumentation may need one reload; show that condition rather than claiming universal live coverage.

Verify all commands below → exit 0, then record manual fresh-install and upgrade results plus the tested Chrome version in this plan. Only then mark plan 017 DONE.

## Final verification gates

| Command | Expected result |
| --- | --- |
| `uv run ruff check .` | No lint errors. |
| `uv run ruff format --check .` | No formatting changes required. |
| `uv run pytest` | All tests pass; opt-in browser tests may skip in this invocation only. |
| `bun test chrome-extension` | Mapping, protocol and discovery unit tests pass. |
| `cd app && bun run build` | TypeScript check and app bundle succeed. |
| `HALFBOLD_BROWSER_TESTS=1 uv run pytest tests/test_browser_acceptance.py -q` | Real extension fixtures pass with zero skips. |

The last two extension commands describe harnesses to add in step 1; they do not exist at the planned commit. Existing Python and app build commands were confirmed from project configuration, not executed during planning.

## Done criteria

1. Setup works without selecting a font; rerun and upgrade preserve saved choices and the stable extension ID. The host continues working after closing the app and from outside the checkout directory.
2. A fixture with local sans/serif/mono plus downloaded static and variable webfonts renders each supported matching Half face. Unsupported faces remain original and have accurate reasons. Shaping tests verify the Half glyph behavior.
3. Weight/style/fallback/feature fixtures, text selection and copying, dynamic content, frames, open roots and disable restoration pass. No blanket replacement stylesheet applies in preserve mode.
4. Cold conversion, warm cache, Settings invalidation, interruption, malformed requests, size limits and source failures pass. Pending work never hides text or blocks heartbeats; page status distinguishes loaded faces from configuration acknowledgement.
5. All verification gates pass, fresh-install/upgrade evidence is recorded, changes stay within scope, and the plan index is updated.

Estimated total: 48–88 engineering hours, with the delivery test as the first checkpoint. Estimates include fixtures and integration work; inaccessible font formats and arbitrary binary FontFace capture are not promised within that range.

## Stop conditions and maintenance

Run `git diff --stat 783e51f..HEAD -- src/halfbold chrome-extension app/src app/index.html tests pyproject.toml uv.lock README.md CONTEXT.md plans` before implementing. Reconcile changed assumptions against the current-state descriptions; report material drift rather than blindly applying the plan. Stop after three failed fixes and name the doubtful assumption. Stop if broad support requires debugger attachment, weakening site security, new outline conversion, or changing the word-bolding algorithm; those need separate scope decisions.

Review matching correctness before coverage counts: a convincing-looking wrong font is a failure. Future collection/CFF support, continuous variable-axis handling and programmatic font capture can extend the catalog/normalization layer without rewriting page mapping. Cache-version changes must accompany converter behavior changes. Browser-owned surfaces remain outside the extension feature.

## Primary references checked during planning

Chrome's [fontSettings API](https://developer.chrome.com/docs/extensions/reference/api/fontSettings) configures generic/default webpage families by script; it is not a mechanism for converting arbitrary named site fonts or browser UI.

Chrome's [native messaging documentation](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) defines the host protocol and 1 MB host-to-browser message limit. This project has a stricter incoming reader limit, so chunk in both directions.

Chrome's [cross-origin request documentation](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests) supports worker requests with host permissions; content scripts retain origin restrictions. Sender and URL validation are required at that privilege boundary.

The [CSS Font Loading specification](https://drafts.csswg.org/css-font-loading/) describes binary-backed FontFace construction. Its viability in the extension's rendering contexts is a step-1 hypothesis, not a verified result of this plan.

FontTools documents [WOFF2 reading and writing](https://fonttools.readthedocs.io/en/latest/ttLib/woff2.html). Decoding the container does not add support for CFF outlines to halfbold.
