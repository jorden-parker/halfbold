# halfbold

Turns a font family into a twin whose `calt` feature bolds the first half of every word, and gives a desktop app to preview, build and install those twins.

## Language

**Candidate**:
A font family found on disk that can be converted: either a Regular and Bold pair or one variable font.
_Avoid_: font entry, source font

**Half font**:
The converted output of a Candidate, installed next to the original under the family name plus ` Half`.
_Avoid_: bionic font, output font, converted font

**Preview**:
A Half font built into the cache, not installed, so the app can show the half-bold result before the user commits.
_Avoid_: sample, demo

**Specimen**:
The editable block of sample text the app draws in a font, once in the Half font and once in the Regular.
_Avoid_: sample text, demo paragraph

**Cask**:
A Homebrew font cask, identified by its token (`font-inter`), shown by its font name.
_Avoid_: brew font, formula

**Google Fonts cask**:
A Cask whose files live in the google/fonts repository, so single faces can be fetched directly without the cask archive.

**Slot**:
One of the Chrome extension's three roles, sans, serif or mono, each pointing at one installed Half font family.
_Avoid_: kind (that is the classification of a Candidate), active font

**Kind**:
The classification of a Candidate as sans, serif or mono.
_Avoid_: category, class

**Stale**:
A Half font whose sources changed after it was built, so it needs a rebuild.
_Avoid_: outdated (UI label only), dirty
