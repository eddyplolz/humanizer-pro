# Changelog

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
