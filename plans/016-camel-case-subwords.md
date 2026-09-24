# Plan 016: Bold each camelCase subword on its own, so identifiers read well in code editors

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 0f0205e..HEAD -- src/halfbold/build.py src/halfbold/settings.py tests/conftest.py tests/test_build.py tests/test_shaping.py tests/test_api.py tests/test_variable.py tests/test_settings.py AGENTS.md CONTEXT.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (pure Python, fully covered by shaping tests; no app or Rust change)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `0f0205e`, 2026-09-24
- **Status**: DONE 2026-09-24, merged to main

## Why this matters

The maintainer uses Half fonts in Ghostty and Neovim. Today the `calt` rules
treat every unbroken run of letters as one word, so an identifier such as
`toHaveBeenCalledExactlyOnceWith` (31 letters) is longer than the longest
rule (20) and gets its first 10 letters bolded: `toHaveBeenC` bold, the rest
plain. That is noise, not a reading aid.

After this plan a run of letters is split into **subwords** at camelCase
boundaries and each subword is bolded on its own. `toHaveBeenCalledExactlyOnceWith`
renders as `t`+o `Ha`+ve `Be`+en `Cal`+led `Exac`+tly `On`+ce `Wi`+th (bold+plain).
Acronyms are handled too: `HTTPServer` becomes `HT`+TP `Ser`+ver, `XMLParser`
becomes `XM`+L `Par`+ser. Prose is unaffected: words that are all lowercase,
Capitalised, or ALL CAPS are still one subword each. snake_case and digits
already split words today (underscore and digits are not letters) and keep
doing so.

The maintainer requested this on 2026-09-24: "Make the built fonts work
better with code editors/IDEs ... appropriate bolding for the likes of
camel-cased words like `toHaveBeenCalledExactlyOnceWith`."

## Revision 1 (2026-09-24, after the first execution attempt)

The first version of this plan wrote one `calt` lookup with a rule per
(length, case shape). On a real Nerd Font (631 letter glyphs) HarfBuzz
silently dropped the whole GSUB table: HarfBuzz gives sanitizing a budget of
64 ops per byte of the table and charges the byte size of a coverage table
**every time it is referenced**. The case-split classes (`@lower`, `@upper`)
have alternating glyph IDs in Latin Extended, so each reference costs ~650
bytes, and ~880 references blew the budget. The single-class design on `main`
works because it references one contiguous class ~210 times. A second defect:
feaLib raises `Empty glyph class in contextual substitution` when a font has
no capitals at all (`@upper = [];`).

The design below fixes both: case-aware classes appear in only ~10
references, the per-length rules use the cheap union class, and rules that
name an empty class are simply not emitted. It was shaped with uharfbuzz on
the test font, on `JetBrainsMonoNLNerdFont` (631 letters, also at
`max_word_length=40`), on `InterVariable` (1437 letters), and on synthetic
lower-only and upper-only letter sets. All produced the expected output.

## The rule design (prototyped and verified with HarfBuzz)

**Subword starts** at a letter that is:

1. not preceded by a letter (existing behaviour), or
2. uppercase preceded by lowercase (`o|H` in `toHave`), or
3. uppercase preceded by uppercase and followed by lowercase (`P|S` in
   `HTTPServer`: the last capital of an acronym belongs to the next word).

Two chained lookups run in order inside `calt`:

**Lookup `MARK_STARTS`** swaps the first letter of every subword to its
`.half` twin, regardless of length. Rules are tried in source order, first
match wins, `ignore` stops matching at that position:

```
ignore sub [@lower @lower_half] @lower';        # lowercase after lowercase: mid-subword
ignore sub [@upper @upper_half] @lower';        # lowercase after capital: mid-subword
ignore sub [@upper @upper_half] @upper' @upper; # capital between capitals: mid-acronym
sub @lower' lookup TO_HALF;                     # any other lowercase starts a subword
sub @upper' lookup TO_HALF @lower;              # capital followed by lowercase starts one
ignore sub [@upper @upper_half] @upper';        # remaining capital after capital: acronym end
sub @upper' lookup TO_HALF;                     # any other capital starts an acronym
```

**Lookup `COUNT`** runs at each `.half` start glyph and sees the whole
subword as `@half` followed by plain letters (the next subword's start is a
`.half`, so it is not `@plain` and ends the match). One rule per length
`n = max..1`, longest first, with `p = bold_prefix_length(n, bold_share)`:

- `n < min_word_length`: `sub @half' lookup TO_PLAIN @plain × (n-1);` — the
  subword is too short, un-bold its start.
- `p > 1`: `sub @half' @plain' lookup TO_HALF × (p-1) @plain' × (n-p);` —
  bold letters 2..p; every letter of the subword is marked (`'`) so the
  cursor skips past the subword afterwards.
- `p == 1` and `n > 1`: `ignore sub @half' @plain × (n-1);` — nothing more
  to bold; stops shorter rules (including the un-bold rules) from matching.
- `p == 1` and `n == 1`: no rule (a lone start is already right).

Plain glyphs never match a `COUNT` rule, so letters past `max_word_length`
stay plain exactly as today.

Why this is cheap for HarfBuzz: `MARK_STARTS` references the expensive
case-split coverages about 10 times; `COUNT` references `@half` (one
contiguous range, since the `.half` glyphs are appended together) and
`@plain` (the union, the same class `main` uses today) about 210 times.

Verified shaping (bold glyphs shown as CAPITALS, plain as lowercase, space
as `*`) with default settings (bold share 0.5, shortest word 2, longest 20):

| Input | Output |
|---|---|
| `hello` | `HELlo` |
| `toHaveBeenCalledExactlyOnceWith` | `ToHAveBEenCALledEXACtlyONceWIth` |
| `HTTPServer` | `HTtpSERver` |
| `XMLParser` | `XMlPARser` |
| `ABCd` | `AbCd` |
| `iPhone` | `iPHOne` |
| `getX` | `GEtx` |
| `HELLO WORLD` | `HELlo*WORld` |
| `parseHTMLNow` | `PARseHTmlNOw` |
| `ABC` | `ABc` |

With `min_word_length=1`: `a` → `A`, `getX` → `GEtX`, `ABC` → `ABc`.
With `min_word_length=5`: `toHaveBeenCalledExactlyOnceWith` →
`tohavebeenCALledEXACtlyoncewith`, `HTTPServer` → `httpSERver`.
With `max_word_length=4`: `abcdef` → `ABcdef` (as today).
With `bold_share=0.8`: `getXFoo` → `GETxFOO`, `abcDef` → `ABCDEF`.
With `bold_share=1.0`: everything bold except subwords shorter than the minimum.

## Current state

Files and their roles:

- `src/halfbold/build.py` — builds the Half font. `word_letter_glyphs`
  (lines 87–98) collects letter glyph names; `build_feature_code` (lines
  123–148) writes the `calt` feature; `build_halfbold_font` (lines 21–47)
  wires them together and returns the letter list.
- `src/halfbold/settings.py` — `Settings` dataclass; `cache_tag` (lines
  60–65) names the app's cached preview builds.
- `src/halfbold/api.py:74` — uses `settings.cache_tag()` in the preview cache
  file name.
- `tests/conftest.py` — `make_font` / `make_variable_font` build test fonts
  with only lowercase `a–z` plus `space`.
- `tests/test_shaping.py` — shapes built fonts with `uharfbuzz`; the pattern
  to follow for new shaping tests.
- `tests/test_build.py`, `tests/test_api.py`, `tests/test_variable.py` —
  assert `26` letter glyphs (becomes 52 once the fixtures gain `A–Z`).
- `AGENTS.md` (line 9) and `CONTEXT.md` — describe the algorithm and the
  domain vocabulary; both need one edit.

`src/halfbold/build.py:87-98` today:

```python
def word_letter_glyphs(regular: TTFont, bold: TTFont) -> list[str]:
    regular_cmap = regular.getBestCmap()
    bold_glyphs = set(bold.getGlyphOrder())
    names: list[str] = []
    seen: set[str] = set()
    for codepoint, name in sorted(regular_cmap.items()):
        if not chr(codepoint).isalpha():
            continue
        if name in bold_glyphs and name not in seen:
            names.append(name)
            seen.add(name)
    return names
```

`src/halfbold/build.py:123-148` today:

```python
def build_feature_code(
    letters: list[str],
    max_word_length: int = MAX_WORD_LENGTH,
    bold_share: float = BOLD_SHARE,
    min_word_length: int = MIN_WORD_LENGTH,
) -> str:
    plain = " ".join(letters)
    half = " ".join(name + BOLD_SUFFIX for name in letters)
    lines = [
        f"@plain = [{plain}];",
        f"@half = [{half}];",
        "lookup TO_HALF {",
        "  sub @plain by @half;",
        "} TO_HALF;",
        "feature calt {",
        "  ignore sub [@plain @half] @plain';",
    ]
    for length in range(max_word_length, max(min_word_length, 1) - 1, -1):
        prefix = bold_prefix_length(length, bold_share)
        marked = " ".join("@plain' lookup TO_HALF" for _ in range(prefix))
        rest = " ".join("@plain" for _ in range(length - prefix))
        lines.append(f"  sub {marked} {rest};".replace("  ;", ";").rstrip())
    lines.append("} calt;")
    return "\n".join(lines) + "\n"
```

`src/halfbold/build.py:31-40` today:

```python
    letters = word_letter_glyphs(regular, bold)
    if not letters:
        raise ValueError("no letter glyphs shared between the two fonts")

    copy_bold_glyphs(regular, bold, letters)
    fea = build_feature_code(
        letters,
        settings.max_word_length,
        settings.bold_share,
        settings.min_word_length,
    )
```

`src/halfbold/settings.py:60-65` today:

```python
    def cache_tag(self) -> str:
        return (
            f"s{round(self.bold_share * 100)}-m{self.min_word_length}"
            f"-x{self.max_word_length}-w{round(self.regular_weight)}"
            f"-b{round(self.bold_weight)}"
        )
```

`tests/conftest.py:8` today: `LETTERS = "abcdefghijklmnopqrstuvwxyz"`.

`AGENTS.md:9` today:

> It then generates an OpenType feature file: one chained `calt` rule per word length, longest first, each bolding `ceil(n / 2)` letters. An `ignore` rule stops the chain from re-firing mid-word.

Conventions to honour (from `AGENTS.md`):

- No code comments at all. Name things well instead.
- Ruff rules `E, F, I, UP, B, SIM, ERA`, line length 88, Python 3.14 (so
  `list[str]`, `X | None`, dataclasses are the norm; see `settings.py`).
- Conventional Commits; the `commit-msg` hook rejects anything else.
- Vocabulary from `CONTEXT.md`: "Half font", "Bold share", "Shortest word".
  Use **subword** for a camelCase piece; this plan adds that term.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Tests | `uv run pytest -q` | all pass (83 today) |
| One file | `uv run pytest -q tests/test_shaping.py` | all pass |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format check | `uv run ruff format --check .` | `N files already formatted` |

`uharfbuzz` is already a dev dependency, so shaping tests run without extra setup.

## Scope

**In scope** (the only files you should modify):

- `src/halfbold/build.py`
- `src/halfbold/settings.py` (one line in `cache_tag`, one constant)
- `tests/conftest.py`
- `tests/test_build.py`
- `tests/test_shaping.py`
- `tests/test_api.py` (the `26` → `52` assertion only)
- `tests/test_variable.py` (the `26` → `52` assertion only)
- `tests/test_settings.py` (one new assertion)
- `AGENTS.md` (the one "How it works" bullet)
- `CONTEXT.md` (add one glossary entry)

**Out of scope** (do NOT touch, even though they look related):

- `src/halfbold/api.py`, `src/halfbold/cli.py`, `src/halfbold/scan.py`,
  `src/halfbold/web.py` — the public JSON/CLI shape and the `letters` count
  they report stay as they are (they receive a plain `list[str]`).
- `app/`, `chrome-extension/`, `scripts/` — no UI, no new setting.
- Keeping the source font's own `GSUB` (coding ligatures such as `->`): a
  separate, larger change; see "Maintenance notes".
- Treating digits as part of a subword (`utf8`, `md5Hash`): deferred.

## Git workflow

- Branch: `advisor/016-camel-case-subwords` from `main`.
- One commit per step or logical unit, Conventional Commits, e.g.
  `feat: bold each camelCase subword on its own`,
  `test: shape camelCase identifiers`, `docs: describe subword rules`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Give the test fonts uppercase letters

In `tests/conftest.py` change line 8 to include capitals:

```python
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
```

Nothing else in `conftest.py` changes: `make_font` and `make_variable_font`
already iterate `LETTERS` for glyph order, cmap, outlines, metrics and gvar.

Update the three letter-count assertions from `26` to `52`:

- `tests/test_build.py:44` — `assert len(letters) == 52`
- `tests/test_build.py:82` — `assert "52 letter glyphs" in ...`
- `tests/test_api.py:42` — `assert payload["letters"] == 52`
- `tests/test_variable.py:35` — `assert "52 letter glyphs" in ...`

**Verify**: `uv run pytest -q` → all pass (the existing shaping tests still
hold because all their inputs are lowercase).

### Step 2: Classify letters by case in `build.py`

Add a frozen dataclass near the top of `src/halfbold/build.py` (after the
constants) and make `word_letter_glyphs` return it:

```python
@dataclass(frozen=True)
class Letters:
    lower: list[str]
    upper: list[str]

    @property
    def names(self) -> list[str]:
        return self.lower + self.upper
```

```python
def word_letter_glyphs(regular: TTFont, bold: TTFont) -> Letters:
    regular_cmap = regular.getBestCmap()
    bold_glyphs = set(bold.getGlyphOrder())
    lower: list[str] = []
    upper: list[str] = []
    seen: set[str] = set()
    for codepoint, name in sorted(regular_cmap.items()):
        char = chr(codepoint)
        if not char.isalpha() or name not in bold_glyphs or name in seen:
            continue
        seen.add(name)
        (upper if char.isupper() else lower).append(name)
    return Letters(lower, upper)
```

Rules: a glyph is classified by the **first** (lowest) codepoint that maps to
it, as today's dedupe already does. Letters that are neither upper nor lower
(`isalpha()` true, `isupper()` false: CJK, Arabic, titlecase digraphs) go in
`lower`, so they never start a camelCase boundary. The two lists are
disjoint by construction.

In `build_halfbold_font` adapt the call sites so the public return type is
unchanged:

```python
    letters = word_letter_glyphs(regular, bold)
    if not letters.names:
        raise ValueError("no letter glyphs shared between the two fonts")

    copy_bold_glyphs(regular, bold, letters.names)
    fea = build_feature_code(
        letters,
        settings.max_word_length,
        settings.bold_share,
        settings.min_word_length,
    )
    ...
    return letters.names
```

Add `from dataclasses import dataclass` to the imports (ruff `I` sorts it).

**Verify**: `uv run ruff check .` → passes. `uv run pytest -q` → fails only in
`tests/test_build.py` where `build_feature_code` is still called with a
plain list (fixed in Step 4).

### Step 3: Rewrite `build_feature_code` around subwords

Replace `build_feature_code` in `src/halfbold/build.py` with the following
four functions. Keep the signature order (`letters, max_word_length,
bold_share, min_word_length`) so `build_halfbold_font` needs no further
change. This code is already ruff-formatted; paste it verbatim.

```python
def build_feature_code(
    letters: Letters,
    max_word_length: int = MAX_WORD_LENGTH,
    bold_share: float = BOLD_SHARE,
    min_word_length: int = MIN_WORD_LENGTH,
) -> str:
    lines = [
        f"@lower = [{' '.join(letters.lower)}];",
        f"@upper = [{' '.join(letters.upper)}];",
        f"@lower_half = [{' '.join(half_name(n) for n in letters.lower)}];",
        f"@upper_half = [{' '.join(half_name(n) for n in letters.upper)}];",
        "@plain = [@lower @upper];",
        "@half = [@lower_half @upper_half];",
        "lookup TO_HALF {",
        "  sub @plain by @half;",
        "} TO_HALF;",
        "lookup TO_PLAIN {",
        "  sub @half by @plain;",
        "} TO_PLAIN;",
        "lookup MARK_STARTS {",
        *start_rules(bool(letters.lower), bool(letters.upper)),
        "} MARK_STARTS;",
        "lookup COUNT {",
        *count_rules(max_word_length, bold_share, min_word_length),
        "} COUNT;",
        "feature calt {",
        "  lookup MARK_STARTS;",
        "  lookup COUNT;",
        "} calt;",
    ]
    return "\n".join(lines) + "\n"


def half_name(name: str) -> str:
    return name + BOLD_SUFFIX


def start_rules(has_lower: bool, has_upper: bool) -> list[str]:
    rules: list[str] = []
    if has_lower:
        rules.append("  ignore sub [@lower @lower_half] @lower';")
    if has_lower and has_upper:
        rules.append("  ignore sub [@upper @upper_half] @lower';")
    if has_upper:
        rules.append("  ignore sub [@upper @upper_half] @upper' @upper;")
    if has_lower:
        rules.append("  sub @lower' lookup TO_HALF;")
    if has_lower and has_upper:
        rules.append("  sub @upper' lookup TO_HALF @lower;")
    if has_upper:
        rules.append("  ignore sub [@upper @upper_half] @upper';")
        rules.append("  sub @upper' lookup TO_HALF;")
    return rules


def count_rules(
    max_word_length: int, bold_share: float, min_word_length: int
) -> list[str]:
    rules: list[str] = []
    for length in range(max_word_length, 0, -1):
        prefix = bold_prefix_length(length, bold_share)
        rest = " ".join(["@plain"] * (length - 1))
        if length < min_word_length:
            rules.append(f"  sub @half' lookup TO_PLAIN {rest};".replace(" ;", ";"))
        elif prefix > 1:
            bolded = ["@plain' lookup TO_HALF"] * (prefix - 1)
            consumed = ["@plain'"] * (length - prefix)
            rules.append(f"  sub @half' {' '.join(bolded + consumed)};")
        elif length > 1:
            rules.append(f"  ignore sub @half' {rest};")
    return rules
```

Notes for the executor:

- Rule order inside `MARK_STARTS` and `COUNT` is load-bearing. Do not sort,
  group or "tidy" it. See "The rule design" above for why each line sits
  where it does.
- `start_rules` only emits rules whose classes are non-empty, because feaLib
  raises `Empty glyph class in contextual substitution` otherwise. Keep the
  `has_lower` / `has_upper` guards exactly as written.
- Do not merge `MARK_STARTS` and `COUNT` into one lookup, and do not add
  `@lower` / `@upper` to any `COUNT` rule: that is what broke HarfBuzz on
  real fonts (see "Revision 1").

**Verify**: `uv run ruff check .` and `uv run ruff format --check .` → pass.

### Step 4: Update the feature-code unit tests

In `tests/test_build.py` change the imports to:

```python
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont

from halfbold.build import (
    BOLD_SUFFIX,
    Letters,
    bold_prefix_length,
    build_feature_code,
    build_halfbold_font,
    copy_bold_glyphs,
    word_letter_glyphs,
)
from halfbold.cli import main
```

Replace `test_feature_code_honours_share_and_min_word_length` and
`test_feature_code_lists_longest_words_first` (and any `lowercase_rules` /
`test_feature_code_orders_camel_case_rules` left from the first attempt) with:

```python
def block(fea: str, name: str) -> list[str]:
    body = fea.split(f"lookup {name} {{\n", 1)[1].split(f"}} {name};", 1)[0]
    return [line.strip() for line in body.splitlines()]


def test_feature_code_honours_share_and_min_word_length():
    count = block(build_feature_code(Letters(["a"], ["A"]), 6, 0.25, 4), "COUNT")
    assert [line.count("lookup TO_HALF") for line in count] == [1, 1, 0, 0, 0, 0]
    unbolded = [line.startswith("sub @half' lookup TO_PLAIN") for line in count]
    assert unbolded == [False, False, False, True, True, True]


def test_feature_code_lists_longest_words_first():
    count = block(build_feature_code(Letters(["a"], ["A"]), 4), "COUNT")
    assert count == [
        "sub @half' @plain' lookup TO_HALF @plain' @plain';",
        "sub @half' @plain' lookup TO_HALF @plain';",
        "ignore sub @half' @plain;",
        "sub @half' lookup TO_PLAIN;",
    ]


def test_feature_code_marks_subword_starts_in_order():
    fea = build_feature_code(Letters(["a"], ["A"]), 3)
    assert block(fea, "MARK_STARTS") == [
        "ignore sub [@lower @lower_half] @lower';",
        "ignore sub [@upper @upper_half] @lower';",
        "ignore sub [@upper @upper_half] @upper' @upper;",
        "sub @lower' lookup TO_HALF;",
        "sub @upper' lookup TO_HALF @lower;",
        "ignore sub [@upper @upper_half] @upper';",
        "sub @upper' lookup TO_HALF;",
    ]
    assert fea.index("lookup MARK_STARTS;") < fea.index("lookup COUNT;")


def test_feature_code_compiles_for_fonts_with_one_case(font_pair: tuple[Path, Path]):
    for pick in (
        lambda found: Letters(found.lower, []),
        lambda found: Letters([], found.upper),
    ):
        regular, bold = TTFont(font_pair[0]), TTFont(font_pair[1])
        letters = pick(word_letter_glyphs(regular, bold))
        copy_bold_glyphs(regular, bold, letters.names)
        addOpenTypeFeaturesFromString(
            regular, build_feature_code(letters), tables=["GSUB"]
        )
        assert "calt" in {
            f.FeatureTag for f in regular["GSUB"].table.FeatureList.FeatureRecord
        }
```

Also update `test_build_adds_bold_glyphs_and_calt` to assert both
`"a" + BOLD_SUFFIX` and `"A" + BOLD_SUFFIX` are in the glyph order.

**Verify**: `uv run pytest -q tests/test_build.py` → 9 passed.

### Step 5: Add shaping tests for subwords

Append to `tests/test_shaping.py`, reusing its `shape` helper (which returns
glyph names such as `t.half o H.half`). Add a helper that encodes the result
as one letter per glyph: bold glyphs as UPPERCASE, plain glyphs as lowercase,
`space` as `*`. So `"toHave"` shaping to `t.half o H.half a.half v e` encodes
as `"ToHAve"`. All assertions below use that encoding.

```python
def bolded(path: Path, text: str) -> str:
    out = ""
    for glyph in shape(path, text).split():
        if glyph == "space":
            out += "*"
        elif glyph.endswith(".half"):
            out += glyph[0].upper()
        else:
            out += glyph[0].lower()
    return out
```

```python
def test_camel_case_subwords_are_bolded_separately(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    assert bolded(out, "toHaveBeenCalledExactlyOnceWith") == (
        "ToHAveBEenCALledEXACtlyONceWIth"
    )
    assert bolded(out, "HTTPServer") == "HTtpSERver"
    assert bolded(out, "XMLParser") == "XMlPARser"
    assert bolded(out, "parseHTMLNow") == "PARseHTmlNOw"
    assert bolded(out, "iPhone") == "iPHOne"
    assert bolded(out, "getX") == "GEtx"


def test_prose_words_are_unchanged_by_case(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    assert bolded(out, "Hello World") == "HELlo*WORld"
    assert bolded(out, "HELLO WORLD") == "HELlo*WORld"
    assert bolded(out, "ABC") == "ABc"


def test_lone_capital_after_acronym_is_not_rebolded(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(min_word_length=1))

    assert bolded(out, "ABC") == "ABc"
    assert bolded(out, "getX") == "GEtX"
    assert bolded(out, "a") == "A"
```

Add two more shaping tests after those:

```python
def test_short_subwords_stay_plain_at_a_higher_minimum(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(min_word_length=5))

    assert bolded(out, "toHaveBeenCalledExactlyOnceWith") == (
        "tohavebeenCALledEXACtlyoncewith"
    )
    assert bolded(out, "HTTPServer") == "httpSERver"


def test_high_bold_share_keeps_subword_boundaries(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(bold_share=0.8))

    assert bolded(out, "getXFoo") == "GETxFOO"
    assert bolded(out, "abcDef") == "ABCDEF"
```

Keep the two existing tests as they are; they must still pass unchanged.

**Verify**: `uv run pytest -q tests/test_shaping.py` → 7 passed.

### Step 6: Version the preview cache tag

The app caches preview builds under a name derived from `Settings.cache_tag()`
(`src/halfbold/api.py:74`). Without a version in the tag, previews built
before this change stay in `~/Library/Caches/halfbold` and keep showing the
old bolding. In `src/halfbold/settings.py` add a constant next to the others
and prefix the tag:

```python
RULES_VERSION = 2
```

```python
    def cache_tag(self) -> str:
        return (
            f"v{RULES_VERSION}-s{round(self.bold_share * 100)}"
            f"-m{self.min_word_length}-x{self.max_word_length}"
            f"-w{round(self.regular_weight)}-b{round(self.bold_weight)}"
        )
```

Add to `tests/test_settings.py`:

```python
def test_cache_tag_carries_rules_version():
    assert Settings().cache_tag().startswith("v2-")
```

Installed Half fonts are compared by mtime against their sources
(`scan.py:35-39`), so they are not rebuilt automatically. That is by design;
the rollout is `uv run halfbold --all --force` (see Maintenance notes).

**Verify**: `uv run pytest -q tests/test_settings.py tests/test_api.py` → pass.

### Step 7: Update the docs

`AGENTS.md`, replace the line-9 bullet with:

> It then generates an OpenType feature file with two chained `calt` lookups. `MARK_STARTS` bolds the first letter of every subword (a run of letters split at camelCase boundaries: a capital after a lowercase letter, or the last capital of an acronym before a lowercase one). `COUNT` then matches each subword from its bold start, longest first, bolds the next `ceil(n * bold_share) - 1` letters, and un-bolds the start of any subword shorter than the shortest word.

`CONTEXT.md`, add after the **Shortest word** entry:

```
**Subword**:
The unit the `calt` rules bold: a run of letters split at camelCase boundaries, so `toHaveBeen` is three subwords and `HTTPServer` is two.
_Avoid_: token, segment, word part
```

**Verify**: `grep -n "Subword" CONTEXT.md` → one match; `grep -n "subword" AGENTS.md` → one match.

### Step 8: Full verification and a real-font smoke check

Run the full gates, then build one real Half font and shape it:

```sh
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Smoke check on a real font (read-only for `~/Library/Fonts`; output goes to `/tmp`).
This is the check that caught the HarfBuzz problem in the first attempt, so it
is mandatory, not optional:

```sh
uv run halfbold ~/Library/Fonts/JetBrainsMonoNLNerdFont-Regular.ttf \
  ~/Library/Fonts/JetBrainsMonoNLNerdFont-Bold.ttf \
  --bold-share 0.5 --min-word-length 2 -o /tmp/JBM-Half.ttf
uv run python - <<'EOF'
from pathlib import Path
import sys
sys.path.insert(0, "tests")
import uharfbuzz as hb
from test_shaping import bolded
font = Path("/tmp/JBM-Half.ttf")
print("has_layout_substitution:", hb.Face(font.read_bytes()).has_layout_substitution)
print(bolded(font, "toHaveBeenCalledExactlyOnceWith HTTPServer hello ABC"))
EOF
```

The explicit flags matter: without them the CLI reads the maintainer's saved
settings file (bold share 0.35 on 2026-09-24) and the bold prefixes come out
shorter. Expected output, exactly:

```
has_layout_substitution: 1
ToHAveBEenCALledEXACtlyONceWIth*HTtpSERver*HELlo*ABc
```

If `has_layout_substitution` prints `0`, HarfBuzz rejected the GSUB table:
STOP and report. If that Nerd Font is not installed, use any Regular + Bold
TrueType pair in `~/Library/Fonts` (`uv run halfbold --all --dry-run` lists
candidates) and report which one you used.

## Test plan

- `tests/test_shaping.py`: five new tests (camelCase identifiers, prose
  unchanged, `min_word_length=1` does not re-bold the last capital of an
  acronym, `min_word_length=5` keeps short subwords plain, `bold_share=0.8`
  keeps boundaries). Pattern: the existing `test_first_half_of_each_word_is_bold`.
- `tests/test_build.py`: two rewritten feature-code tests plus two new ones
  (`MARK_STARTS` order, one-case fonts compile); `test_build_adds_bold_glyphs_and_calt`
  also checks an uppercase `.half` glyph exists.
- `tests/test_settings.py`: one new cache-tag test.
- Counts updated `26` → `52` in `test_build.py`, `test_api.py`, `test_variable.py`.
- Verification: `uv run pytest -q` → all pass, 91 tests (83 today + 5 shaping + 2 build + 1 cache tag).
- Every snippet in Steps 2–5 was applied to a scratch copy of the repo on 2026-09-24 (revision 1) and passed `ruff check`, `ruff format --check` and `pytest` (91 tests). If you transcribe them exactly, they pass.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `uv run ruff check .` exits 0
- [ ] `uv run ruff format --check .` exits 0
- [ ] `uv run pytest -q` exits 0 with at least 91 tests
- [ ] `grep -c "lookup TO_HALF" src/halfbold/build.py` ≥ 1 and `grep -n "ignore sub \[@plain @half\] @plain'" src/halfbold/build.py` returns nothing
- [ ] Step 8 smoke check prints `has_layout_substitution: 1` and the expected bolded string
- [ ] `grep -n "#" src/halfbold/build.py` returns no comment lines
- [ ] `git status --porcelain` lists only in-scope files
- [ ] `plans/README.md` status row for 016 updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations in "Current state" doesn't match the excerpts.
- feaLib raises on the generated feature file (for example on an empty
  `@upper = [];` class, or a glyph name it cannot parse). Paste the error
  and the offending line.
- Any shaping assertion in Step 5 fails after you have confirmed the rule
  order in Step 3 matches the plan character for character. The design was
  verified against HarfBuzz; a mismatch means the rules were transcribed
  differently, not that the expectation is wrong.
- The fix appears to require touching `api.py`, `cli.py`, `scan.py` or `app/`.
- `uv run pytest` was not green before you started (record the failures).

## Maintenance notes

- **Rollout**: installed Half fonts are only rebuilt when their sources are
  newer. After merging, run `uv run halfbold --all --force` and restart
  Ghostty / Neovim to pick up the new `calt` rules.
- **Rule order is the algorithm.** `MARK_STARTS` must keep its seven-rule
  order and `COUNT` must stay longest-first. The tests in Step 4 guard both;
  a reviewer should reject a diff that reorders them without a new shaping
  test proving the output.
- **HarfBuzz budget.** Never reference `@lower` / `@upper` from a per-length
  rule. HarfBuzz charges each coverage reference its byte size against a
  budget of 64 ops per GSUB byte, and the case-split classes are large on
  real fonts. Any new rule family must be smoke-checked on a Nerd Font
  (Step 8), not only on the 52-letter test font.
- **Deferred, worth a separate plan**: keep the source font's own `GSUB`
  (JetBrains Mono / Fira Code ligatures such as `->` and `!=` are dropped
  today because `addOpenTypeFeaturesFromString(..., tables=["GSUB"])`
  replaces the table). That needs merging lookups into the existing table
  rather than a feature-file rewrite, so it is its own plan.
- **Deferred**: digits inside identifiers (`md5Hash`, `utf8`) currently end
  a subword because they are not letters; `md5Hash` bolds `m` and `Ha`. A
  future `@digit` class could let digits ride along inside a subword.
- **Deferred**: a `split_subwords` setting to turn this off. `Settings.merged`
  only coerces `int`/`float`, and the app's sliders would need a toggle, so
  it was left out until someone asks for it.
