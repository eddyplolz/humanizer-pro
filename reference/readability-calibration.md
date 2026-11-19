# Readability: why it is a stat, not a finding

The audit reports two readability numbers in the `stats` block:
`fk_grade` (Flesch-Kincaid grade) and `syllables_per_word`. Neither is a
finding, and neither moves the risk score. This page says why.

## Method

- Flesch-Kincaid grade = 0.39 x words per sentence + 11.8 x syllables per
  word - 15.59. It approximates a US school grade and can fall below zero
  for very plain text.
- Only words inside sentences count. Markdown headings are not sentences,
  so their words are left out too.
- Syllables come from a vowel-group count with a silent final "e". It is a
  heuristic for English, not a dictionary lookup.
- `fk_grade` is `null` when the text has no sentence (for example, headings
  only).
- `scripts/fp_measure.py` reports the median grade of human and machine
  text in each register, and the AUROC of the grade, on the test split.
  The table is in `corpus/RESULTS.md` under "Reading grade by register".

## Result

Test split, full corpus:

| Register | Human n | Machine n | Human median | Machine median | AUROC |
|---|---|---|---|---|---|
| chat | 450 | 365 | 8.8 | 9.8 | 0.60 |
| docs | 303 | 43 | 10.6 | 7.4 | 0.08 |
| essay | 474 | 48 | 10.1 | 7.0 | 0.14 |
| news | 263 | 185 | 11.7 | 11.2 | 0.42 |
| wiki | 4 | 193 | 10.1 | 12.4 | 0.69 |

The gap points in different directions in different registers. Machine
chat replies read at a slightly higher grade than human ones. Machine docs
and essays read at a much lower grade than human ones. News is close. Wiki
shows a higher machine grade, but it rests on 4 human articles.

## Why no rule

- One global rule would point the wrong way in some register. A rule that
  treats a high grade as a tell would likely flag academic and technical
  writers; one that treats a low grade as a tell would likely flag students
  and second-language writers. The corpus does not measure the second group.
- The two strong gaps rest on small machine slices (43 docs, 48 essays),
  and the machine docs and essays all come from Claude models.
- About half the human essays are a century old, so part of the essay gap
  may come from era rather than authorship.
- The grade is rough on text with few full stops (lists, code, old books)
  and means little outside English.

BFI Working Paper 2025-116 also treats readability as a property it aims
to match between its human and machine sets, not as a detector input. Its
human-machine grade gap still changes sign across genres: machine text
reads higher for reviews, blogs, and news, and lower for resumes.

Revisit only with larger machine slices per register, decided on the dev
split and checked on the test split.
