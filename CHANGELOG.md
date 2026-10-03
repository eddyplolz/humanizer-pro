# Changelog

## Unreleased

- README: the measurement section now says what was measured (1,912 documents with the 4.12.0
  rules), that the public collection holds no AI text yet, and that the dev/test split applies
  from the next measurement on. The newspaper date range is 1898 to 1909. Install snippets pin
  the current release, and a test keeps them pinned.
- SKILL.md: the description is 810 characters, under the 1,024-character skill-loader limit (it
  was 1,049), and a test keeps it there. The audit CLI is resolved from the skill's own directory
  or the installed `humanizer-audit` command, never from the working directory.
- Self-scan budget for SKILL.md lowered from 95 to 60 after the description shrank.
- Fixture names are invented in a test fixture and two source notes.

Audit CLI:

- New artifact rule `artifact.assistant_self_disclosure` (severity error, exit 2): "As an AI
  language model, I…", "I'm just an AI", "I don't have access to real-time data", "I cannot
  browse the internet". The most recognizable chatbot leak scored zero before this.
- `family9.chatbot_residue` now catches the knowledge-cutoff variants: "as of my knowledge cutoff
  in 2023", "up to my last training update", "my training data only goes up to".
- `family7.rhetorical_formula` now catches the "not just X; it's Y" and "not just X. It's Y."
  contrasts, anchored on a preceding copula so "had not just arrived" stays clear.
- `artifact.bracket_placeholder` now covers generic fill-in blanks such as `[Recipient Name]`,
  `[Company]`, `[Date]`, and skips Markdown links, reference links, and wiki links.
- Each change has a regression test that failed before it. The false-positive rates in
  `corpus/RESULTS.md` were not re-measured for these rules; the next corpus run covers them.
- Document paths in text and JSON output use forward slashes on every OS, as the SARIF
  output already did. On Windows they were backslashes.

GitHub Action and CI:

- The Action picks the first `python3` or `python` that actually runs. On a Windows runner
  `python3` can be the Microsoft Store alias, which is on PATH but exits without running.
- CI now runs the test suite on Windows and macOS (Python 3.12) as well as Ubuntu. The
  README leads with Windows instructions; until now nothing tested them.

## 4.14.1 - 2026-10-03

Corpus and documentation.

- The forum and wiki pools' entries are kept in a local manifest; the public manifest lists their
  totals (`private_pools`), and public-source digests stay public so anyone can verify them.
  `corpus.py` and `fp_measure.py` read both files when the local one exists.
- Test fixtures and code comments use invented examples.
- README: a "Your privacy" section says what the checker, the skill, SARIF output, and the
  GitHub Action do with your text.
- CLAUDE.md: conventions for commit identity and examples.

## 4.14.0 - 2026-10-03

Two-way measurement and distribution. No catch rate is published yet: the machine pools are
built from Hugging Face, RAID, and the Claude API, which the build machine for this release could
not reach. They are built locally and `fp_measure.py` rerun before the next measurement.

Audit CLI:

- Prose rules and stats skip fenced and inline code by default, so `utilize()` in a README no
  longer counts as wordiness. `--include-code` restores the old behavior. Artifact rules and
  bypass characters still see the whole text: a chatbot reply pasted inside a ```markdown fence
  keeps its leaked tokens, and still blocks. Fences count only when they open and close a line,
  so a sentence that mentions ``` cannot hide the prose after it. Self-scan's raw column still
  counts every match.
- Several targets in one run (needed by pre-commit), `--version`, and `--sarif PATH` for SARIF
  2.1.0 output in audit and compare mode (checked against the official schema; columns are
  declared as Unicode code points).
- Installable: `pyproject.toml` ships `humanizer_audit` as the zero-dependency `humanizer-audit`
  command (`pipx install git+https://github.com/eddyplolz/humanizer-pro`).
- A pre-commit hook (`.pre-commit-hooks.yaml`) and a composite GitHub Action (`action.yml`). The
  action passes inputs through environment variables, never into the script text, accepts
  space- or newline-separated `paths`, removes a stale SARIF file before running, and takes
  `fail-on: block|review|never`.
- CI: tests on Python 3.10-3.13, self-scan, a package install, and an action smoke test.

Corpus and measurement:

- Manifest entries carry `label` (human or machine). Machine entries add the generating `model`.
  Every document, human or machine, falls in a dev or test split chosen by its digest: about a
  quarter dev, the rest test.
- New pools:
  - `build-peps`: a docs-register human pool from Python Enhancement Proposals, read at the
    python/peps commit current at the cutoff (public-domain PEPs only).
  - `build-raid`: RAID's non-adversarial training file (MIT); sampled generations without
    repetition penalty, from chat and instruction-tuned models only.
  - `build-wildchat`: WildChat-1M first replies in English with no code (ODC-BY).
  - `scripts/generate_machine.py`: current Claude models on 60 committed prompts across wiki,
    news, essay, and docs. It uses the official SDK and no refusal fallbacks, so each label names
    the model that wrote the text. `--limit` is a trial run that saves nothing, and a run that
    produces nothing keeps the existing pool.
  - Every builder that can come back empty (`build-peps`, `build-raid`, `build-wildchat`,
    `build-hf-news`) now keeps the existing pool instead of saving an empty one. `build-peps` also
    checks the pinned commit's date itself and stops if any download fails.
- `fp_measure.py` (results schema v2) publishes both rates on the test split only: the
  false-positive rate on human test documents, and the catch rate on machine test documents, by
  register and by model, with Wilson intervals and the same "flagged" definition. A rule scorecard
  compares each rule's firing rate on human dev and machine dev documents; it is the one place
  rule tuning may look, so neither published rate grades its own tuning.
- Wiki entries carry the `mixed` author tier. A wiki page holds other
  editors' text too. Only the label changed; digests and ids did not.

Docs and checks:

- README: CI badge, a two-way results table that says plainly what isn't measured yet, real CLI
  output, and install, pre-commit, Action, and SARIF instructions.
- The SKILL.md self-scan budget drops from 100 (a ceiling the score can't exceed, so never a gate)
  to its measured 95.
- A test keeps the version in `humanizer_audit.py`, SKILL.md, CHANGELOG.md, and README.md in step.
- README rewritten in plain-language, task-first style (GOV.UK conventions, American English), with
  a contents list, numbered setup steps, and an options table for the GitHub Action.
- A release workflow publishes a GitHub release once CI passes on `main` for a version with no
  release yet, using that version's CHANGELOG section as the notes. It runs only after a
  successful CI run for a push to `main`.

## 4.13.0 - 2026-10-03

Fixes from a full-repo review. Rule changes below only stop false or double matches, but they
were made without the corpus cache, so `corpus/RESULTS.md` still shows 4.12.0 numbers until the
`scripts/fp_measure.py --write-results corpus/RESULTS.md` is rerun.

Audit CLI:

- Usage errors (no input, unknown flag, bad `--fail-score`) now exit 3 as documented. argparse
  exited 2, the code reserved for "block", so a typo in a CI command read as a leaked artifact.
- `family7.rhetorical_formula`: "not just ... but" and "not only ... but also" must sit in one
  sentence. The DOTALL pattern matched "not just" in one paragraph to the last "but" anywhere later.
- `family9.chatbot_residue`: "of course!" now matches. Its closing `\b` after "!" only matched when
  a letter followed with no space, so the phrase never fired in real text.
- One phrase, one score: "it is important to note" is family5-only (it was also family3), and
  "has the ability to" is family6-only (it was also `clarity.wordiness`).
- `family4.ai_vocab_cluster` counts distinct words. One topical word repeated ("robust ...
  robust ... robust") no longer reads as a cluster.
- The word tokenizer handles letters in any script, curly apostrophes, and multi-part hyphenated
  words. "café" was split into "caf", and "don’t" into two words, which skewed word counts,
  sentence lengths, and MATTR.
- `mattr_50` is `null` below one 50-token window instead of silently falling back to plain TTR, a
  window below 1 raises `ValueError` instead of dividing by zero or going negative, and the
  computation is a linear sliding count.
- `--stdin` decodes strict UTF-8 like file input (not the platform locale) and normalizes newlines.
- A directory with no `.md` or `.txt` files now says so on stderr.
- The `structure.low_sentence_variance` message was a cut-off sentence; it is complete now.

Compare mode:

- Quotes and code blocks are aligned before comparison. Dropping the first quote used to shift every
  later quote into a false "changed" pair and report the wrong quote as dropped.
- A retargeted link is caught when its label repeats; the label map kept only the last link.
- Tilde (`~~~`) fences count as code blocks, in compare and in `code_block_count`.

Corpus and measurement:

- The Strunk pool no longer includes the Project Gutenberg header and licence. Seven of the 33
  "1918 Strunk" chunks held that modern text. The pool is rebuilt from the repo: 27 chunks, and the
  manifest now has 2,145 entries.
- `fp_measure.py` counts a blocked (exit 2) human document as a false positive at any score; it
  was listed only in a side column. The median is a true median, the "CLI default" label shows only
  for the default threshold, and an empty cache no longer renders a broken sweep table.
- Cache reads are byte-exact in `verify` and `fp_measure.py`, and entry ids are checked before any
  path is built from them.
- Corpus extraction fixes, versioned so existing entries still verify:
  - `bbcode-strip.v2`: nested quote blocks are removed inside out, so an inner quote no longer
    leaks the outer quoted author's words into the post, and SQL escapes are decoded in one pass
    (`C:\\new` stayed a newline before).
  - `build-forum` reads each post's `edittime` and drops posts edited after the cutoff, since
    MyBB stores the edited text in place. It counts rows whose dump has no parseable `edittime`.
  - `wikitext-strip.v2`: templates and links resolve innermost first until nothing changes. A
    media caption holding a link no longer leaves `]]` behind, and templates nested deeper than
    four levels are removed. `wikitext-strip.v1` is kept unchanged, and `fetch` rebuilds each wiki
    entry with the extractor it was built with.
  - The word counter and the OCR alphabetic gate count curly apostrophes inside words
    (`ocr-chunk.v3`, `chunk.v2`), and OCR cleaning folds stray carriage returns.
- The audit's text report no longer crashes (exit 1, read as "review") when a Windows pipe can't
  encode quoted evidence; characters the stream can't hold are escaped.
- `build-news` retries rate limits and transient failures (a read timeout used to abort the whole
  build) and sorts its Internet Archive search so reruns select the same issues. The dead loc.gov
  retry helper is gone. `fetch` batches wiki revisions per API endpoint, names the `build-*`
  command for each missing kind, and exits 1 while entries stay uncached.

Docs:

- `reference/mattr-calibration.md` corrected: the 4.12.0 "AI contrast" set included the human
  control and three other non-AI fixtures. On the four real AI fixtures MATTR is 0.84 to 0.89 and
  no threshold in the table catches any of them (previously reported as 0.71 to 0.92, with catch
  rates of 12.5% and 37.5%). The page now states the length mismatch and that the human figures
  can't be reproduced.
- SKILL.md is back under its 350-line limit (the second-pass list moved to
  `reference/tell-catalog.md`); a test now enforces it.
- WARP.md, README.md, and scripts/README.md file lists and commands brought up to date.

## 4.12.0 - 2026-09-10

- Added **MATTR** (moving-average type-token ratio over 50-token windows) as a diagnostic stat in the
  `stats` block, alongside the existing `type_token_ratio`. MATTR is length-robust: it averages the
  type-token ratio of a sliding fixed-size window instead of dividing uniques by total, so it does not
  decay as a document grows.
- **Reported as a stat only — deliberately NOT a finding and NOT a score input.** Calibration against
  110 pre-2022-11-01 Wikipedia article revisions (encyclopedic register) found human MATTR spans a low,
  wide band (median ~0.76, 10th percentile ~0.69, min ~0.46), while the repo's AI-slop fixtures score
  *higher* (0.71-0.92). No flagging threshold separates the two: one safe for encyclopedic prose (<=0.68,
  ~9% false-positive) catches none of the AI fixtures, and one that catches AI floods false positives on
  exactly the register this skill most often audits. With no machine-generated corpus to establish a
  true-positive rate, MATTR is surfaced for analysis, not verdicts. Method and figures:
  `reference/mattr-calibration.md`.
- *Corrected in 4.13.0:* the AI-fixture range and catch rates above came from a contrast set that
  included the human control and other non-AI fixtures. The four AI fixtures score 0.84-0.89 and
  none is caught at any threshold in the table.

## 4.11.2 - 2026-09-10

- Renamed the bypass count from `zero_width` to `invisible` in the counts dict, the
  `artifact.bypass_characters` evidence string, and its message. The bucket has covered tag
  characters, noncharacters, invisible math operators, and the Mongolian vowel separator since
  4.11.0, so a tag-character-only hit no longer reports as "zero-width."
- Added tests for the always-strip codepoints that shipped untested in 4.11.0: the invisible math
  operators (U+2061-U+2064) and the Mongolian vowel separator (U+180E) now have strip-and-flag
  coverage.
- Dropped the redundant regional-indicator (U+1F1E6-1F1FF) and skin-tone (U+1F3FB-1F3FF) clauses in
  the emoji-context test; both are already inside the U+1F000-1FAFF block. No behavior change.

## 4.11.1 - 2026-09-09

- Closed a variation-selector bypass hole introduced with the preserve-list in 4.11.0. Two or more
  variation selectors (VS15/VS16) placed side by side between ordinary letters used to treat each
  other as legitimate emoji context, so a run of them survived the bypass pass uncounted. A selector
  now anchors only to a real emoji base, never to another selector, so injected runs are stripped and
  counted while genuine emoji sequences (heart, keycap, family) are still preserved byte-for-byte.
- Bumped `SKILL.md` and the README to match; both still advertised 4.10.1 after the 4.11.0 change.

## 4.11.0 - 2026-09-09

- Hardened the detector-bypass normalization against two newer text-hiding tricks and one
  corruption bug. The audit now always strips **Unicode tag characters** (U+E0000–E007F) and
  **noncharacters** (U+FDD0–FDEF and every plane's U+xFFFE/U+xFFFF), which render as nothing and
  carry hidden payloads; both now count toward `artifact.bypass_characters`.
- Added a **preserve-list** so the bypass pass no longer corrupts legitimate multilingual text.
  The zero-width joiner/non-joiner and the variation selectors (VS15/VS16) are kept when a
  neighbour proves a real context — an emoji ZWJ sequence, a Persian/Arabic non-joiner, a
  Devanagari ligature, an emoji variation selector or keycap — and stripped only where they sit
  between Latin letters with no shaping role. Previously ZWJ/ZWNJ were stripped unconditionally,
  which mangled emoji families and Indic/Arabic script.
- Six paired tests cover the new coverage and the preserve-list (byte-identity on legitimate
  strings, stripping on injected bypass characters). The single-class `ZERO_WIDTH_RE` was retired
  in favour of the neighbour-aware classifier.

## 4.10.1 - 2026-08-26

- Rewrote the README in plain language: GOV.UK-style plain-English principles in American
  English, with numbered one-action-per-step procedure blocks for install and CLI use. The
  structure now layers novice to advanced: what it does, a demo, the built-in refusals, a
  2-minute install, everyday phrasing, then the CLI, the nine families, the measured
  evidence, and credits.
- The README's own audit score fell from raw 100 / exemption-adjusted 60 to raw 65 /
  adjusted 35; its self-scan budget re-baselines 65 → 40 (measured + 5, downward only).
  The residual raw score is mostly the tells the README quotes in order to warn about them.
- Moved the pre-4.2 version history (4.1.0 back to 1.0.0) from the README into this
  changelog; the README now carries the current release plus a pointer here. Nothing was
  deleted.

## 4.10.0 - 2026-08-26

- Recalibrated the two audit rules that drove the wiki register's false-positive rate,
  measured against the human-control corpus: **wiki FPR at threshold 60 drops from 9.1% to
  1.5%** (8/548, 95% CI 0.7–2.9%); chat, essay, and news stay at 0.0%, and all four in-repo
  AI fixtures keep their exact risk scores.
- `family7.rhetorical_formula` no longer carries the naive two-word triplet pattern
  ("\w+ \w+, \w+ \w+, and \w+ \w+"): it fired on 33% of human wiki documents — ordinary
  enumerations of names, offices, and places — and three hits force-floor the score to
  review. The ten explicit formula phrases remain; rule-of-three judgment is model-side
  (catalog §7.3, coverage map).
- `family8.markdown_structure` now reports once per document (new `once_per_doc` rule
  attribute). Table-heavy human documents matched ~29 lines each, so this one rule maxed
  the family score cap and tripped the ≥10-findings review floor on its own; whether
  mechanical structure is present is a document-level fact.
- Two regression tests cover the recalibrations (suite: 39).
- `fp_measure.py`'s generated results page now states how many manifest entries had no
  cached text and were skipped — the text report already warned; the Markdown page
  silently narrowed its document count.
- `corpus/RESULTS.md` regenerated. Provenance note: 239 of the 500 news-pool documents
  could not be re-fetched from their public sources at release time (Internet Archive
  search returned a different issue set; some upstream rows drifted), so the news row
  re-measures n=261. The manifest is unchanged — those documents remain part of the
  corpus — and this release only removes findings, so the v4.9.0 news result (0.0% at
  n=500) is not weakened.

## 4.9.0 - 2026-08-26

- Grew the news pool from 150 to 500 documents using OpenCulture's US-PD-Newspapers dataset
  (PleIAs, public domain) via the Hugging Face rows API — stdlib-only, deterministic fixed
  offsets, dates capped at 1928, the same per-chunk OCR-quality and English gates, failed
  offsets skipped and counted. The news register's FPR stays 0.0% and its 95% upper bound
  tightens from 2.5% to 0.8%; every other register is unchanged (corpus now 2,151 documents).
- The paired US-PD-Books dataset was deliberately not added: its rows are novels, and fiction
  poured into the essay register would blur that slice's claim rather than strengthen it.
- Chunker v2 (`ocr-chunk.v2`): paragraphs past the chunk cap now split on line boundaries, so
  sources that emit a whole page as one block chunk correctly; earlier entries keep their
  truthful v1 tag.

## 4.8.0 - 2026-08-26

- Adopted the writing-quality half of harshaneel/humanize (MIT), and deliberately none of its
  detector-related code.
- SKILL.md process: a **counted gate** (write every check's count with zeros explicit; list every
  sentence's word count and fix the list until it passes range/mid-band/neighbor rules — counting
  beats feel) and the **own-output-is-foreign-text** rule for rewriting text you drafted earlier.
- Catalog: §7.12 thesis-first openers and setup sentences, §7.13 anaphora and parallel-subject
  mirrors, §7.14 chiasmus and balanced symmetry, §7.15 parallel reason chains, §9.11 RLHF
  helpful-assistant framing.
- CLI: `structure.anaphora` (3+ consecutive sentences sharing an opener, stopword-guarded),
  `structure.uniform_length_run` (**calibrated against the human-control corpus**: a threshold of
  4 fires on 40% of human documents, the shipped 6 on 11%), `structure.midband_dominance`; RLHF
  framing phrases extend `family9.chatbot_residue`; filler wrappers extend `clarity.wordiness`
  (zero risk weight; "due to the fact that" stays family-3-only to avoid double counting).
- Measured FPR at threshold 60 is unchanged by the new rules: chat 0.0%, essay 0.0%, news 0.0%,
  wiki 9.1% — the corpus gated a rule calibration before it shipped, which is what it is for.
- Self-scan budgets re-baselined (measured + 5) because the new rules fire on this repo's own
  docs; that is a measuring-stick change, not a prose regression.

## 4.7.0 - 2026-08-26

- Widened the human-control corpus with two public-domain pools: a **news register**
  (Internet Archive newspaper issues, 1900-1922, chunked to ~600-word documents and gated per
  chunk on OCR quality and an English check, with every drop counted) and a broader **essay
  pool** (Gutenberg: Emerson, Thoreau, Twain, chunked like the existing Strunk text). Four of
  the six registers the skill defines are now measured.
- New corpus subcommands `build-news` and `build-essays`; fetching is rate-limit-aware
  (backoff on 429/503). Public-domain pools publish their sources for reproducibility; the
  forum and wiki pools publish no locators (unchanged contract, still test-enforced).
- The news slice is page-level OCR of century-old newsprint — the
  quality gate (alphabetic-token ratio) bounds but does not eliminate OCR noise, and
  `corpus/RESULTS.md` states that caveat next to the numbers.

## 4.6.0 - 2026-08-26

- Added the hash-only, anonymous human-control corpus: `corpus/manifest.json` carries register,
  author tier, date, word count, and SHA-256 digest for 1,345 documents (~639k words) that all
  predate ChatGPT (cutoff 2022-11-01), so any audit flag on one is a false positive by
  construction. No text, usernames, or source locators are published — ids derive from the
  content digest, and a test enforces the anonymity contract. `scripts/corpus.py` builds and
  verifies the corpus from local sources; only the public-domain slice is
  independently rebuildable, on purpose.
- Added `scripts/fp_measure.py`: false-positive rates by register and author slice with Wilson
  95% intervals, a review-threshold sweep, and the rules firing most often on human text.
  Measured at the default threshold: chat 0.0% (n=764), essay 0.0% (n=33), wiki 9.1% (n=550) —
  the aggregate (3.7%) hides the register split, which is why rates are reported per register.
  Results published in `corpus/RESULTS.md`.
- One hard block on human text is recorded: a 2014 forum post carrying two invisible
  zero-width characters (ordinary copy-paste residue) trips `artifact.bypass_characters`.
  Corpus and measurement design adapted from conorbronsdon/avoid-ai-writing (MIT).

## 4.5.0 - 2026-08-26

- Added `reference/registers.md`: per-register strictness (wiki/news/essay/docs/chat/commit) with
  auto-detection cues — the same pattern can be a tell in one register and the correct form in
  another. SKILL.md now requires naming the register before editing.
- Added `reference/coverage-map.md`: the anti-drift contract between catalog prose and CLI rule
  ids, including a recorded judgment-only list (why certain rules deliberately have no regex).
  A new test fails if a CLI rule id is missing from the map.
- Added `scripts/self_scan.py` + `self_scan_budgets.json`: runs the audit over this repo's own
  docs, reporting raw and exemption-adjusted scores (fenced/inline code, tables, blockquotes,
  and quoted spans are exempt as documented self-reference). Budgets gate the exempt score in
  pytest; they are measured regression ceilings and only move down.
- Ideas adapted from conorbronsdon/avoid-ai-writing's tolerance matrix, CATEGORIES.md, and
  PROOF.md (MIT).

## 4.4.0 - 2026-08-26

- Tiered the AI vocabulary: Tier 1A frequency markers (two distinct 1A words anywhere now fire the
  cluster) vs. Tier 2 cluster-only words; the frequency claims are marked as inherited from the
  source catalogs, not measured here.
- Split wordiness (utilize, commence, facilitate, endeavor, ascertain) into `clarity.wordiness`:
  info severity, no tell family, zero risk-score weight, own `clarity_hit_count` in the summary —
  a clarity fix can never push a document toward an AI classification.
- Voice rules now carry the provenance test ("did this information come from the source? subtract
  and sharpen, never add") with explicit never-inject items: fake first person, invented specifics,
  manufactured stakes/contrarianism, staccato conversion. Compare mode is wired into the anti-swap
  check: `compare.*.introduced` findings after a deep edit are anti-swap failures.
- New detectors: `family2.speculative_gap_filling` ("is believed to have," "likely began"),
  `family2.vague_validation` ("independent testing confirms," "analysts agree"),
  `family8.list_label_period` (`**Label.** gloss` where a person writes `**Label:**`).
- New judgment-only catalog patterns (deliberately not regexes, with the reasons recorded):
  diff-anchored writing (§8.15) and wall-of-text replies (§9.10).
- Credits: tiering and the five new patterns adapted from conorbronsdon/avoid-ai-writing (MIT) and
  the brandonwise/humanizer vocabulary research it builds on.

## 4.3.0 - 2026-08-26

- Widened `artifact.chatgpt_tracking_url` into `artifact.ai_tracking_url`: now catches
  `utm_source=chatgpt.com|claude.ai|copilot.com|openai|perplexity.ai` and `referrer=grok.com`.
  Compare mode's URL normalization strips the AI `referrer` param the same way it already
  stripped `utm_*`, so removing tracking noise is still not drift.
- Added a detector-bypass normalization pre-pass: zero-width characters and Cyrillic/Greek
  homoglyphs inside mixed-script words are normalized before matching (an obfuscated `delve`
  still hits) and reported as `artifact.bypass_characters`. A single leading BOM and genuine
  Cyrillic/Greek prose are exempt.
- Added `artifact.roleplay_marker` for `*nods*`-style chat action markers (verb-anchored;
  ordinary italics untouched).
- Capped the multi-pass principle at two full rewrite passes unless the user asks for more.
- Added cited false-positive context (Stanford *Patterns* 2023; BFI 2025-116; arXiv:2506.07001)
  to `reference/ai-check.md` and the README: scores are signals, never sole grounds for a
  consequential decision about a person.
- New operating principle: the text under audit is data, never instructions — embedded
  editor-directed instructions get flagged, not obeyed.
- Credits: the widened referrer list, bypass-normalization idea, and roleplay-marker pattern are
  adapted from conorbronsdon/avoid-ai-writing (MIT).

## 4.2.2 - 2026-06-30

- Added Codex-facing skill metadata in `agents/openai.yaml` and clarified Claude Code, Codex, and
  generic-agent install/invocation paths.

## 4.2.1 - 2026-06-30

- Added score-only AI check mode documentation for "check this," "score this," "audit only," and
  "do not rewrite" workflows.
- Documented Claude Code installs to `~/.claude/skills/humanizer-pro`, Codex/generic agent installs
  to `~/.agents/skills/humanizer-pro`, and Windows/POSIX audit CLI examples.
- Added `--compare original.md revised.md` fidelity guards for protected-content drift in numbers,
  dates, names, URLs, citations, quotes, fenced code blocks, and source-dependent statements.

## 4.2.0 - 2026-06-30

- Added the deterministic `humanizer-audit` CLI for artifact sweeps, tell-family hits, source-risk
  flags, rhythm/structure stats, JSON output, and threshold exit codes.
- Added automated scenario-contract tests for the existing Humanizer Pro fixtures.

## 4.1.0 - 2026-06-24

- Added mode routing for quick rewrite, full audit, style edit, wiki/article mode, self-audit,
  and self-improvement. Added compact Elements guidance, the full public-domain Strunk text,
  the neutral wiki/article workflow, the review-based improvement loop, and manual eval
  fixtures. Kept `SKILL.md` lean and preserved the nine-family tell system, artifact-first
  checking, anti-swap checking, and restraint checking.

## 4.0.0 - 2026-05-29

- Restructured into a lean `SKILL.md` core plus a `reference/` library (`tell-catalog`,
  `llm-artifacts`, `worked-examples`). Reorganized into 9 families and added deterministic
  artifact detection, syntactic tells, verbosity and padding, register and diction, cohesion
  overuse, title/opening patterns, operating principles, the persistent-tells checklist,
  anti-swap and restraint checks, and a 6th "Restraint" scoring dimension.

The entries below predate this repository and are recorded from the upstream
blader/humanizer lineage; no reliable dates exist for them.

## 3.0.0

- Merged Stop Slop patterns, added Quick Checks and the 5-dimension scoring system.

## 2.2.0

- Added a final "obviously AI generated" audit and second-pass rewrite prompts.

## 2.1.1

- Fixed pattern #18 example.

## 2.1.0

- Added before/after examples for all 24 patterns.

## 2.0.0

- Complete rewrite based on raw Wikipedia article content.

## 1.0.0

- Initial release.
