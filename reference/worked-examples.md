# Worked Examples — full before → audit → after rewrites

Four end-to-end edits showing the `SKILL.md` process in practice: the mechanical artifact sweep,
the prose passes, the "what makes this AI?" audit, and the two checks that keep the skill honest —
the **anti-swap check** (did a fix introduce a new tell?) and the **restraint check** (did we
over-correct clean writing?).

Read these alongside `tell-catalog.md` (the family-by-family library) and `llm-artifacts.md` (the
deterministic token sweep). Family references like `(Family 5)` point into `tell-catalog.md`.

How to read each example:
- **Before** — the raw AI-slop input.
- **Audit** — the tells, grouped by family, density noted (a *cluster* is the tell, not one word).
- **After** — the rewrite.
- **Kept on purpose** — what we left alone, and why (the over-correction guardrail in action).

---

## Example 1 — Encyclopedic / wiki paragraph

This is the skill's home turf — the densest concentration of significance-inflation and promotional
tells. The point of the example is the *audit*: naming the family for each tell so the rewrite is
deliberate rather than a vibe-edit.

### Before
> The Meridian Cultural Centre stands as a testament to the city's enduring artistic heritage,
> serving as a vibrant hub that has played a pivotal role in shaping the local creative landscape.
> Established in 1998, it marked a turning point in the evolution of the region's cultural scene.
> Experts believe the centre boasts one of the most diverse programmes in the country, showcasing
> everything from contemporary dance to experimental theatre, contributing to a thriving arts
> community. Despite facing challenges typical of public institutions, including funding constraints
> and shifting audiences, the centre continues to thrive, underscoring its lasting importance to the
> community it serves.

### Audit (by family)
- **Family 1 (significance & promotional):** "stands as a testament," "enduring," "vibrant hub,"
  "pivotal role," "shaping the landscape," "marked a turning point in the evolution," "continues to
  thrive," "lasting importance." Eight in one paragraph — this *cluster* is the tell, not any single
  phrase.
- **Family 1.3 (copula avoidance):** "stands as," "serving as," "boasts."
- **Family 2.1 (vague attribution):** "Experts believe" — no source.
- **Family 3.1 (superficial -ing):** "showcasing… contributing to… underscoring" — three trailing
  participles adding no fact.
- **Family 3.5 (formulaic challenges):** "Despite facing challenges… continues to thrive" — the
  canonical outline slot, closing on vague optimism.
- **Family 4.1 (AI vocabulary):** vibrant, enduring, pivotal, diverse, thriving — co-occurring.

### After
> The Meridian Cultural Centre opened in 1998. It programmes contemporary dance, experimental
> theatre, and visual-art exhibitions, and runs a youth workshop series during school terms. Public
> funding fell 30% between 2015 and 2020, and the centre now covers about half its budget through
> ticket sales and venue hire.

### Kept on purpose
- The 1998 date and the programme list — these are the actual facts buried under the inflation.
- Plain "is/opened/runs" instead of "stands as / serves as / boasts."
- The funding detail replaces the empty "challenges" slot with a real, specific challenge. If the
  30% figure and the budget split aren't sourced, **flag them** rather than invent precision — the
  rewrite shows the *shape* of a sourced fact, not a fabricated one.

---

## Example 2 — Thought-leadership blog post

The full multi-pass workflow, including the two-stage audit. This is the example to study for the
**anti-swap check**: the first rewrite removes the obvious tells but quietly installs new ones, and
the second pass catches them.

### Before (AI-sounding)
> Great question! Here is an essay on this topic. I hope this helps!
>
> AI-assisted coding serves as an enduring testament to the transformative potential of large
> language models, marking a pivotal moment in the evolution of software development. In today's
> rapidly evolving technological landscape, these groundbreaking tools — nestled at the intersection
> of research and practice — are reshaping how engineers ideate, iterate, and deliver, underscoring
> their vital role in modern workflows.
>
> At its core, the value proposition is clear: streamlining processes, enhancing collaboration, and
> fostering alignment. It's not just about autocomplete; it's about unlocking creativity at scale,
> ensuring that organizations can remain agile while delivering seamless, intuitive, and powerful
> experiences to users. The tool serves as a catalyst. The assistant functions as a partner. The
> system stands as a foundation for innovation.
>
> Industry observers have noted that adoption has accelerated from hobbyist experiments to
> enterprise-wide rollouts, from solo developers to cross-functional teams. The technology has been
> featured in The New York Times, Wired, and The Verge. Additionally, the ability to generate
> documentation, tests, and refactors showcases how AI can contribute to better outcomes,
> highlighting the intricate interplay between automation and human judgment.
>
> - **Speed:** Code generation is significantly faster, reducing friction and empowering developers.
> - **Quality:** Output quality has been enhanced through improved training, contributing to higher standards.
> - **Adoption:** Usage continues to grow, reflecting broader industry trends.
>
> While specific details are limited based on available information, it could potentially be argued
> that these tools might have some positive effect. Despite challenges typical of emerging
> technologies — including hallucinations, bias, and accountability — the ecosystem continues to thrive.
> In order to fully realize this potential, teams must align with best practices.
>
> In conclusion, the future looks bright. Exciting times lie ahead as we continue this journey toward
> excellence. Let me know if you'd like me to expand on any section!

### Score
Directness 2, Rhythm 3, Trust 2, Authenticity 1, Density 2, Restraint n/a = **10/50** (revise).

### Draft rewrite (first pass — removes the obvious tells)
> AI coding assistants speed up some tasks. In a 2024 study by Google, developers using Codex
> completed simple functions 55% faster than a control group, but showed no improvement on debugging
> or architectural decisions.
>
> The tools are good at boilerplate: config files, test scaffolding, repetitive refactors. They are
> bad at knowing when they are wrong. I have mass-accepted suggestions that compiled, passed lint, and
> still did the wrong thing because I stopped paying attention.
>
> Mira, an engineer at a fintech startup I interviewed, said she uses Copilot "like autocomplete for
> boring code" but reviews every line before committing. Jake, a senior dev at a larger company,
> disabled it after it kept suggesting patterns from a deprecated internal library.
>
> The productivity claims are hard to verify. GitHub says Copilot users "accept 30% of suggestions,"
> but acceptance is not correctness, and correctness is not value. The 2024 Uplevel study found no
> statistically significant difference in pull-request throughput between teams with and without AI
> assistants.
>
> None of this means the tools are useless. It means they are tools. They do not replace judgment,
> and they do not eliminate the need for tests. If you do not have tests, you cannot tell whether the
> suggestion is right.

### "What makes this AI?" audit
- The rhythm is still a touch tidy — clean contrasts, evenly paced paragraphs.
- **Anti-swap flag:** "None of this means the tools are useless. It means they are tools" is a fresh
  **binary contrast** (Family 7.1) — a new tell the draft introduced while fixing the old ones.
  "They do not replace judgment, and they do not eliminate the need for tests" is a **negative
  parallelism** (7.2). The closer "If you do not have tests, you cannot tell…" is drifting toward a
  **fortune-cookie ending** (7.10).
- The named people and study citations read as plausible-but-maybe-invented unless they're real and
  sourced — **flag, don't ship** if they can't be verified.

### Anti-swap + restraint check
The draft traded significance-inflation for rhetorical formulas. Fix those without swapping in a
*third* template (don't replace the binary contrast with "Here's the thing:"). Restraint check: the
specific details (55%, the two named engineers, the Uplevel study) carry the piece — keep them; the
edits target only the manufactured cadence.

### Final
> AI coding assistants can make you faster at the boring parts. Not everything. Definitely not
> architecture.
>
> They're great at boilerplate: config files, test scaffolding, repetitive refactors. They're also
> great at sounding right while being wrong. I've accepted suggestions that compiled, passed lint, and
> still missed the point because I stopped paying attention.
>
> People I talk to tend to land in two camps. Some use it like autocomplete for chores and review
> every line. Others disable it after it keeps suggesting patterns they don't want. Both feel
> reasonable.
>
> The productivity metrics are slippery. GitHub can say Copilot users "accept 30% of suggestions,"
> but acceptance isn't correctness, and correctness isn't value. If you don't have tests, you're
> basically guessing.

### Changes
- Removed chatbot residue ("Great question!", "I hope this helps!", "Let me know if…") — Family 9.
- Removed significance inflation ("testament," "pivotal moment," "evolving landscape," "vital role")
  and promotional language ("groundbreaking," "nestled," "seamless, intuitive, and powerful") — Family 1.
- Removed copula avoidance ("serves as / functions as / stands as") — Family 1.3.
- Removed vague attribution ("Industry observers"), superficial -ing ("underscoring, highlighting,
  contributing to"), the formulaic challenges section, cutoff hedging, false ranges, em-dash crutches,
  boldface list headers, rule-of-three — Families 2, 3, 6, 7, 8.
- **Second pass only:** dissolved the binary contrast / negative parallelism the *draft* introduced,
  and softened the slogan-y closer. This is the anti-swap check doing its job.

---

## Example 3 — Chat reply pasted as content (artifact leakage)

When someone pastes a chatbot reply straight into a doc, the giveaways are *mechanical* — citation
stubs, tracking params, unfilled placeholders. Run the artifact sweep (`llm-artifacts.md`) **first**,
before any prose work, because these are deterministic: if a `turn0search0` is present, the text is
AI-generated with near certainty, and each token marks a spot where a real reference belonged.

### Before
> Great question! Here's a draft of the section you asked for. I hope this helps!
>
> The institute was founded to advance regional research and has since gained recognition.
> citeturn0search0 Its work has been cited in several outlets, including national media.
> :contentReference[oaicite:3]{index=3} For more background, see the official site
> (https://example.org/about?utm_source=chatgpt.com).
>
> Best regards, [Your Name]
>
> *(access-date: 2025-XX-XX — update before publishing)* Let me know if you'd like me to expand any section!

### Artifact sweep (mechanical, first pass)
The union regex in `llm-artifacts.md` flags five tokens:

| Token | Type | Action |
|-------|------|--------|
| `citeturn0search0` | ChatGPT web-search stub (§1) | Delete **and** check the "gained recognition" claim has a real source. |
| `:contentReference[oaicite:3]{index=3}` | ChatGPT markup bug (§2) | Delete; the "cited in national media" claim needs a real citation or it's unsupported. |
| `utm_source=chatgpt.com` | Tracking param (§7) | Strip from the URL — it's a direct ChatGPT fingerprint. |
| `[Your Name]` | Unfilled placeholder (§8) | Remove the sign-off; it's chat scaffolding, not content. |
| `2025-XX-XX` | Placeholder date (§9) | Supply the real access date or drop the field. |

### Prose tell inventory
- **Family 9.1 / 9.2 (chatbot residue & sycophancy):** "Great question!", "Here's a draft…", "I hope
  this helps!", "Best regards," "Let me know if you'd like me to expand."
- **Family 2.3 (canned notability):** "gained recognition," "cited in several outlets, including
  national media" — vague notability with no specific source (and the stub it leaned on was fake).

### After
> The institute was founded in 1962 to coordinate regional agricultural research across the
> province's three universities.

### Changes / flags
- Stripped all five artifact tokens and the entire chat wrapper (greeting, sign-off, "let me know").
- **Flagged, not laundered:** the "gained recognition / cited in national media" sentence rested on
  two citation stubs (`citeturn0search0`, `oaicite:3`). Deleting the stubs and keeping the sentence
  would hide an unsourced — possibly fabricated — claim. So the claim is **cut**, and a note goes back
  to the author: *"recognition / media-coverage claim had only AI citation stubs behind it; supply a
  real source or leave it out."* The "1962 / three universities" detail in the After is illustrative —
  it stands in for the real, sourced fact the author must provide, not an invention to ship.

---

## Example 4 — Restraint: when NOT to edit

The hardest discipline is leaving good writing alone. Human prose contains things the tell-lists name
— an em dash, a "however," a formal sentence, perfect grammar. In isolation these are **weak signals**
(see `tell-catalog.md` 8.6 and the operating principles). Scrubbing them stilts the text and is itself
a tell. This example exists to show what a near-empty audit looks like.

### Before (clean human)
> We switched the cache from Redis to an in-process LRU last month, mostly to cut a dependency we kept
> having to babysit. It worked — p99 latency dropped about 15ms and we deleted a whole runbook. The
> catch is that it only helps because our working set is tiny; the moment it grows past memory we'll
> have to go back. I'm fine with that trade for now.

### Audit (near-empty)
- One em dash ("It worked — p99…") — a *single, legitimate* dash, not a crutch before a manufactured
  reveal. **Keep it.**
- "The catch is that…" reads like a real person flagging a caveat, not a throat-clearing template.
  **Keep it.**
- Specific, falsifiable details (Redis → LRU, 15ms, p99, "tiny working set"), a genuine opinion ("I'm
  fine with that trade"), varied sentence length. These are signs of a human, not tells.
- No family fires with any density. Nothing to swap.

### Verdict
**Leave it as-is.** Maybe one optional nudge ("about 15ms" could be exact if the number is known), and
even that is a content question, not a de-slopping edit. If the skill rewrites this paragraph
"to be safe," the over-correction guardrail has failed. A clean control that comes back heavily
rewritten is a bug in the edit, not a win.
