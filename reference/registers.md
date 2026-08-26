# Register Strictness

The same pattern is a tell in one register and the correct form in another. This table sets how
hard each rule area is enforced per register. It implements operating principle 2 (don't
over-correct) instead of merely asserting it — adapted from avoid-ai-writing's tolerance matrix
(MIT), compressed to the registers this skill actually meets.

**Registers:**

- **wiki** — encyclopedic/source-bound articles (pairs with `wiki-mode.md`).
- **news** — news stories and press-style pieces.
- **essay** — blog posts, essays, long-form prose. The default when nothing else fits.
- **docs** — READMEs, documentation, guides.
- **chat** — Discord/forum/issue replies, quick messages.
- **commit** — commit messages, handoffs, changelogs, terse operational prose.

**Levels:** strict (flag and fix) · relaxed (flag only clusters or egregious cases) · skip
(the pattern is the correct form here; do not flag).

| Rule area | wiki | news | essay | docs | chat | commit |
|---|---|---|---|---|---|---|
| Artifact sweep (`llm-artifacts.md`) | strict | strict | strict | strict | strict | strict |
| Significance/promotional inflation (F1) | strict | strict | strict | relaxed | skip | skip |
| Vague attribution / gap-filling (F2) | strict | strict | strict | relaxed | skip | relaxed |
| Filler and hedging (F3) | strict | strict | strict | strict | relaxed | relaxed |
| AI-vocab clusters (F4) | strict | strict | strict | relaxed* | relaxed | relaxed |
| Wordiness (1B clarity) | strict | strict | strict | strict | skip | relaxed |
| Syntactic tells (F5) | strict | strict | strict | relaxed | skip | skip |
| Verbosity/padding (F6) | strict | strict | strict | strict | relaxed | strict |
| Rhetorical formulas (F7) | strict | strict | strict | strict | relaxed | skip |
| Formatting/structure (F8) | strict | strict | strict | relaxed | skip | skip |
| Em-dash crutches (§8.6) | strict** | strict | strict | relaxed | skip | skip |
| Fragments / agentless passives | strict | strict | strict | skip | skip | skip |
| Uniform paragraph rhythm (§8.12) | strict | strict | strict | relaxed | skip | skip |
| Chatbot residue (F9 prose) | strict | strict | strict | strict | strict | strict |
| Wall-of-text replies (§9.10) | skip | skip | skip | skip | strict | skip |
| Diff-anchored writing (§8.15) | strict | strict | strict | strict | skip | skip*** |

\* Technical docs legitimately use robust, ecosystem, leverage, facilitate as terms of art — judge
by density, not presence.
\** A target wiki's own style rules outrank this table; some house lints ban em dashes outright —
follow them.
\*** Changelogs, release notes, migration guides, and commit messages narrate change correctly;
that is the §8.15 carve-out, not an exemption from it.

## Auto-detection cues

When the user does not name a register, infer it and say so ("Auditing as a chat reply — say the
word if this is long-form"). The user's word always overrides.

| Signal | Register |
|---|---|
| wikitext markup, `<ref>`, `{{cite}}`, encyclopedic tone requested | wiki |
| headline/dateline shape, attribution-heavy reporting | news |
| README/heading/step structure, API or parameter docs | docs |
| short reply-length text, @-mentions, message thread context | chat |
| conventional-commit subject, Verify:/Scope: blocks, handoff shape | commit |
| none of the above | essay |

## How this composes

- The artifact sweep and chatbot-residue checks never relax: mechanical residue is wrong in every
  register.
- A "skip" is not a license to add the pattern during a rewrite — never-inject (see `SKILL.md`,
  Voice Without New Tells) still governs edits.
- Wiki register additionally loads `wiki-mode.md`; its source discipline outranks any relaxation
  here.
