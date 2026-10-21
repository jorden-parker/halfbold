# Bionic reading: how the text is supposed to look

## TL;DR

- Every source I could read bolds the **start** of each word. The official site says "the opening letters of each word are emphasised". No source found bolds word endings, so the maintainer's "both sides" idea is refuted by the evidence.
- The official method does not publish a per-length table or a percentage. Its three knobs are Fixation, Saccade and Opacity.
- Open clones disagree on how much to bold. text-vide bolds roughly 60 to 80 percent of long words by a heuristic table. halfbold bolds 50 percent by default.
- Evidence on benefit is weak. Snell (2024, Acta Psychologica) found no speed gain. The 2025 registered eye-tracking study (Parker et al., Royal Society Open Science) found start-bolding moved the first fixation toward the start of long words, but gave no speed, skipping or comprehension gain. The Readwise experiment (n = 1,916) showed no significant speed difference.

## 1. Official method (bionic-reading.com, Renato Casutt)

- The official BR method page says: "the opening letters of each word are emphasised" to create artificial fixation points. Start-only bolding is what the text says.
- The page says the method "revises texts so that the most concise parts of words are highlighted". That phrase is vague, but it does not mention endings. The official example is an image, and I could not read which letters it bolds. This is the only gap in the evidence.
- The official site describes three parameters: Fixation ("Strong" or "Low"; words sorted into long, medium and short categories, with no rules given), Saccade ("Much" or "Few"), and Opacity (visibility of the fixation).
- No percentage, letter count or word-length rule is published on the page.
- Patent: I could not verify it. A LinkedIn profile lists a "Bionic Reading" patent with publication number FR1755215 (France). I did not find the document itself, its claims, or grant status, so I cannot use it as a primary source.

Verdict on "both sides bolded": refuted by the official text, which names the opening letters only. The one ambiguous phrase is "most concise parts", and it does not say endings.

## 2. Fixation and saccade parameters, and letters bolded per word length

- Fixation (official): controls "the expression of the letter combinations", i.e. how much of each word is bolded. Saccade (official): "the visual jumps from Fixation to Fixation". Narrow columns need fewer saccades. Neither is a count per word length in the official material.
- Published tables: none from Casutt or the company.
- text-vide (fixationPoint default 1), from its HOW.md, gives the number of **non-bold** letters per word length (the author says "I couldn't find a specific pattern here but thought I could use a Heuristic instead"). Derived bold counts (length minus non-bold):

| Word length | Non-bold (text-vide, fp=1) | Bold letters |
|---|---|---|
| 1-4 | 1 | 0, 1, 2, 3 for lengths 1, 2, 3, 4 |
| 5-12 | 2 | length - 2 (5 to 10 bold for 5 to 12 letters) |
| 13-16 | 3 | length - 3 |
| 17-24 | 4 | length - 4 |
| 25-29 | 5 | length - 5 |
| 30-35 | 6 | length - 6 |
| 36-42 | 7 | length - 7 |
| 43-48 | 8 | length - 8 |
| 49+ | 9 | length - 9 |

  Checks against the page's own examples: "Bionic" is shown as "Bion" bold plus "ic" plain (4 bold, 6 letters), and "Reading" as "Readi" bold plus "ng" plain (5 bold, 7 letters). Both match the table.
- Fast-Font (Born2Root/Fast-Font, `opentype_feature.fea`): rules grouped by word length in blocks 1-3, 4-6, 7-8, 9-11, 12-13, 14-16 and 17 letters. Each block uses `ignore sub` rules to pick a position and switch one letter to its bold form. The exact per-block bold count could not be read from the fetched summary, so the table above is not available for Fast-Font.
- Short words: text-vide bolds 0 letters for a 1-letter word and 1 letter for 2-letter words. For 1-3 letter words Fast-Font's first block bolds only the letter not preceded by another letter in its set. The official method does not say.
- halfbold (`src/halfbold/build.py`, `bold_prefix_length`): total bold letters per subword = `min(n, max(1, ceil(n * bold_share)))`, with `bold_share = 0.5` (`settings.py`). Lengths 1 to 10 give 1, 1, 2, 2, 3, 3, 4, 4, 5, 5. Not checked: how the `min_word_length` un-bolding in `count_rules` changes 1-3 letter subwords.

## 3. Open implementations (what they actually do)

- text-vide (Gumball12/text-vide): option `fixationPoint` range [1, 5], default 1. The README examples are `<b>Bion</b>ic` and `<b>Readi</b>ng`. The saccade feature is listed as not implemented (issue #21). The fixation table above is quoted from HOW.md. The `src/index.ts` path returned 404, so the source file itself was not read.
- Fast-Font (Born2Root/Fast-Font; the name "Born2Hack" in the brief returned 404): a calt-based OpenType font. Bolding is done by word-length blocks as described above. Bolds the first letters of each word (README: "the reader is only focusing on the highlighted initial letters").
- JiffyReader (ansh/jiffyreader-public-archive): README says the extension bolds "half the words" and that the fixation slider controls "how much or how little of each word is emphasized". The `src` folder listing did not show file contents, so no formula was retrieved.

## 4. Studies

- Snell, J. (2024). "No, Bionic Reading does not work." *Acta Psychologica* 247, article 104304. DOI 10.1016/j.actpsy.2024.104304. Reported as 100 paragraphs read in Bionic or normal font, with no significant difference in reading time. One secondary source says 32 participants; check the full text before quoting a sample size.
- Parker, A., Lee, H., Wang, H., Joseph, H. (2025). Registered report, *Royal Society Open Science*. DOI 10.1098/rsos.250177. 90 skilled adults, EyeLink 1000 Plus, 18-point Courier New, start-bolded vs unbolded vs middle-bolded. Start-bolding moved first fixation toward the start of long words. Gaze duration, word-level time and sentence reading time showed no difference. Comprehension was about 95 percent in every condition. Readability ratings favoured unbolded text (mean 7.48 unbolded, 6.76 start-bolded, 5.43 middle-bolded). Limits: skilled adults only, single sentences, no dyslexic readers.
- Readwise (2022 web experiment, blog.readwise.io): 3,334 started, 1,916 analysed, two Paul Graham essays in Literata with or without Bionic Reading. Mean 325.3 WPM with vs 327.9 without (difference 0.8 percent). Paired t-test t = -1.92, p = 0.055. Comprehension 88 percent in both. Limits: self-selected volunteers, outlier removal.
- Summary: the start-bolding effect is small to none in speed for typical adults. The eye-tracking study shows an effect on where the eye lands on long words, but no benefit in reading speed or comprehension. Readability ratings were lower with bolding.

## Implications for halfbold

- Current behaviour matches the official method's direction: it bolds the opening letters of each subword (`MARK_STARTS` plus `COUNT`), not word endings.
- Its count rule (`ceil(n * 0.5)`) is a 50 percent share. The official method gives no count, and text-vide's heuristic bolds more (60 to 80 percent for long words). Neither source supports a particular share as correct.
- The camelCase subword split is not described in any source reviewed. It is a halfbold design choice, not part of the bionic method.
- The evidence does not support bolding word endings. If that is wanted, it would be a different scheme, not bionic reading. Such a rule would need its own tests, and no source provides a model for it.
- Evidence suggests the bolding does not improve reading speed or comprehension for skilled adults, so any change should be judged on the user's own preference rather than on claimed speed gains.

## Sources

- https://bionic-reading.com/ (official site; the page is a font-feature marketing page)
- https://bionic-reading.com/br-method/ (official method page: "the opening letters of each word are emphasised"; Fixation, Saccade, Opacity)
- https://www.linkedin.com/in/renato-casutt (patent FR1755215 listed; unverified, not a primary source)
- https://github.com/Gumball12/text-vide (README: fixationPoint, examples)
- https://github.com/Gumball12/text-vide/blob/main/HOW.md (non-bold count table for fixationPoint 1)
- https://github.com/Born2Root/Fast-Font (README; the Born2Hack name in the brief returned 404)
- https://raw.githubusercontent.com/Born2Root/Fast-Font/main/opentype_feature.fea (word-length blocks)
- https://github.com/Born2Root/Fast-Font/blob/main/README_Tutorial.md
- https://github.com/ansh/jiffyreader-public-archive (README; src folder not read)
- https://doi.org/10.1016/j.actpsy.2024.104304 (Snell 2024)
- https://doi.org/10.1098/rsos.250177 (Parker et al. 2025; PMC copy at https://pmc.ncbi.nlm.nih.gov/articles/PMC12565662/ was not fetched)
- https://blog.readwise.io/bionic-reading-results/ (Readwise experiment)
- Local: `/Users/jorden/src/halfbold/src/halfbold/build.py` (`bold_prefix_length`, `count_rules`), `/Users/jorden/src/halfbold/src/halfbold/settings.py` (`BOLD_SHARE = 0.5`)
