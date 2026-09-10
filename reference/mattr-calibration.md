# MATTR calibration — why it is a stat, not a finding

MATTR (moving-average type-token ratio, 50-token windows) was evaluated as a
candidate lexical-diversity **finding** — the theory being that AI text reuses
vocabulary and so scores a lower MATTR than human prose. The calibration below
did not support that theory on the register this skill most often audits, so
MATTR ships as a **diagnostic stat only**: reported in the `stats` block, never
a finding, never a score input.

## Method

- **Human baseline:** 110 English Wikipedia articles, each read at its last
  revision **before 2022-11-01** (the corpus cutoff — every such revision
  predates ChatGPT, so it is human by construction), parsed to plain text,
  filtered to ≥120 tokens. Encyclopedic register, the one MATTR must not
  over-flag. (The in-repo hash-only corpus cache was unavailable in the build
  clone, so a fresh public human baseline was pulled for this measurement.)
- **AI contrast:** the repo's own `eval/fixtures/*.md` slop samples.
- MATTR computed with the shipping `moving_avg_type_token_ratio` (window 50,
  lowercased tokens), the finding modelled as "fires when MATTR ≤ threshold."

## Result

Human encyclopedic MATTR: mean 0.75, median 0.76, p10 0.69, p05 0.64, min 0.46,
max 0.86 — a low, wide band. The AI-slop fixtures scored **higher** (0.71–0.92),
because they are short and lexically varied; their AI-ness lives in vocabulary,
formatting, and rhetoric, not in lexical repetition.

| MATTR threshold | Human encyclopedic false-positive | AI-fixture catch |
|---|---|---|
| ≤ 0.68 | 9.1% | 0% |
| ≤ 0.70 | 12.7% | 0% |
| ≤ 0.72 | 21.8% | 12.5% |
| ≤ 0.76 | 49.1% | 12.5% |
| ≤ 0.80 | 80.0% | 37.5% |

No threshold separates the classes: one safe for encyclopedic prose catches no
AI, and one that catches AI floods false positives on wiki articles. There is
also no machine-generated corpus in the repo to establish a true-positive rate,
so the signal's real value is unproven either way.

## Decision

Ship MATTR as a **diagnostic stat**, not a finding or score input. It stays
available for analysis (e.g. spotting genuinely repetitive long text by eye or
in downstream tooling) without imposing a threshold the data does not justify.
Revisit only if a labelled long-form machine-generated corpus becomes available
to test MATTR's intended target case (long, repetitive AI prose).
