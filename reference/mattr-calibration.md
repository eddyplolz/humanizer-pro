# MATTR calibration: why it is a stat, not a finding

MATTR (moving-average type-token ratio, 50-token windows) was evaluated as a
candidate lexical-diversity **finding**. The idea: AI text reuses vocabulary,
so it should score a lower MATTR than human prose. The calibration below did
not support that idea, so MATTR ships as a **diagnostic stat only**. It is
shown in the `stats` block as `mattr_50`, never as a finding, never as a
score input. A document shorter than one window (50 tokens) gets `null`,
because a plain TTR over fewer tokens is not comparable with a windowed value.

## Method

- **Human baseline:** 110 English Wikipedia articles, each read at its last
  revision **before 2022-11-01** (the corpus cutoff, so human by
  construction), parsed to plain text, filtered to ≥120 tokens. Encyclopedic
  register, the one MATTR must not over-flag.
- **AI contrast:** the four AI fixtures listed in `scripts/fp_measure.py`
  (`FIXTURE_TP`): `ai-slop-general.md`, `artifact-leakage.md`,
  `wiki-promotional.md`, `over-humanized.md`.
- The finding was modelled as "fires when MATTR ≤ threshold."

## Result

Human encyclopedic MATTR: mean 0.75, median 0.76, p10 0.69, p05 0.64, min
0.46, max 0.86. A low, wide band.

The four AI fixtures score **higher**, 0.84 to 0.89. Their AI-ness lives in
vocabulary, formatting, and rhetoric, not in lexical repetition.

| MATTR threshold | Human encyclopedic false-positive | AI-fixture catch (n=4) |
|---|---|---|
| ≤ 0.68 | 9.1% | 0% |
| ≤ 0.70 | 12.7% | 0% |
| ≤ 0.72 | 21.8% | 0% |
| ≤ 0.76 | 49.1% | 0% |
| ≤ 0.80 | 80.0% | 0% |

No threshold in the table catches a single AI fixture, and every threshold
that would reach them (≥ 0.84) flags nearly all human articles.

## Limits

- **Length mismatch:** The fixtures hold 62 to 93 tokens; the human articles
  were filtered to at least 120 and most are far longer. Short samples score
  high on diversity, so the gap above is partly length, not register. The
  comparison is not length-matched.
- **Four fixtures are an anecdote:** They tuned the audit rules and are not
  a labelled machine corpus. There is no machine-generated corpus in the repo
  to establish a true-positive rate, so the signal's value is unproven either
  way.
- **The human figures are not reproducible from this repo:** The 110-article
  sample was pulled ad hoc (the hash-only corpus cache was unavailable in the
  build clone). No revision ids or script were committed, and the figures
  were computed before the audit tokenizer learned accented letters and
  curly apostrophes.
- **Correction:** The 4.12.0 release of this page gave an AI range of
  0.71 to 0.92 and catch rates of 12.5% and 37.5%. That contrast set wrongly
  included the human control (`clean-human.md`, 0.92), `style-elements.md`
  (0.71), and two fidelity fixtures (0.78 and 0.79). Every "catch" in the old
  table was a non-AI fixture. The corrected numbers above use `FIXTURE_TP`
  only, and the conclusion stands with more force.

## Decision

Ship MATTR as a **diagnostic stat**, not a finding or score input. It stays
available for analysis, such as spotting long repetitive text by eye or in
downstream tooling, without a threshold the data does not justify. Revisit
only with a labelled, length-matched, long-form machine corpus, built with a
committed script so the numbers can be rerun.
