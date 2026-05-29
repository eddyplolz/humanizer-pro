# Humanizer Pro

A Claude Code skill that removes signs of AI-generated writing from text, making it read as natural and
human — without over-correcting clean prose or swapping one machine pattern for another.

*A standalone rebuild of [blader/humanizer](https://github.com/blader/humanizer) (MIT). See [Credits & licensing](#credits--licensing).*

## Installation

### Recommended (clone directly into the Claude Code skills directory)

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

The skill is split across `SKILL.md` (the operating core) and a `reference/` directory; clone the whole
repo so the reference files come with it.

## Usage

In Claude Code, invoke the skill and paste your text:

```
/humanizer-pro

[paste your text here]
```

Or ask Claude directly: `Please humanize this text: [your text]`. The skill also runs as a
self-audit on Claude's own drafts before delivery.

## Overview

The skill synthesizes three sources:

- **[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**
  (WikiProject AI Cleanup) — prose tells and markup/placeholder leakage from thousands of real examples.
- **"Comprehensive Analysis of AI-Generated Writing Tells"** — the syntactic, verbosity, register, and
  persistence layers, plus the "trying-to-sound-human" paradox.
- **[Stop Slop](https://github.com/hardikpandya/stop-slop)** by Hardik Pandya — blog/thought-leadership
  tells and the scoring system.

> **Key insight (Wikipedia):** "LLMs use statistical algorithms to guess what should come next. The
> result tends toward the most statistically likely result that applies to the widest variety of cases."

What makes v4 different from a find-and-replace list: it edits **clusters**, not isolated words; it
**preserves** legitimate prose (a lone em dash, one "however," a formal register); it refuses to **swap**
one tell for another; and it guards against the **over-humanizing paradox** (fake-casual openers,
strategic profanity, performance markers) that naive "add personality" advice produces.

## File layout

| File | Role |
|------|------|
| `SKILL.md` | Operating core: operating principles, the 9-family compact index, checklists, scoring, and the multi-pass workflow. The runtime artifact Claude Code reads. |
| `reference/tell-catalog.md` | The full pattern library — every tell with watch-words and before/after, tagged by source (WP / PDF / Stop Slop). |
| `reference/llm-artifacts.md` | Deterministic detector for leaked tokens and placeholders, each with a grep-ready regex and a one-pass union sweep. |
| `reference/worked-examples.md` | Four full before → audit → after edits, including a restraint (don't-edit) case. |

## The nine families of tells

1. **Significance & promotional inflation** — "stands as a testament," "pivotal moment," brochure tone, copula avoidance ("serves as").
2. **Vague attribution & notability** — "Experts believe," outlet name-drops, "active social media presence."
3. **Superficial analysis & filler** — trailing "-ing" depth, "In order to," hedging stacks, formulaic "Challenges" sections.
4. **AI vocabulary & diction** — clustered AI words (crucial, vibrant, testament, robust…), academic register, business jargon, modifier stacking. Includes a dated era table because tells drift.
5. **Syntactic tells** — anticipatory "it," existential "there," passive hedging, cleft emphasis, front-loaded transitions.
6. **Verbosity & padding** — nominalization, redundant clarification, elaboration compulsion, false precision, both-sides-ism.
7. **Rhetorical formulas** — binary contrasts, negative parallelism, rule of three, false ranges, dramatic fragmentation, fortune-cookie endings.
8. **Structure & formatting** — colon/gerund titles, title-case headings, boldface overuse, emojis, curly quotes, em-dash overuse (a weak signal), markdown leaking into non-markdown targets.
9. **Chatbot residue & artifacts** — "Great question!", cutoff disclaimers, and the deterministic artifact tokens (`citeturn0search0`, `:contentReference[oaicite:N]`, `oai_citation`, `grok_card`, `utm_source=chatgpt.com`) and placeholders (`[Your Name]`, `2025-XX-XX`).

Full watch-words and examples for every family live in `reference/tell-catalog.md`.

## Full example

**Before (AI-sounding):**
> Great question! Here is an essay on this topic. I hope this helps!
>
> AI-assisted coding serves as an enduring testament to the transformative potential of large language
> models, marking a pivotal moment in the evolution of software development. In today's rapidly evolving
> technological landscape, these groundbreaking tools are reshaping how engineers ideate, iterate, and
> deliver, underscoring their vital role in modern workflows.
>
> While specific details are limited based on available information, it could potentially be argued that
> these tools might have some positive effect. In conclusion, the future looks bright. Let me know if
> you'd like me to expand on any section!

**After (humanized):**
> AI coding assistants can make you faster at the boring parts. Not everything. Definitely not
> architecture.
>
> They're great at boilerplate: config files, test scaffolding, repetitive refactors. They're also great
> at sounding right while being wrong. I've accepted suggestions that compiled, passed lint, and still
> missed the point because I stopped paying attention.
>
> The productivity metrics are slippery. GitHub can say Copilot users "accept 30% of suggestions," but
> acceptance isn't correctness, and correctness isn't value. If you don't have tests, you're guessing.

The full version (with score, the two-pass audit, and an anti-swap example) is in
`reference/worked-examples.md`, Example 2.

## References

- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) — primary prose/markup source.
- [WikiProject AI Cleanup](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_AI_Cleanup) — maintaining organization.
- [Stop Slop](https://github.com/hardikpandya/stop-slop) by Hardik Pandya — thought-leadership tells and scoring.

## Version History

- **4.0.0** — Restructured into a lean `SKILL.md` core + `reference/` library (tell-catalog, llm-artifacts, worked-examples). Reorganized into 9 families and added whole new layers: LLM artifact/placeholder detection (deterministic regex sweep), syntactic tells, verbosity & padding, register & diction, cohesion overuse, title/opening patterns. Added the operating principles (density over single instances, don't over-correct, don't swap templates, the trying-to-sound-human paradox, tells evolve, multi-pass), a persistent-tells second-pass checklist, the anti-swap and restraint checks, and a 6th "Restraint" scoring dimension.
- **3.0.0** — Merged Stop Slop patterns (binary contrasts, dramatic fragmentation, rhetorical setups, throat-clearing, business jargon, emphasis crutches, meta-commentary), added Quick Checks and the 5-dimension scoring system. 31 patterns.
- **2.2.0** — Added a final "obviously AI generated" audit + second-pass rewrite prompts.
- **2.1.1** — Fixed pattern #18 example (curly vs straight quotes).
- **2.1.0** — Added before/after examples for all 24 patterns.
- **2.0.0** — Complete rewrite based on raw Wikipedia article content.
- **1.0.0** — Initial release.

## Credits & licensing

This project is released under the [MIT License](LICENSE).

It is a standalone rebuild of [**blader/humanizer**](https://github.com/blader/humanizer) by Siqi Chen
(MIT, Copyright © 2025), re-architected into a lean core plus a nine-family reference library and extended
with new layers for syntactic tells, verbosity, deterministic artifact detection, and the over-humanizing
paradox. The `LICENSE` file carries both the original and the new copyright.

Pattern sources, with thanks:

- **[blader/humanizer](https://github.com/blader/humanizer)** by Siqi Chen — MIT. The base this repo grew from.
- **[Stop Slop](https://github.com/hardikpandya/stop-slop)** by Hardik Pandya — MIT. Thought-leadership tells and the scoring approach.
- **[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)** (WikiProject AI Cleanup) — available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Catalog entries here are original wording with synthetic examples; any passage reused directly from Wikipedia stays under CC BY-SA 4.0, and adaptations of it must be shared alike.
