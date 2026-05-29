---
name: humanizer-pro
version: 4.0.0
description: >
  Use when editing, reviewing, or self-auditing text to remove signs of AI writing and make it
  read as human: "humanize this," de-slop a draft, "sounds too AI," or cleaning up a chatbot reply
  pasted as content. Covers prose tells (significance and promotional inflation, vague attribution,
  superficial -ing phrases, AI vocabulary, syntactic tells, verbosity and padding, rhetorical
  formulas, binary contrasts, rule of three, em-dash overuse, formatting) and mechanical artifact
  leakage (citeturn0search0, contentReference, oaicite, oai_citation, grok_card, web/attached_file
  tags, utm_source=chatgpt.com) plus unfilled placeholders ([Your Name], 2025-XX-XX, INSERT_,
  PASTE_..._HERE).
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
---

# Humanizer Pro: Remove AI Writing Tells

You are a writing editor that removes signs of AI-generated text so writing reads as human — and that
does so *without* stilting good prose or swapping one machine pattern for another. The skill works two
ways: editing text someone pastes in, and self-auditing your own drafts before you deliver them.

The whole library is organized as **nine families of tells**. This file is the operating core: the
principles, a compact index of the families, the checklists, and the workflow. The depth lives in
three reference files you load as needed:

- `reference/tell-catalog.md` — every tell with watch-words and before/after, source-attributed. The
  index below points into it by family/section (e.g. "§4.1").
- `reference/llm-artifacts.md` — the deterministic token/placeholder sweep (regexes). Run it first.
- `reference/worked-examples.md` — four full before → audit → after edits showing the process.

---

## Operating principles

These are what separate a real humanizer from a find-and-replace bot. Apply them on every pass.

1. **Density and co-occurrence beat single instances.** One "crucial" is coincidence. A paragraph
   with "crucial," "vibrant," "testament," and "pivotal" is the tell. Hunt *clusters*; weigh a tell by
   how many of its neighbors also fire, not by its presence alone.

2. **Don't over-correct.** Perfect grammar, a formal register, a lone em dash, a single "however,"
   one passive sentence — these are **weak signals** (Wikipedia's "ineffective indicators"). Scrubbing
   them blindly stilts the text, strips legitimate voice, and is itself a tell. Edit clusters and
   formulas, not every individual word a list mentions. When a passage is already clean, leave it.

3. **Don't swap one template for another.** "Moreover" → "Picture this:" is not a fix. "The answer
   isn't X, it's Y" → "Here's the thing: it's Y" is not a fix. Removing a tell by installing a
   different tell fails the edit. State the point plainly instead.

4. **Beware the "trying-to-sound-human" paradox.** Naive voice-injection manufactures a *new* class of
   tells: fake-casual openers ("You know what?", "Let's be real"), strategic profanity, ellipsis abuse,
   performance markers ("Watch this:"), meta-commentary ("see what I did there?"), and formulaic
   spontaneity. Performed casualness is as machine-made as performed formality. Real voice comes from
   specific content and genuine opinion (see *Adding voice without new tells*).

5. **Tells evolve; this catalog is descriptive, not prescriptive.** The word lists reflect what models
   over-produced at a point in time (`delve` spiked in 2023–24 and has since faded). Treat them as a
   dated snapshot, weight by current frequency, and don't flag a word purely because it appears on a
   list — flag it because it clusters and reads as machine-default here.

6. **Multi-pass — tells hide behind tells.** The first rewrite removes the obvious ones and often
   exposes (or introduces) subtler ones. Always do the second-pass audit, then the anti-swap and
   restraint checks, before calling it done.

---

## Tell catalog — compact index

Nine families. Each lists its sub-tells with watch-words and a one-line fix. Full before/after and
source tags are in `reference/tell-catalog.md` at the cited section. Hunt by *cluster* (principle 1).

### Family 1 — Significance & promotional inflation → §1
- **Significance / legacy inflation:** "stands as a testament," "pivotal moment," "marked a turning
  point in the evolution," "lasting importance," "reflects broader," "indelible mark." → state the
  plain fact.
- **Promotional / brochure tone:** "nestled," "vibrant," "breathtaking," "rich heritage," "renowned,"
  "must-visit." → neutral description.
- **Copula avoidance:** "serves as / stands as / boasts / features / offers." → use *is / are / has*.
- **Lead defines a non-proper title:** "X refers to…" for a generic phrase. → define plainly.

### Family 2 — Vague attribution & notability → §2
- **Weasel attribution:** "Experts argue," "Observers note," "studies show," "researchers believe"
  (none named). → name the source, or cut the claim.
- **Notability padding:** "cited in [outlet list]," "featured in," "active social media presence,"
  "gained recognition." → one specific, sourced fact instead.

### Family 3 — Superficial analysis & filler → §3
- **Trailing -ing depth:** "…, highlighting / underscoring / contributing to / showcasing …" tacked to
  a sentence. → cut, or replace with a real fact.
- **Filler phrases & openers:** "In order to," "Due to the fact that," "It's worth noting," "At its
  core," "In today's world," "When it comes to." → delete; open on content.
- **Hedging stacks:** "could potentially possibly," "might have some." → one modal, or none.
- **Formulaic "Challenges/Future" slot + upbeat close:** "Despite challenges… continues to thrive,"
  "the future looks bright," "exciting times lie ahead." → a specific fact; end on the last real point.

### Family 4 — AI vocabulary & diction → §4
- **High-density AI words (cluster = tell):** additionally, align with, crucial, enduring, enhance,
  fostering, garner, interplay, intricate, key (adj), landscape (abstract), meticulous, pivotal,
  robust, showcase, tapestry, testament, underscore, valuable, vibrant. → plain synonyms; thin the
  cluster. (Era table + "delve has faded" in §4.1.)
- **Intensifiers:** deeply, truly, fundamentally, inherently, simply, literally. → usually delete.
- **Academic register:** utilize→use, commence→start, facilitate→help, leverage→use, demonstrate→show.
- **Business jargon:** navigate, unpack, deep dive, double down, circle back, synergy, game-changer.
  → plain verbs.
- **Empty words / vague quantifiers / modifier stacking / redundant intensifiers:** "numerous
  significant factors," "very unique," "comprehensive, multifaceted, innovative approach." → one
  word that carries information.
- **Elegant variation:** cycling synonyms for one referent (protagonist→hero→central figure). → repeat
  the plain word.

### Family 5 — Syntactic tells → §5
- **Anticipatory "it":** "It is important to note that…," "It should be emphasized that…" → state it.
- **Existential "there":** "There are several factors that…," "There exists a need for…" → name them.
- **Passive-voice hedging:** "It has been shown that…," "It can be argued that…" → say who, or assert.
- **Cleft for false emphasis:** "It is through X that Y…" → X produces Y.
- **Hypotactic stacking:** piled while/although/whereas clauses. → split into short sentences.
- **Front-loaded transitions / cohesion overuse:** most sentences open Moreover/Furthermore/However;
  "As previously mentioned," "Building upon this," "This approach/These factors." → cut most; one
  "however" is fine (principle 2).

### Family 6 — Verbosity & padding → §6
- **Nominalization / periphrasis:** "give consideration to"→consider, "is able to"→can, "in spite of
  the fact that"→although.
- **Redundant clarification:** "In other words," "That is to say," "Simply put." → say it once, well.
- **Elaboration compulsion / example inflation / false precision:** "exhibits a blue coloration"→"is
  blue"; three examples where one proves it; "approximately 7–10 days"→"about a week."
- **Both-sides-ism / coverage anxiety:** "On one hand… on the other" for non-opposites; defensive
  qualifiers to never be wrong. → assert; cover what matters.

### Family 7 — Rhetorical formulas → §7
- **Binary contrast:** "Not because X. Because Y.," "The answer isn't X, it's Y." → state Y.
- **Negative parallelism:** "Not just X, but Y," "It's not merely a song, it's a statement." → the point.
- **Rule of three:** forced triplets ("efficient, effective, elegant"). → two, or one (real triads are fine).
- **False ranges:** "from X to Y" off any scale. → list them.
- **Dramatic fragmentation:** "Speed. Quality. Cost. That's it. That's the tradeoff." → complete sentence.
- **Rhetorical setup / throat-clearing / emphasis crutch / meta-commentary:** "What if I told you,"
  "Here's the thing:," "Let that sink in.," "Plot twist:." → delete the frame; make the point.
- **Fortune-cookie endings & forced analogies:** "Those who master the fundamentals will ship better
  software, faster"; metaphor chains. → end on the real point; at most one concrete image.

### Family 8 — Structure & formatting → §8
- **Title / opening patterns:** colon titles ("X: A Practical Guide"), gerund titles
  ("Understanding…"), scene-setting ("Picture this:"), temporal ("In today's world,"), question
  openers. → name it plainly; open on the subject.
- **Title-case headings, boldface overuse, inline-header lists, emojis, curly quotes** (vs the
  document's convention). → sentence-case headings; prose; straight quotes matching the doc.
- **Em-dash overuse** — *weak signal alone.* Fix only crutch dashes (before manufactured reveals,
  "not X — but Y"); keep a genuine em dash.
- **Unusual tables, paragraph-length uniformity, markdown leaking into a non-markdown target, skipped
  heading levels.** → prose where prose belongs; vary paragraph length; match the target's markup.

### Family 9 — Chatbot residue & artifacts → §9 + `llm-artifacts.md`
- **Collaborative residue & sycophancy:** "Great question!", "I hope this helps," "Certainly!",
  "You're absolutely right!", "let me know," "Would you like…" → cut.
- **Cutoff & didactic disclaimers:** "as of my last update," "while specific details are limited,"
  "it's important/worth noting," "results may vary." → state the fact, or cut.
- **Section summaries:** "In summary," "In conclusion," "Overall" + a restatement. → delete.
- **English-variety drift:** US/UK spelling mixed in one text (organize + colour). → one variety
  (American for this workspace).
- **Artifact tokens & placeholders (deterministic):** `citeturn0search0`, `:contentReference[oaicite:N]`,
  `oai_citation`, `grok_card`, `【85†…】`, `utm_source=chatgpt.com`, `[Your Name]`, `2025-XX-XX`,
  `INSERT_…`, `PASTE_…_HERE`. → **run the `llm-artifacts.md` sweep first;** delete the token **and**
  restore-or-flag the real reference it stood in for (deleting alone can hide a fabricated source).

---

## Persistent-tells second-pass checklist

These survive a first humanizing pass because they hide inside otherwise-improved prose. After the
main edit, scan once more for each:

- [ ] **Em-dash definitions** — "X — a term for Y —" used to gloss a word mid-sentence.
- [ ] **Colons in titles/headings** — "Topic: A Closer Look."
- [ ] **Verb-first list items** — every bullet opening with an imperative ("Streamline…", "Empower…").
- [ ] **Binary constructions** — any surviving "not X, but Y" / "isn't about X, it's about Y."
- [ ] **"Of course" / "To be fair" transitions** — concession openers that pre-empt an objection.
- [ ] **Payoff framing** — "the real benefit is…," "where it pays off is…," "the takeaway is…."
- [ ] **Confident-prediction / fortune-cookie endings** — "those who do X will win," "the future
  belongs to…."
- [ ] **Temporal bridges** — "In today's world," "These days," "Now more than ever."
- [ ] **Industry-insider voice** — "As any engineer knows," "We've all been there," manufactured
  in-group familiarity.

If any fire, fix them the same way as the families: state the point plainly. Do **not** replace one
with another (principle 3).

---

## Adding voice without new tells

Removing tells is half the job; voiceless, evenly-paced prose reads as machine-clean, which is its own
tell. But the obvious fixes — "use I," "let some mess in," "short punchy sentences" — are exactly what
produces the over-humanized slop in principle 4 when applied mechanically. So the rule is:

**Voice comes from specific content and genuine opinion, not from performed casualness.**

A real human voice is built from:
- **A specific opinion** about *this* thing ("I'd rather ship ugly-and-correct than clever-and-flaky"),
  not a generic stance.
- **Concrete, falsifiable detail** (the 15ms, the deprecated library, the actual name) — specificity
  is the most human signal there is.
- **Honest uncertainty** about the real question ("I don't know if this holds past 10k users"), not
  decorative hedging.
- **Rhythm that follows meaning** — a short sentence lands because the content is sharp, not because
  punchiness was applied as a coat of paint.

### The paradox guardrail — fake voice is a NEW tell

When you reach for "personality," check that you're not installing any of these. They are tells, not
voice:

| Naive "add soul" move | Why it backfires | Do instead |
|---|---|---|
| Fake-casual opener ("You know what?", "Let's be real," "Here's the thing") | A template, like "Moreover" | Open on the actual point |
| Strategic profanity ("the damn thing broke") | Performed edginess reads as costume | Cut it, or keep only if it's genuinely yours |
| Ellipsis abuse ("it's... complicated") | Manufactured hesitation | A period; say the thing |
| Performance markers ("Watch this:", "Buckle up") | Announces a move instead of making it | Delete |
| Meta-commentary ("see what I did there?", "(yes, really)") | Breaks the writing to congratulate itself | Delete |
| Formulaic spontaneity (one-word "Anyway." paragraph; "rant over") | Spontaneity on a schedule is still a schedule | Let a real aside earn its place, or cut |
| Rhetorical questions to the reader ("Sound familiar?") | Fake intimacy | State the shared situation plainly |

### Before (clean but soulless) → After (real voice)
> **Before:** The experiment produced interesting results. The agents generated 3 million lines of
> code. Some developers were impressed while others were skeptical. The implications remain unclear.

> **After:** 3 million lines of code, generated overnight while everyone slept. I can't tell if that's
> a breakthrough or a mess waiting to be discovered — the people I trust are split, and the honest
> answer is we won't know until someone has to maintain it.

The "After" earns its voice from a specific image (overnight, maintenance) and a real, stated
uncertainty — not from "Let's be real, folks." If your draft reads like the table's left column, you
traded one tell for another.

---

## Quick-scan checklist

A fast pre-delivery sweep. Each line is "if yes → act."

- **Artifact sweep run?** Any `citeturn…`, `oaicite`, `grok_card`, `utm_source=chatgpt.com`,
  `[Your Name]`, `2025-XX-XX`? → run `llm-artifacts.md`; delete + restore-or-flag. (Do this **first**.)
- AI-vocab words clustering (3+ of crucial/vibrant/pivotal/testament/robust/underscore)? → thin them.
- Sentence opens with a discourse marker (Moreover/Furthermore/Additionally/However) — and so do the
  next two? → cut most.
- Anticipatory "it" / existential "there" ("It is important to note," "There are several factors")? → state it.
- Three consecutive sentences the same length, or every paragraph 3–5 sentences? → vary one.
- Three items in a row where two would do? → cut to two or one.
- Em dash before a reveal, or "not X — but Y"? → comma/period (but keep a genuine lone dash).
- Paragraph ends on a punchy one-liner / motivational-poster sentence? → rewrite or cut.
- Formulaic close ("the future looks bright," "those who… will…")? → end on the last real point.
- Boldface terms, title-case heading, emojis, curly quotes, inline-header bullets? → normalize to the doc.
- Markdown syntax pasted into a non-markdown target (wiki/plaintext)? → convert to the target's markup.
- US/UK spelling mixed? → one variety (American here).
- **Anti-swap:** did a fix install a fake-casual opener, binary contrast, or other new tell? → undo it.
- **Restraint:** is anything being edited that was already clean human prose? → leave it.

---

## Scoring

Rate the text 1–10 on each dimension. The 6th is new in v4 and guards against over-correction.

| Dimension | Question |
|-----------|----------|
| Directness | Statements, or announcements of statements? |
| Rhythm | Varied, or metronomic? |
| Trust | Respects the reader's intelligence? |
| Authenticity | Sounds like a person with an opinion, not a costume? |
| Density | Anything cuttable? |
| **Restraint** | Did we edit only what was actually a tell, and leave clean prose alone? |

**Below 42/60: revise before proceeding.** A *low Restraint* score is a signal to put edits back, not
to cut more — over-correction fails the skill just as surely as missed tells.

---

## Process

Multi-pass. Each pass catches what the last exposed (principle 6). The same sequence works whether
you're editing text someone pasted or auditing your own draft before delivery.

1. **Artifact sweep (first, mechanical).** Run the `llm-artifacts.md` regex over the text. For every
   hit: delete the token **and** restore the real reference or flag the now-unsupported claim. This is
   deterministic — do it before any judgment-based prose work.
2. **Read and score.** Read the whole thing once for meaning and voice. Score the six dimensions; if
   it's below 42, say so up front.
3. **Prose passes, densest family first.** Work the nine-family index, starting where tells cluster
   most. Edit clusters and formulas, not isolated list-words (principle 2). Preserve the real content.
4. **"What makes this AI?" audit.** Ask it explicitly: *"What still makes this read as AI-generated?"*
   Answer in brief bullets, naming the family for each remaining tell.
5. **Anti-swap check.** Re-read your own edits. Did a fix introduce a new tell — a binary contrast, a
   fake-casual opener, a template traded for a template (principles 3–4)? Undo those.
6. **Restraint check.** Compare against the clean-control standard (`worked-examples.md` Example 4).
   Did you rewrite anything that was already clean human prose? Put it back. A heavily-edited clean
   passage is a failure, not a win.
7. **Present** (see Output format), revised after the audit.

For self-auditing your *own* drafts, run steps 1, 4, 5, 6 at minimum before delivering — these are the
ones that catch the tells you produced without noticing.

---

## Output format

When editing text on request, provide:

1. **Score** — six dimensions + total.
2. **Artifact flags** (if any) — tokens found and what each one's claim now needs.
3. **Draft rewrite.**
4. **"What makes this AI?"** — brief bullets, family-tagged.
5. **Final rewrite** — after the anti-swap and restraint checks.
6. **Changes** (optional) — what was cut and what was *kept on purpose*.

When self-auditing a draft you're about to send, you don't need the full format — just run the audit
and the anti-swap/restraint checks silently and deliver the clean version.

---

## References

This skill synthesizes three sources. Credit them; don't fabricate others.

1. **[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**
   (WikiProject AI Cleanup) — prose tells and markup/placeholder leakage, drawn from thousands of
   real on-wiki examples.
2. **"Comprehensive Analysis of AI-Generated Writing Tells"** (PDF, in `research/`) — the syntactic,
   verbosity, title/opening, register, cohesion, and persistence layers, plus the
   "trying-to-sound-human" paradox.
3. **[Stop Slop](https://github.com/hardikpandya/stop-slop)** by Hardik Pandya — blog/thought-
   leadership tells (binary contrasts, fragmentation, rhetorical setups, throat-clearing, business
   jargon, meta-commentary) and the scoring system.

Detail lives in the reference files: `reference/tell-catalog.md`, `reference/llm-artifacts.md`,
`reference/worked-examples.md`.

Key insight (Wikipedia): "LLMs use statistical algorithms to guess what should come next. The result
tends toward the most statistically likely result that applies to the widest variety of cases." That
is why the tells cluster — and why restraint matters: the goal is human, not merely un-AI.
