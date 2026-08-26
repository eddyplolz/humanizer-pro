# Changelog

## 4.6.0 - 2026-08-26

- Added the hash-only, anonymous human-control corpus: `corpus/manifest.json` carries register,
  author tier, date, word count, and SHA-256 digest for 1,345 documents (~639k words) that all
  predate ChatGPT (cutoff 2022-11-01), so any audit flag on one is a false positive by
  construction. No text, usernames, or source locators are published — ids derive from the
  content digest, and a test enforces the anonymity contract. `scripts/corpus.py` builds and
  verifies the corpus from maintainer-local sources; only the public-domain slice is
  independently rebuildable, on purpose.
- Added `scripts/fp_measure.py`: false-positive rates by register and author slice with Wilson
  95% intervals, a review-threshold sweep, and the rules firing most often on human text.
  Measured at the default threshold: chat 0.0% (n=764), essay 0.0% (n=33), wiki 9.1% (n=550) —
  the aggregate (3.7%) hides the register split, which is why rates are reported per register.
  Results published in `corpus/RESULTS.md`.
- One hard block on human text is recorded honestly: a 2014 forum post carrying two invisible
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
