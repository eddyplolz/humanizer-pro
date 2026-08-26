# Humanizer Pro

Humanizer Pro is a Claude Code and Codex skill for turning AI-assisted drafts into publishable prose
without fake-casual "make it sound human" tricks.

It removes AI-writing tells, citation/artifact residue, promotional padding, wiki puffery, and
formulaic rhythm while preserving clean human prose. It is not a synonym spinner, detector-bypass
gimmick, or personality injector.

*A standalone rebuild of [blader/humanizer](https://github.com/blader/humanizer) (MIT). See
[Credits & licensing](#credits--licensing).*

## Why Use This?

- **De-slop drafts without over-editing.** The restraint check protects prose that already works.
- **Catch AI residue before it ships.** Flags `turn0search0`, `contentReference`, `oaicite`,
  AI-referrer URL params (`utm_source=chatgpt.com`, `utm_source=claude.ai`, `referrer=grok.com`,
  and friends), `*nods*`-style roleplay markers, zero-width/homoglyph detector-bypass characters,
  placeholder dates, and unfinished template fields.
- **Check without rewriting.** AI check mode returns score, blocker flags, family hits, source-risk
  notes, and quoted evidence when you ask for "check this," "score this," or "do not rewrite."
- **Avoid swapping one tell for another.** The anti-swap pass catches fake-casual voice, binary
  contrasts, rule-of-three filler, and motivational-poster endings introduced during edits.
- **Handle wiki and article prose.** Wiki/article mode neutralizes puffery, preserves citations, and
  flags unsupported claims instead of laundering them.
- **Stay local and simple.** No detector API, no external service, no autonomous optimization loop.

A note on honesty: every flag here is a signal, not proof of authorship. Independent audits report
false-positive rates above 60% on non-native English writers (Liang et al., Stanford, *Patterns*
2023) and heavy misclassification across detectors generally. Humanizer Pro scores writing tells;
it does not judge people, and its output should never be the sole basis for an academic-integrity,
hiring, or attribution decision.

## Quick Demo

**Before**

> In today's rapidly evolving digital landscape, effective collaboration serves as a crucial
> cornerstone for organizations seeking to unlock their full potential. It is important to note that
> this approach is not just about tools, but about creating a vibrant culture of innovation.

**After**

> Good collaboration depends less on the tool than on whether people know what decisions they own,
> where work is tracked, and how quickly blockers get resolved.

## What It Catches

Humanizer Pro works from a nine-family catalog:

- significance inflation and promotional tone
- vague attribution and notability padding
- superficial "-ing" analysis and filler
- AI vocabulary clusters and inflated diction (tiered: frequency markers vs. cluster-only words,
  with plain wordiness reported separately as a clarity edit, never as authorship evidence)
- syntactic tells such as anticipatory "it" and existential "there"
- verbosity, nominalization, false precision, and both-sides anxiety
- rhetorical formulas such as "not X, but Y" and forced triplets
- structure and formatting tells, including Markdown leakage
- chatbot residue, citation stubs, tracking links, and placeholders

## Installation

Clone the whole repository so `SKILL.md`, `agents/`, `reference/`, `scripts/`, and `eval/` stay
together.

### Claude Code

POSIX:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

Windows:

```bat
mkdir "%USERPROFILE%\.claude\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.claude\skills\humanizer-pro"
```

### Codex And Generic Agents

POSIX:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.agents/skills/humanizer-pro
```

Windows:

```bat
mkdir "%USERPROFILE%\.agents\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.agents\skills\humanizer-pro"
```

For standard Codex personal-skill installs, use `$CODEX_HOME/skills` when `CODEX_HOME` is set, or
`~/.codex/skills` otherwise. This repo also includes `agents/openai.yaml` so Codex can show a
friendly skill name, short description, and default `$humanizer-pro` prompt.

## Usage

Invoke the skill and paste text.

Claude Code:

```text
/humanizer-pro

[paste your text here]
```

Codex:

```text
Use $humanizer-pro to check this draft for AI-writing tells without rewriting it.

[paste your text here]
```

Or ask directly: `Please humanize this text: [your text]`.

Simple requests return a concise rewrite. Ask for a "full audit" to get scores, artifact flags,
family-tagged rationale, and the final rewrite after anti-swap and restraint checks.

Ask for "AI check," "score this," "audit only," or "do not rewrite" to get a score-only report with
blockers, family hits, source-risk notes, and quoted evidence. AI check mode does not rewrite unless
you separately ask for a rewrite.

### Deterministic Audit CLI

For file-based checks, use the zero-dependency audit CLI:

Windows:

```bat
py -3 scripts\humanizer_audit.py eval\fixtures\ai-slop-general.md
py -3 scripts\humanizer_audit.py eval\fixtures --json
py -3 scripts\humanizer_audit.py --compare original.md revised.md --json
```

POSIX:

```bash
python3 scripts/humanizer_audit.py eval/fixtures/ai-slop-general.md
python3 scripts/humanizer_audit.py eval/fixtures --json
python3 scripts/humanizer_audit.py --compare original.md revised.md --json
```

The CLI does not rewrite text. It reports artifact leakage, tell-family hits, source-risk flags,
rhythm/structure stats, JSON output, and threshold exit codes for CI or pre-publish review.
Compare mode checks fidelity only: protected numbers, dates, names, URL targets, citations, quotes,
code blocks, and source-dependent statements. It does not judge style or make detector claims.

## Modes

- **Quick rewrite** - simple "humanize this" or "make this less AI" requests. Returns the cleaned text
  plus serious source-risk notes.
- **Deep edit / full audit** - scores the text, reports artifact flags, names the tell families, and
  shows the final rewrite.
- **AI check / audit-only** - returns score, blocker flags, family hits, source-risk notes, and quoted
  evidence without rewriting.
- **Style edit** - uses the compact Elements of Style checklist in `reference/style-principles.md`.
  The full public-domain Strunk text is in `reference/elements-of-style-1918.md` and is loaded only on
  explicit request or deep style work.
- **Wiki/article mode** - uses `reference/wiki-mode.md` for Wikipedia-style, encyclopedic
  article, wikitext, neutral tone, citation, and source-bound writing requests.
- **Self-audit** - silently checks drafts before delivery.
- **Self-improvement** - uses `reference/improvement-loop.md` to review recurring failures before any
  rule is promoted.

## Overview

The skill synthesizes four sources:

- **[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**
  (WikiProject AI Cleanup) - prose tells and markup/placeholder leakage from real examples.
- **"Comprehensive Analysis of AI-Generated Writing Tells"** - syntactic, verbosity, register, and
  persistence layers, plus the "trying-to-sound-human" paradox.
- **[Stop Slop](https://github.com/hardikpandya/stop-slop)** by Hardik Pandya - blog and
  thought-leadership tells plus the scoring approach.
- **[The Elements of Style](https://www.gutenberg.org/ebooks/37134)** by William Strunk Jr. - compact
  clarity guidance, treated as advisory rather than absolute.

What makes v4+ different from a find-and-replace list: it edits clusters, preserves legitimate prose,
refuses to swap one tell for another, runs deterministic artifact checks first, and guards against the
over-humanizing paradox.

## File Layout

| File | Role |
|------|------|
| `SKILL.md` | Lean operating core: routing, principles, nine-family index, quick checklist, scoring, workflow, output formats. |
| `agents/openai.yaml` | Codex-facing display metadata and default `$humanizer-pro` prompt. |
| `reference/tell-catalog.md` | Full pattern library with watch-words and before/after examples. |
| `reference/llm-artifacts.md` | Deterministic detector for leaked tokens, placeholders, and AI citation residue. |
| `reference/ai-check.md` | Score-only audit mode for "check this," "score this," "AI check," and "do not rewrite" requests. |
| `reference/worked-examples.md` | Four full before/audit/after examples, including a restraint case. |
| `reference/style-principles.md` | Compact Elements of Style checklist for everyday style edits. |
| `reference/elements-of-style-1918.md` | Full public-domain Project Gutenberg text of Strunk's *The Elements of Style*. |
| `reference/wiki-mode.md` | Neutral, source-bound article workflow for wiki and encyclopedic prose. |
| `reference/registers.md` | Per-register strictness table with auto-detection cues. |
| `reference/coverage-map.md` | Anti-drift contract mapping catalog prose to CLI rule ids, with judgment-only rules recorded. |
| `reference/improvement-loop.md` | Review gate for promoting recurring skill failures into durable rules. |
| `scripts/humanizer_audit.py` | Deterministic CLI for artifact, source-risk, tell-family, rhythm, and JSON checks. |
| `scripts/self_scan.py` + `self_scan_budgets.json` | Runs the audit over this repo's own docs; budgets gate the exemption-adjusted score. |
| `eval/cases.md` | Manual validation matrix. |
| `eval/contracts/*.json` | Automated scenario contracts for the audit CLI. |
| `eval/fixtures/*.md` | Regression fixtures for clean prose, AI slop, wiki promotion, over-humanizing, artifacts, style edits, and fidelity compare checks. |
| `tests/` | Pytest coverage for the deterministic audit CLI. |

## The Nine Families of Tells

1. **Significance and promotional inflation** - "stands as a testament," "pivotal moment," brochure
   tone, copula avoidance.
2. **Vague attribution and notability** - "Experts believe," outlet name-drops, "active social media
   presence."
3. **Superficial analysis and filler** - trailing "-ing" depth, "In order to," hedging stacks,
   formulaic "Challenges" sections.
4. **AI vocabulary and diction** - clustered AI words, academic register, business jargon, modifier
   stacking, elegant variation.
5. **Syntactic tells** - anticipatory "it," existential "there," passive hedging, cleft emphasis,
   transition overuse.
6. **Verbosity and padding** - nominalization, redundant clarification, elaboration compulsion, false
   precision, both-sides anxiety.
7. **Rhetorical formulas** - binary contrasts, negative parallelism, rule of three, false ranges,
   dramatic fragmentation, fortune-cookie endings.
8. **Structure and formatting** - colon/gerund titles, title-case headings, boldface overuse, emojis,
   em-dash crutches, markup leakage.
9. **Chatbot residue and artifacts** - chat wrappers, cutoff disclaimers, summaries, English-variety
   drift, citation stubs, placeholders, and tracking parameters.

Full watch-words and examples live in `reference/tell-catalog.md`.

## Self-Improvement Loop

Humanizer Pro v4.1 adds a controlled promotion system:

Observation -> Candidate -> Fixture -> Review -> Promotion -> Regression check

A new rule is promoted only when it repeats or caused a serious miss, fits an existing family or
justifies a small sub-rule, can be stated in about 80 words, includes a before/after example, avoids
over-editing, and passes the clean-human restraint fixture. The loop is intentionally review-based:
no automatic memory accumulation, detector APIs, autonomous optimize-until-green loops, large scripts,
or one-off clever observations in `SKILL.md`.

## Validation

Manual validation lives in `eval/cases.md` and `eval/fixtures/`.

Expected checks include:

- `py -3 -m pytest -q tests` passes.
- `py -3 scripts/self_scan.py` exits 0: the repo's own docs stay within their recorded budgets.
  Both raw and exemption-adjusted scores are reported, on purpose — the raw number includes every
  tell this repo quotes in order to warn about it, and publishing only the flattering column is
  the behavior this project exists to criticize. Budgets are regression ceilings, not quality
  claims, and they only move down.
- `py -3 scripts/humanizer_audit.py eval/fixtures --json` emits schema `humanizer-audit.v1`.
- `py -3 scripts/humanizer_audit.py --compare eval/fixtures/fidelity/original.md eval/fixtures/fidelity/revised-drift.md --json`
  reports protected-content drift without style scoring.
- General AI-slop becomes plainer and more specific.
- Clean human prose remains mostly unchanged.
- Over-humanized prose loses fake-casual performance without becoming stiff.
- Wiki promotional prose becomes neutral and source-bound.
- Artifact leakage is flagged with source-risk notes.
- Elements-style edits improve clarity without flattening legitimate voice.

On POSIX systems, use `python3` in place of `py -3`.

## Version History

- **4.7.0** - Widened the corpus with two public-domain pools: a news register (Internet
  Archive newspaper issues 1900-1922, OCR-quality-gated) and a broader essay pool (Gutenberg:
  Emerson, Thoreau, Twain). Four of the six registers are now measured; the personal pools'
  anonymity contract is unchanged.
- **4.6.0** - Added the hash-only, anonymous human-control corpus (`corpus/manifest.json`,
  built by `scripts/corpus.py`; digests and registers only, never text or source locators)
  and measured false-positive rates by register (`scripts/fp_measure.py`, results in
  `corpus/RESULTS.md`). Every corpus document predates ChatGPT, so every flag on one is a
  false positive by construction; rates are reported per register with Wilson intervals
  because the aggregate hides the register split. No true-positive rate is claimed — there
  is no machine-generated corpus here yet.
- **4.5.0** - Added per-register strictness profiles (`reference/registers.md`), the
  prose-to-CLI coverage map with a test that every CLI rule id is mapped
  (`reference/coverage-map.md`), and the budget-gated self-scan
  (`scripts/self_scan.py`) that audits this repo's own documentation.
- **4.4.0** - Tiered the AI vocabulary (Tier 1A frequency markers vs. Tier 2 cluster-only) and
  split wordiness into `clarity.wordiness`, which carries zero risk weight so a clarity fix can
  never read as authorship evidence. Added the provenance test and never-inject guardrails to the
  voice rules, wired compare mode into the anti-swap check, and added five patterns: speculative
  gap-filling, vague third-party validation, list-label periods, diff-anchored writing, and
  wall-of-text replies.
- **4.3.0** - Widened AI-referrer URL detection beyond ChatGPT (claude.ai, copilot.com, openai,
  perplexity.ai, grok.com), added zero-width/homoglyph detector-bypass normalization and flagging,
  added roleplay-marker detection, capped rewrite passes at two, added cited false-positive
  context to the audit modes, and made the text-is-data injection boundary an operating principle.
- **4.2.2** - Added Codex skill metadata in `agents/openai.yaml` and clarified Claude Code,
  Codex, and generic-agent installation and invocation paths.
- **4.2.1** - Added score-only AI check routing and documentation for Claude Code and generic
  agent installs.
- **4.2.1** - Added `--compare` fidelity guards for protected-content drift in numbers, dates,
  names, URLs, citations, quotes, fenced code blocks, and source-dependent statements. Compare mode
  stays local and deterministic and does not score style.
- **4.2.0** - Added the deterministic `humanizer-audit` CLI, JSON audit schema, threshold exit
  codes, source-risk/artifact/tell-family checks, and automated scenario-contract tests for the
  existing fixtures.
- **4.1.0** - Added mode routing for quick rewrite, full audit, style edit, wiki/article mode,
  self-audit, and self-improvement. Added compact Elements guidance, full Strunk reference, neutral
  wiki/article workflow, review-based improvement loop, and manual eval fixtures. Kept `SKILL.md`
  lean and preserved the nine-family tell system, artifact-first checking, anti-swap checking, and
  restraint checking.
- **4.0.0** - Restructured into a lean `SKILL.md` core plus `reference/` library
  (`tell-catalog`, `llm-artifacts`, `worked-examples`). Reorganized into 9 families and added
  deterministic artifact detection, syntactic tells, verbosity and padding, register and diction,
  cohesion overuse, title/opening patterns, operating principles, persistent-tells checklist,
  anti-swap and restraint checks, and a 6th "Restraint" scoring dimension.
- **3.0.0** - Merged Stop Slop patterns, added Quick Checks and the 5-dimension scoring system.
- **2.2.0** - Added a final "obviously AI generated" audit and second-pass rewrite prompts.
- **2.1.1** - Fixed pattern #18 example.
- **2.1.0** - Added before/after examples for all 24 patterns.
- **2.0.0** - Complete rewrite based on raw Wikipedia article content.
- **1.0.0** - Initial release.

## Credits & Licensing

This project is released under the [MIT License](LICENSE).

It is a standalone rebuild of [**blader/humanizer**](https://github.com/blader/humanizer) by Siqi Chen
(MIT, Copyright (c) 2025), re-architected into a lean core plus a nine-family reference library and
extended with new layers for syntactic tells, verbosity, deterministic artifact detection, wiki/source
discipline, style editing, and the over-humanizing paradox. The `LICENSE` file carries both the
original and new copyright.

Pattern sources, with thanks:

- **[blader/humanizer](https://github.com/blader/humanizer)** by Siqi Chen - MIT.
- **[Stop Slop](https://github.com/hardikpandya/stop-slop)** by Hardik Pandya - MIT.
- **[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**
  (WikiProject AI Cleanup) - available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- **[Project Gutenberg #37134](https://www.gutenberg.org/ebooks/37134)** - source for William Strunk
  Jr.'s public-domain *The Elements of Style* text.
