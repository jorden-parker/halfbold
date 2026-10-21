# Plan 022: A "Bold ends" setting chooses between bolding the start of each word (today) or its start and end

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 00fe501..HEAD -- src/halfbold/settings.py src/halfbold/build.py src/halfbold/cli.py tests/test_settings.py tests/test_build.py tests/test_shaping.py app/index.html app/src/main.ts app/src/api.ts README.md CONTEXT.md`
> If plan 021 has landed, `src/halfbold/build.py` and `src/halfbold/cli.py`
> will show changes from it (a new `build_bold_face`, `rename_font(style)`,
> a `build_bold_face` call in `cli.main`). That is expected; only the excerpts
> quoted below matter. Any other mismatch with the excerpts is a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (independent of plan 021; either order works)
- **Category**: direction
- **Planned at**: commit `00fe501`, 2026-10-21

## Why this matters

halfbold bolds the opening letters of each subword ("**hel**lo"), which matches
the Bionic Reading method (research in `plans/research/bionic-reading.md`: the
method bolds "the opening letters of each word"; no source bolds endings). The
maintainer still wants to try bolding both ends of a word ("**he**ll**o**") and
compare. This plan adds that as an opt-in Setting, **Bold ends**, with two
values: `1` = start only (default, today's output unchanged) and `2` = start
and end. It is exposed in the CLI, the JSON API and the desktop app's tuning
panel, like Bold share.

### The rule for "start and end" (decided, implement exactly this)

The total number of bold letters stays what Bold share already gives:
`total = bold_prefix_length(n, bold_share)` (that is
`min(n, max(1, ceil(n * bold_share))`). With Bold ends = 2 it is split:

- `start = ceil(total / 2)` letters bold from the start of the subword
- `end = total - start` letters bold at the end of the subword

`start + end == total <= n`, so a word is never wholly bold unless Bold share is
100%. Words shorter than Shortest word stay entirely plain, as today. Words
longer than the longest rule (`max_word_length`, default 20) get start-only
bolding exactly as today (`total` for `max_word_length` letters at the start,
no end letters), because the font cannot see where such a word ends.

Expected output at the defaults (Bold share 0.5, Shortest word 2), uppercase =
bold in the notation the tests use:

| text | Bold ends 1 (today) | Bold ends 2 |
|---|---|---|
| `hello` | `HELlo` | `HEllO` |
| `word word` | `WOrd*WOrd` | `WorD*WorD` |
| `a be` | `a*Be` | `a*Be` |
| `reading` | `READing` | `REadiNG` |
| `the` | `THe` | `ThE` |
| `toHaveBeen` | `ToHAveBEen` | `ToHavEBeeN` |

With `Settings(max_word_length=4, bold_ends=2)`: `abcd` → `AbcD`,
`abcdef` → `ABcdef`.

## Current state

Files involved:

- `src/halfbold/settings.py` — the `Settings` dataclass shared by CLI, app and
  watcher; saved as JSON in `~/Library/Application Support/halfbold/settings.json`.
- `src/halfbold/build.py` — `bold_prefix_length`, `build_feature_code`,
  `count_rules` generate the `calt` rules; `build_halfbold_font` passes
  Settings fields into `build_feature_code`.
- `src/halfbold/cli.py` — `--bold-share` etc. flags, merged into Settings.
- `app/index.html`, `app/src/main.ts`, `app/src/api.ts` — the tuning panel's
  range-slider knobs.

Excerpt, `src/halfbold/settings.py` (lines 7–12 and the dataclass):

```python
RULES_VERSION = 4
BOLD_SHARE = 0.5
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 20
REGULAR_WEIGHT = 400
BOLD_WEIGHT = 700
...
@dataclass(frozen=True)
class Settings:
    bold_share: float = BOLD_SHARE
    min_word_length: int = MIN_WORD_LENGTH
    max_word_length: int = MAX_WORD_LENGTH
    regular_weight: float = REGULAR_WEIGHT
    bold_weight: float = BOLD_WEIGHT

    def validated(self) -> Settings:
        if not 0 < self.bold_share <= 1:
            raise ValueError("bold_share must be between 0 and 1")
        ...
    def merged(self, values: dict) -> Settings:
        known = {f.name: type(getattr(self, f.name)) for f in fields(self)}
        ...
        coerced = {
            name: (int(value) if known[name] is int else float(value))
            for name, value in values.items()
        }
        return replace(self, **coerced).validated()
    ...
    def rules_tag(self) -> str:
        return (
            f"v{RULES_VERSION}-s{round(self.bold_share * 100)}"
            f"-m{self.min_word_length}-x{self.max_word_length}"
        )
```

`rules_tag` names the app's cached preview files; any new rule-affecting
setting must appear in it or the app shows a stale preview.

Excerpt, `src/halfbold/build.py` (`count_rules`, the lookup that decides which
letters after a subword's first letter are bold; `@half'` is the subword's
first letter, already bolded by the `MARK_STARTS` lookup; rules are listed
longest word first so the first match is the whole subword):

```python
def bold_prefix_length(word_length: int, bold_share: float = BOLD_SHARE) -> int:
    return min(word_length, max(1, math.ceil(word_length * bold_share)))
...
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

How the GSUB rule syntax works, so you can generate the end letters: in a
chained contextual rule every input position marked `'` can carry its own
`lookup NAME`. So for a 7-letter subword with start 2 and end 2:

```
sub @half' @plain' lookup TO_HALF @plain' @plain' @plain' @plain' lookup TO_HALF @plain' lookup TO_HALF;
```

Unmarked glyphs after the marked ones are lookahead (matched, not consumed):
`sub @half' @plain' lookup TO_HALF @plain' @plain' @plain;` matches only when a
further letter follows. Use that to give words longer than `max_word_length`
their start-only rule (Step 3). Subword boundaries already work: the next
subword's first letter was turned into `@half` by `MARK_STARTS`, so `@plain`
never matches across it, and spaces and punctuation are not in `@plain`.

`build_feature_code(letters, max_word_length, bold_share, min_word_length)`
calls `count_rules(max_word_length, bold_share, min_word_length)`;
`build_halfbold_font` calls `build_feature_code(letters,
settings.max_word_length, settings.bold_share, settings.min_word_length)`.

Excerpt, `src/halfbold/cli.py` (around lines 106–118 and 240–248):

```python
    parser.add_argument(
        "--bold-share",
        type=float,
        default=settings.bold_share,
        help="Share of each word to bold, 0 to 1 (default from settings)",
    )
...
    settings = load_settings().merged(
        {
            "bold_share": args.bold_share,
            "min_word_length": args.min_word_length,
            "max_word_length": args.max_word_length,
            "regular_weight": args.regular_weight,
            "bold_weight": args.bold_weight,
        }
    )
```

The JSON API's `settings` subcommand (`src/halfbold/api.py` `settings_command`)
takes a JSON object and goes through `Settings.merged`, so it needs no change.

Excerpt, `app/index.html` (inside `<form id="tuning">`):

```html
<label class="knob">
  <span class="knob-name">Shortest word bolded</span>
  <input id="knob-min" type="range" name="min_word_length" min="1" max="8" step="1" />
  <output id="out-min"></output>
</label>
```

Excerpt, `app/src/main.ts`:

```ts
const knobs: Record<keyof Omit<Settings, "max_word_length">, { input: HTMLInputElement; out: HTMLOutputElement }> = {
  bold_share: { input: $("#knob-share"), out: $("#out-share") },
  min_word_length: { input: $("#knob-min"), out: $("#out-min") },
  regular_weight: { input: $("#knob-regular"), out: $("#out-regular") },
  bold_weight: { input: $("#knob-bold"), out: $("#out-bold") },
};
...
function knobValue(name: keyof typeof knobs, value: number): string {
  if (name === "bold_share") return `${Math.round(value * 100)}%`;
  if (name === "min_word_length") return `${value}`;
  return `${Math.round(value)}`;
}
```

`app/src/api.ts` has `interface Settings { bold_share: number;
min_word_length: number; max_word_length: number; regular_weight: number;
bold_weight: number; }` (around line 34).

Vocabulary (`CONTEXT.md`): **Settings** ("The one set of build choices applied
to every Half font: Bold share, Shortest word, Plain and Bold weights, and the
longest word that gets its own rule."), **Bold share** ("The fraction of each
word's letters drawn bold, counted from the start and rounded up, at least one
letter."), **Subword**. The new term is **Bold ends**.

Conventions: no comments anywhere in code (enforced by a hook and ruff `ERA`);
small single-purpose functions; TDD. Exemplar tests:
`tests/test_shaping.py::test_camel_case_subwords_are_bolded_separately`
(shapes text with HarfBuzz and compares with the `bolded()` helper:
uppercase = bold, `*` = space) and
`tests/test_build.py::test_feature_code_lists_longest_words_first`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Python tests | `uv run pytest -q` | all pass |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | exit 0 |
| App typecheck | `cd app && bunx tsc --noEmit -p .` | no output |
| App tests | `cd app && bun test` | 0 fail |

## Scope

**In scope**:

- `src/halfbold/settings.py`, `src/halfbold/build.py`, `src/halfbold/cli.py`
- `tests/test_settings.py`, `tests/test_build.py`, `tests/test_shaping.py`
- `app/index.html`, `app/src/main.ts`, `app/src/api.ts`
- `README.md`, `CONTEXT.md` (doc lines only)

**Out of scope**:

- `start_rules` / `MARK_STARTS` — which letter starts a subword does not change.
- The default: Bold ends stays `1`. Do not change any existing expected
  output in tests.
- `bold_prefix_length` semantics — reuse it, do not change it.
- Plan 021's Half Bold face code, if present.
- `app/src/styles.css` — reuse the existing `.knob` styling.

## Git workflow

- Branch: `advisor/022-bold-word-ends`
- Conventional Commits (hook-enforced), e.g. `feat: add a bold ends setting`.
- Do NOT push or open a PR.

## Steps

### Step 1: `Settings.bold_ends`

Failing tests first in `tests/test_settings.py`:

- `Settings().bold_ends == 1`
- `Settings().merged({"bold_ends": "2"}).bold_ends == 2`
- `Settings().merged({"bold_ends": 3})` raises `ValueError` matching
  `bold_ends`; same for `0`.
- `Settings().cache_tag() != Settings(bold_ends=2).cache_tag()` (add to
  `test_cache_tag_changes_with_values`).

Then in `settings.py`: add `BOLD_ENDS = 1`, field `bold_ends: int = BOLD_ENDS`
(place it after `bold_share`), validation `if self.bold_ends not in (1, 2):
raise ValueError("bold_ends must be 1 (start) or 2 (start and end)")`, and
`-e{self.bold_ends}` appended inside `rules_tag`. `merged` already coerces
`int` fields.

Verify: `uv run pytest -q tests/test_settings.py` → all pass.

### Step 2: split the bold letters between start and end

Failing test in `tests/test_build.py`:

```python
def test_bold_split_puts_the_extra_letter_at_the_start():
    assert [bold_split(n, 0.5, 1) for n in (2, 3, 5, 7)] == [
        (1, 0), (2, 0), (3, 0), (4, 0)
    ]
    assert [bold_split(n, 0.5, 2) for n in (2, 3, 4, 5, 7)] == [
        (1, 0), (1, 1), (1, 1), (2, 1), (2, 2)
    ]
```

Implement `bold_split(word_length, bold_share, bold_ends) -> tuple[int, int]`
in `build.py` returning `(start, end)` per the rule in "Why this matters".

Verify: `uv run pytest -q tests/test_build.py` → all pass.

### Step 3: `count_rules` bolds the end letters

Failing tests in `tests/test_shaping.py`, one per row of the table in "Why this
matters", building with `Settings(bold_ends=2)` and asserting with `bolded()`;
plus the `max_word_length=4` cases (`abcd` → `AbcD`, `abcdef` → `ABcdef`).
Keep every existing shaping test unchanged; they prove Bold ends 1 is
untouched.

Also add to `tests/test_build.py` a check that with `bold_ends=1`
`build_feature_code` output is byte-identical to calling it without the new
argument (guards the default).

Then implement:

- Add `bold_ends: int = BOLD_ENDS` to `build_feature_code` and `count_rules`
  (import `BOLD_ENDS` from `halfbold.settings` like the other defaults), and
  pass `settings.bold_ends` from `build_halfbold_font`.
- In `count_rules`, use `bold_split(length, bold_share, bold_ends)` for each
  length. The rule for a length is: `@half'`, then `start - 1` copies of
  `@plain' lookup TO_HALF`, then `length - start - end` copies of `@plain'`,
  then `end` copies of `@plain' lookup TO_HALF`. When `start == 1` and
  `end == 0` keep today's `ignore sub @half' {rest};` line. Words below
  `min_word_length` keep today's `TO_PLAIN` line.
- Only when `bold_ends == 2`: before the longest rule, emit a start-only rule
  for words longer than `max_word_length`: the start-only rule for
  `max_word_length` letters (`bold_split(max_word_length, bold_share, 1)`)
  followed by one unmarked `@plain` as lookahead. If that start-only split is
  `(1, 0)`, emit it as `ignore sub @half' {max_word_length copies of @plain};`
  instead.
- Keep functions small; a helper that renders one rule from
  `(length, start, end)` is a good split.

Verify: `uv run pytest -q` → all pass. If HarfBuzz/feaLib rejects the generated
rules, see STOP conditions.

### Step 4: CLI flag

Failing test in `tests/test_cli.py` or `tests/test_build.py` (follow
`test_cli_defaults_output_next_to_regular`): `main([str(regular), str(bold),
"--bold-ends", "2"])` succeeds and the written font shapes `hello` as `HEllO`.

Add to `cli.py`, after `--bold-share`:

```python
    parser.add_argument(
        "--bold-ends",
        type=int,
        choices=(1, 2),
        default=settings.bold_ends,
        help="Bold the start of each word (1) or its start and end (2)",
    )
```

and `"bold_ends": args.bold_ends` in the `merged({...})` dict.

Verify: `uv run pytest -q` → all pass; `uv run ruff check .` and
`uv run ruff format --check .` clean.

### Step 5: app knob

- `app/src/api.ts`: add `bold_ends: number;` to `interface Settings`.
- `app/index.html`: after the Bold share `<label class="knob">`, add:

```html
<label class="knob">
  <span class="knob-name">Bold ends</span>
  <input id="knob-ends" type="range" name="bold_ends" min="1" max="2" step="1" />
  <output id="out-ends"></output>
</label>
```

- `app/src/main.ts`: add `bold_ends: { input: $("#knob-ends"), out: $("#out-ends") },`
  to `knobs`, and in `knobValue` return `"Start"` for 1 and `"Start + end"` for
  2 when `name === "bold_ends"`. `renderKnobs` and `onKnobInput` need no other
  change (only `bold_share` is scaled by 100).

Verify: `cd app && bunx tsc --noEmit -p .` → no output; `cd app && bun test` →
0 fail.

Browser check (maintainer preference: UI changes are checked in a real
browser): run `uv run halfbold --desktop` (or `cd app && bun run tauri dev`),
select a font, drag **Bold ends** to `Start + end`, and confirm the Specimen's
Half line shows bold word endings and the console has no errors. If you cannot
launch the app in your environment, say so in your report; do not mark this
done.

### Step 6: docs

- `CONTEXT.md`: add a **Bold ends** entry next to **Bold share**: "Where a
  word's bold letters go: the start only (default), or split between the start
  and the end, with the extra letter at the start. The number of bold letters
  is still set by Bold share." `_Avoid_: mode, style, both sides`. Add "Bold
  ends" to the **Settings** list.
- `README.md`: next to the Bold share text (search `grep -n -i "bold share"
  README.md`), one sentence on `--bold-ends 2`, noting that start-only is the
  Bionic Reading convention and links `plans/research/bionic-reading.md`.

Verify: `grep -n "Bold ends" CONTEXT.md README.md` → hits in both.

## Test plan

- `test_settings.py`: default, coercion, validation, cache tag.
- `test_build.py`: `bold_split` table; default feature code unchanged.
- `test_shaping.py`: the six-row table at Bold ends 2, the two
  `max_word_length=4` cases, all existing tests untouched.
- CLI flag round trip.

## Done criteria

- `uv run pytest -q` → all pass; `uv run ruff check .` → `All checks passed!`;
  `uv run ruff format --check .` → exit 0.
- `cd app && bunx tsc --noEmit -p .` → no output; `cd app && bun test` → 0 fail.
- `git diff 00fe501..HEAD -- tests/test_shaping.py` shows only added lines.
- `git diff --stat 00fe501..HEAD` lists only in-scope files (plus plan 021's
  files if it landed first).
- Browser check from Step 5 done or explicitly reported as not possible.

## STOP conditions

- feaLib or HarfBuzz rejects a generated rule, or a shaping test shows end
  letters being bolded inside a word (not at its end). Report the generated
  rule and the shaped output; do not restructure the `MARK_STARTS` / `COUNT`
  lookups on your own (plan 016 already had to redesign them once after a
  HarfBuzz rejection).
- Any existing shaping test changes output.
- A verification fails twice after a reasonable fix attempt.

## Maintenance notes

- Font size grows slightly at Bold ends 2 (longer rules); negligible.
- Installed Half fonts are not rebuilt just because Settings changed (staleness
  is source-mtime based, same as Bold share today); the app's Convert / Use
  buttons rebuild with current Settings.
- If a third placement is ever wanted, `bold_ends` should become a named
  choice rather than a bigger number.
