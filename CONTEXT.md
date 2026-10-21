# halfbold

Turns a font family into a twin whose `calt` feature bolds the first half of every word, and gives a desktop app to preview, build and install those twins.

## Language

**Face**:
One weight file of a family on disk, named by its style and its weight number: Regular 400, ExtraBold 800. Read from the style name, falling back to `OS/2.usWeightClass`.
_Avoid_: variant, cut, weight file

**Candidate**:
A font family found on disk that can be converted: either two or more Faces at different weights, or one variable font.
_Avoid_: font entry, source font

**Half font**:
The converted output of a Candidate, installed next to the original under the family name plus ` Half` as two Faces: the Regular, which carries the half-bold effect, and the Half Bold face. The Regular is always named Regular at weight 400 whichever Faces built it.
_Avoid_: bionic font, output font, converted font

**Half Bold face**:
The source family's own bold outlines installed into the Half font family, with no half-bold rules, so text that is already bold is drawn as ordinary bold.
_Avoid_: bold companion, bold variant

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

**Originals**:
The Visual Studio Code font settings and Slot values recorded the first time the app changes them, so Reset can put them back.
_Avoid_: backup, snapshot

**Kind**:
The classification of a Candidate as sans, serif or mono.
_Avoid_: category, class

**Settings**:
The one set of build choices applied to every Half font: Bold share, Bold ends, Shortest word, Plain and Bold weights, and the longest word that gets its own rule.
_Avoid_: options, preferences, tuning (UI heading only)

**Plain weight**, **Bold weight**:
The weights the plain and the bold letters are drawn at. A variable font is instanced at them; a static family snaps each to its nearest Face.
_Avoid_: regular weight, boldness (that is Bold share), thickness

**Bold share**:
The fraction of each word's letters drawn bold, counted from the start and rounded up, at least one letter.
_Avoid_: boldness, amount, ratio

**Bold ends**:
Where a word's bold letters go: the start only (default), or split between the start and the end, with the extra letter at the start. The number of bold letters is still set by Bold share.
_Avoid_: mode, style, both sides

**Shortest word**:
The word length below which a word stays entirely plain.
_Avoid_: skip, min length

**Subword**:
The unit the `calt` rules bold: a run of letters split at camelCase boundaries, so `toHaveBeen` is three subwords and `HTTPServer` is two.
_Avoid_: token, segment, word part

**Stale**:
A Half font whose sources changed after it was built, so it needs a rebuild.
_Avoid_: outdated (UI label only), dirty
