# Humanizer Pro

A Claude Code skill that removes signs of AI-generated writing from text, making it read as natural
and human without over-correcting clean prose, inventing sources, or swapping one machine pattern for
another.

*A standalone rebuild of [blader/humanizer](https://github.com/blader/humanizer) (MIT). See
[Credits & licensing](#credits--licensing).*

## Installation

### Recommended

Clone the whole repository into the Claude Code skills directory:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

The skill is split across `SKILL.md`, `reference/`, and `eval/`; clone the whole repo so the
progressively loaded references and fixtures come with it.

## Usage

Invoke the skill and paste text:

```text
/humanizer-pro

[paste your text here]
```

Or ask directly: `Please humanize this text: [your text]`.

Simple requests return a concise rewrite. Ask for a "full audit" to get scores, artifact flags,
family-tagged rationale, and the final rewrite after anti-swap and restraint checks.

## Modes

- **Quick rewrite** - simple "humanize this" or "make this less AI" requests. Returns the cleaned text
  plus serious source-risk notes.
- **Deep edit / full audit** - scores the text, reports artifact flags, names the tell families, and
  shows the final rewrite.
- **Style edit** - uses the compact Elements of Style checklist in `reference/style-principles.md`.
  The full public-domain Strunk text is in `reference/elements-of-style-1918.md` and is loaded only on
  explicit request or deep style work.
- **Wiki/article mode** - uses `reference/wiki-mode.md` for Wikipedia, MicrasWiki, encyclopedic
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
| `reference/tell-catalog.md` | Full pattern library with watch-words and before/after examples. |
| `reference/llm-artifacts.md` | Deterministic detector for leaked tokens, placeholders, and AI citation residue. |
| `reference/worked-examples.md` | Four full before/audit/after examples, including a restraint case. |
| `reference/style-principles.md` | Compact Elements of Style checklist for everyday style edits. |
| `reference/elements-of-style-1918.md` | Full public-domain Project Gutenberg text of Strunk's *The Elements of Style*. |
| `reference/wiki-mode.md` | Neutral, source-bound article workflow for wiki and encyclopedic prose. |
| `reference/improvement-loop.md` | Review gate for promoting recurring skill failures into durable rules. |
| `eval/cases.md` | Manual validation matrix. |
| `eval/fixtures/*.md` | Regression fixtures for clean prose, AI slop, wiki promotion, over-humanizing, artifacts, and style edits. |

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

- General AI-slop becomes plainer and more specific.
- Clean human prose remains mostly unchanged.
- Over-humanized prose loses fake-casual performance without becoming stiff.
- Wiki promotional prose becomes neutral and source-bound.
- Artifact leakage is flagged with source-risk notes.
- Elements-style edits improve clarity without flattening legitimate voice.

## Version History

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
