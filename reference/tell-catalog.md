# Tell Catalog — full reference with before/after

The complete pattern library behind `SKILL.md`. Nine families. Each sub-tell lists its **watch-words**,
the **problem**, a **before → after**, and **source** (WP = Wikipedia "Signs of AI writing", PDF =
"Comprehensive Analysis of AI-Generated Writing Tells", SS = Stop Slop).

**Read this with the operating principles in mind** (see `SKILL.md`): hunt *clusters*, not single
words; don't over-correct legitimate prose; don't swap one template for another. For artifact tokens
and placeholder stubs, see `reference/llm-artifacts.md`.

---

## Family 1 — Significance & promotional inflation

### 1.1 Significance / legacy / broader-trends inflation (WP)
**Watch:** stands/serves as, is a testament/reminder, a vital/crucial/pivotal/key role/moment,
underscores its importance, reflects broader, symbolizing its enduring, marking/shaping the, represents
a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted.
**Problem:** Puffs up importance by tying arbitrary details to a "broader" significance.
> **Before:** Established in 1989, marking a pivotal moment in the evolution of regional statistics.
> **After:** Established in 1989 to collect and publish regional statistics.

### 1.2 Promotional / advertisement-like language (WP)
**Watch:** nestled, in the heart of, breathtaking, vibrant, rich (figurative), boasts a, renowned,
must-visit, stunning, diverse array, exemplifies, commitment to, natural beauty, groundbreaking.
**Problem:** LLMs drift to travel-brochure tone even when asked for neutral prose.
> **Before:** Nestled in the breathtaking region of Gonder, Alamata stands as a vibrant town with rich heritage.
> **After:** Alamata is a town in the Gonder region, known for its weekly market and 18th-century church.

### 1.3 Copula avoidance (WP)
**Watch:** serves as / stands as / marks / represents [a]; boasts / features / offers / maintains [a]; refers to.
**Problem:** Elaborate constructions substituted for a plain "is/are/has."
> **Before:** Gallery 825 serves as the exhibition space and boasts over 3,000 square feet.
> **After:** Gallery 825 is the exhibition space and has 3,000 square feet.

### 1.4 Lead defines the title as a proper noun (WP)
**Watch:** "X refers to…", "X is the chronological list of…", "The 'List of…' is a curated compilation of…"
**Problem:** Non-proper titles (lists, generic phrases) get introduced as standalone entities.
> **Before:** "Catchment area (health)" refers to the geographic area from which a facility draws patients.
> **After:** A catchment area is the geographic area from which a health facility draws its patients.

---

## Family 2 — Vague attribution & notability

### 2.1 Vague attribution / weasel words (WP)
**Watch:** Experts argue, Observers have cited, Industry reports, Some critics argue, researchers and
conservationists, "such as" before an exhaustive list.
**Problem:** Opinions pinned to an unnamed authority.
> **Before:** Experts believe the river plays a crucial role in the regional ecosystem.
> **After:** The river supports several endemic fish species (2019 survey, Chinese Academy of Sciences).

### 2.2 Overstating source quantity (WP)
**Watch:** "several sources", "multiple reviewers", "scholars agree" — when one (or none) is cited.
**Problem:** One source presented as a consensus; example lists implied non-exhaustive.
> **Before:** Toy-industry publications such as The Toy Insider and Mojo Nation have presented it as…
> **After:** The Toy Insider described it as a STEM platform; Mojo Nation reported the Spin Master deal.

### 2.3 Canned notability / media-coverage emphasis (WP)
**Watch:** independent coverage, featured in, profiled in, cited in [outlet list], local/national media
outlets, active/strong social media presence.
**Problem:** Hammering notability by listing outlets instead of saying something.
> **Before:** Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence.
> **After:** In a 2024 New York Times interview, she argued AI regulation should target outcomes, not methods.

### 2.4 Speculative gap-filling (avoid-ai-writing)
**Watch:** is believed to have, likely began/studied/served, appears to have been/worked,
maintains a relatively low public profile.
**Problem:** When the model lacks a fact it fills the gap with hedged speculation dressed as
background. Worse than a cutoff disclaimer, which at least *admits* the gap — this hides it, so
the reader cannot tell known from invented. Directly dangerous in wiki/source-bound work.
> **Before:** He is believed to have studied law and likely began his career in the ministry.
> **After:** (source it, or cut it — a guess formatted as biography is a fabrication.)

### 2.5 Vague third-party validation (avoid-ai-writing)
**Watch:** independent testing confirms, third-party benchmarks show, analysts agree, studies
consistently show — an **unnamed** authority plus a generic superlative.
**Problem:** The inverse of notability name-dropping: the authority is faceless and the claim
unfalsifiable. **Carve-out:** specifically attributed, checkable validation is legitimate — a
named benchmark, a linked report, a dated audit.
> **Before:** Independent testing confirms the institute's standing among its peers.
> **After:** The 2019 national research assessment ranked the institute second in materials science.

---

## Family 3 — Superficial analysis & filler

### 3.1 Superficial "-ing" analyses (WP)
**Watch:** highlighting/underscoring/emphasizing…, reflecting/symbolizing…, contributing to…,
ensuring…, fostering…, showcasing…, encompassing… (participle tacked to a sentence end).
**Problem:** Fake depth via a trailing participle phrase, often with vague attribution.
> **Before:** The station links major cities, contributing to the socio-economic development of the region.
> **After:** The station connects Darbhanga to Delhi, Patna, and Kolkata.

### 3.2 Filler phrases (SS/PDF)
**Watch:** In order to, Due to the fact that, At this point in time, In the event that, has the ability to, It is important to note that.
> **Before:** In order to achieve this goal, the system has the ability to process requests.
> **After:** To do this, the system can process requests.

### 3.3 Filler openers / adverbs (SS)
**Watch:** At its core, In today's [X], It's worth noting, Interestingly, Importantly, Crucially, At the end of the day, When it comes to, In a world where, The reality is.
**Fix:** Delete; start with content.

### 3.4 Excessive hedging (SS/PDF)
**Watch:** could potentially possibly, might have some, perhaps, may possibly.
> **Before:** It could potentially possibly be argued that the policy might have some effect.
> **After:** The policy may affect outcomes.

### 3.5 Formulaic "challenges & future prospects" sections (WP)
**Watch:** "Despite its… faces several challenges…", "Despite these challenges", "Challenges and Legacy", "Future Outlook".
**Problem:** A rigid outline slot, not real analysis — usually closing on vague optimism.
> **Before:** Despite challenges typical of urban areas, the town continues to thrive thanks to ongoing initiatives.
> **After:** Traffic rose after 2015 when three IT parks opened; a 2022 drainage project addressed recurring floods.

### 3.6 Generic positive conclusions (SS)
**Watch:** the future looks bright, exciting times lie ahead, a step in the right direction, journey toward excellence.
> **Before:** The future looks bright. Exciting times lie ahead.
> **After:** The company plans to open two more locations next year.

## Family 4 — AI vocabulary & diction

### 4.1 High-density "AI vocabulary" (WP)
The list is tiered by what a hit *means* (tiering adapted from avoid-ai-writing / brandonwise's
vocabulary research). The frequency claims behind Tier 1A are inherited from those sources, not
measured here — treat them as a well-supported convention.

**Tier 1A — frequency markers** (reported far more common in machine text; two distinct 1A words
anywhere is already a cluster): delve, emphasizing, enduring, garner, interplay,
intricate/intricacies, landscape (abstract), meticulous(ly), pivotal, robust, showcase/showcasing,
tapestry (abstract), testament, underscore (verb), vibrant.

**Tier 2 — cluster-only** (legitimate alone; evidence when 2+ share a paragraph or 3+ share a
document): additionally (sentence-initial), align with, boasts, bolstered, cornerstone, crucial,
enhance, foster(ing), highlight(ing) (verb), key (adj), leverage, unlock, valuable.

**Problem:** Post-2022 over-represented words. One is coincidence; a *cluster* is a strong tell,
and a 1A cluster is the strongest vocabulary evidence available.
**Era (so the skill ages well — tells drift):**
- 2023–mid-2024 (GPT-4): additionally, boasts, bolstered, crucial, delve, emphasizing, enduring, garner, intricate, interplay, key, landscape, meticulous, pivotal, underscore, tapestry, testament, valuable, vibrant.
- mid-2024–mid-2025 (GPT-4o): align with, bolstered, crucial, emphasizing, enhance, enduring, fostering, highlighting, pivotal, showcasing, underscore, vibrant.
- mid-2025+ (GPT-5): emphasizing, enhance, highlighting, showcasing (+ notability/attribution wording).
- *Faded:* `delve` spiked in 2023–24, dropped off in 2025 — don't treat it as current.
> **Before:** An enduring testament to Italian influence is pasta in the local culinary landscape, showcasing how dishes integrated.
> **After:** Pasta, introduced during Italian colonization, is still common, especially in the south.

### 4.2 AI intensifiers (SS)
**Watch:** deeply, truly, fundamentally, inherently, simply, literally, inevitably. **Fix:** usually delete.

### 4.3 Academic register inflation — Tier 1B, a clarity edit (PDF)
**Watch:** utilize→use, commence→start, demonstrate→show, facilitate→help, endeavor→try,
ascertain→find out.
**Problem:** Latinate word picked over a plain Germanic one regardless of context. **A 1B hit is
NOT authorship evidence** — plenty of humans write "utilize" in formal registers. Fix it as good
editing, report it separately from the vocabulary cluster (the CLI emits it as
`clarity.wordiness` with zero risk contribution), and never present a wordiness fix as evidence
about who wrote the text.
> **Before:** Organizations can utilize these tools to facilitate efficiency.
> **After:** Companies can use these tools to work faster.

### 4.4 Business jargon (SS)
**Watch / fix:** navigate (challenges)→handle; unpack→explain; lean into→accept; deep dive→analysis;
game-changer→significant; double down→commit; take a step back→reconsider; moving forward→next;
circle back→revisit; on the same page→agreed; leverage→use; synergy→(cut); paradigm shift→(cut).

### 4.5 Empty words: bleaching, vague quantifiers, tautology (PDF)
**Watch:** significant/notable/considerable (adding nothing); numerous/various/multiple (no number);
"success requires successful strategies" (tautology).
> **Before:** Numerous significant factors play a considerable role.
> **After:** Three things drive it: price, timing, and trust.

### 4.6 Redundant intensifiers (PDF)
**Watch:** very unique, extremely essential, critically important, absolutely vital. **Fix:** drop the modifier; "unique" and "essential" are already absolute.

### 4.7 Modifier stacking (PDF)
**Watch:** 3+ adjectives per noun ("comprehensive, multifaceted, innovative approach").
> **Before:** a comprehensive, multifaceted, innovative approach.
> **After:** a broad approach. (Pick the one adjective that carries information.)

### 4.8 Elegant variation / synonym cycling (WP)
**Problem:** Repetition-penalty causes needless synonym swaps for the same referent.
> **Before:** The protagonist faces challenges. The main character must overcome obstacles. The hero returns home.
> **After:** The protagonist faces many challenges but eventually returns home.

---

## Family 5 — Syntactic tells (PDF)

### 5.1 Anticipatory "it"
**Watch:** It is important to note that…, It should be emphasized that…, It is worth mentioning that…
> **Before:** It is important to note that adoption varies.  **After:** Adoption varies.

### 5.2 Existential "there"
**Watch:** There are several factors that…, There exists a need for…
> **Before:** There are several factors that influence cost.  **After:** Three things influence cost: …

### 5.3 Passive-voice hedging
**Watch:** It has been shown that…, It can be argued that…, It is widely believed that…
> **Before:** It has been shown that the method works.  **After:** A 2023 trial showed the method works. (or: The method works.)

### 5.4 Cleft sentences for false emphasis
**Watch:** It is through X that Y…, What matters is…, It was X that…
> **Before:** It is through careful planning that results are achieved.  **After:** Careful planning produces results.

### 5.5 Hypotactic over-complexity
**Problem:** Stacked subordinate clauses (while/although/whereas) bury the point.
> **Before:** While the tool is useful, although it has limits, whereas alternatives exist, teams adopt it.
> **After:** The tool is useful but limited. Teams adopt it anyway.

### 5.6 Front-loaded transitions
**Problem:** Most sentences open with a discourse marker (Moreover/Furthermore/Additionally/However).
**Fix:** Cut most; let sentence order carry the logic. (A single "however" is fine — see don't-over-correct.)

### 5.7 Cohesion-device overuse
**Watch:** As previously mentioned, As we have seen, Building upon this; "This approach/These factors"
(demonstrative obsession); "Also… Moreover… Furthermore… Additionally…" chains.
> **Before:** Building upon this, as previously mentioned, this approach addresses these factors.
> **After:** This also fixes the latency problem.

---

## Family 6 — Verbosity & padding (PDF)

### 6.1 Nominalization excess
**Watch:** give consideration to→consider, make a decision→decide, provide an explanation→explain, conduct an analysis→analyze.

### 6.2 Periphrastic constructions
**Watch:** is able to→can, has the capacity to→can, in spite of the fact that→although, at this moment in time→now.

### 6.3 Redundant clarification
**Watch:** In other words, That is to say, To put it another way, Simply put. **Fix:** say it once, well.

### 6.4 Elaboration compulsion
**Problem:** Never letting a plain statement stand.
> **Before:** The sky exhibits a blue coloration due to atmospheric light scattering.  **After:** The sky is blue.

### 6.5 Example inflation
**Problem:** Three examples where one proves the point. **Fix:** keep the best one.

### 6.6 Unnecessary precision
**Watch:** "approximately 7–10 days", false exactness. **Fix:** "about a week."

### 6.7 Both-sides-ism / false balance
**Watch:** "On one hand… on the other hand" for non-opposing ideas; reflexive "however" + counterpoint.
> **Before:** On one hand it is fast; on the other, it is useful.  **After:** It is fast and useful.

### 6.8 Coverage anxiety
**Problem:** Trying to cover every angle / adding defensive qualifiers to never be wrong. **Fix:** cover what matters; cut the hedges.

## Family 7 — Rhetorical formulas

### 7.1 Binary contrasts (SS)
**Watch:** "Not because X. Because Y.", "X isn't the problem. Y is.", "The answer isn't X. It's Y."
> **Before:** Not because the technology is complex. Because people are.  **After:** The hard part is people, not technology.

### 7.2 Negative parallelism (WP)
**Watch:** "Not just X, but Y", "Not only… but also", "It's not merely a song, it's a statement."
> **Before:** It's not just about the beat; it's about the aggression.  **After:** The heavy beat drives the aggressive tone.

### 7.3 Rule of three (WP/PDF)
**Watch:** triplets everywhere — "efficient, effective, and elegant"; "engaged, motivated, and successful."
**Problem:** Ideas forced into threes to feel complete. **Fix:** two items, or one. (Real triads are fine — judge by content, not count.)

### 7.4 False ranges (WP)
**Watch:** "from X to Y" where X and Y aren't on a scale.
> **Before:** from the Big Bang to the cosmic web, from stars to dark matter.  **After:** the Big Bang, star formation, and dark matter.

### 7.5 Dramatic fragmentation (SS)
**Watch:** "Speed. Quality. Cost.", "X. That's it. That's the [thing].", "And Y. And Z."
> **Before:** Speed. Quality. Cost. You can only pick two. That's it.  **After:** Speed, quality, cost — pick two.

### 7.6 Rhetorical setups (SS)
**Watch:** "What if I told you…?", "Here's what I mean:", "Think about it:", "And that's okay."
> **Before:** What if I told you the best teams optimize for learning?  **After:** The best teams optimize for learning.

### 7.7 Throat-clearing openers (SS)
**Watch:** "Here's the thing:", "The truth is,", "Let me be clear", "The uncomfortable truth is", "It turns out".
> **Before:** Here's the thing: most startups fail on team dynamics.  **After:** Most startups fail on team dynamics.

### 7.8 Emphasis crutches (SS)
**Watch:** "Full stop.", "Period.", "Let that sink in.", "Make no mistake", "This matters because".
**Fix:** delete — write well enough that the reader feels it.

### 7.9 Meta-commentary (SS)
**Watch:** "Plot twist:", "Spoiler:", "Hint:", "You already know this, but", "X is a feature, not a bug."
> **Before:** Plot twist: the real bottleneck was never the technology.  **After:** The bottleneck was management.

### 7.10 Fortune-cookie endings & confident prediction (PDF)
**Watch:** payoff framing ("For teams, the payoff is…"), prediction closers ("will ship better software,
faster"), "Those who [do X] will [win]…" closers.
> **Before:** Those who master the fundamentals will ship better software, faster.  **After:** (end on the last real point; cut the slogan.)

### 7.11 Forced analogies & mixed metaphors (PDF)
**Watch:** technical/crystalline metaphors ("crystal ball", "wiring models into shells"), workplace
analogies for everything, chains ("climb the learning curve… stay focused… feels lighter").
**Fix:** at most one fresh, concrete image; cut the chain.

---

## Family 8 — Structure & formatting

### 8.1 Title patterns (PDF)
**Watch:** colon addiction ("Coding with AI: A Practical Snapshot"), "Benefits and Challenges of…",
"The [Adjective] [Noun]" ("The Essential Guide"), gerund titles ("Understanding/Navigating/Exploring…").
**Fix:** name the thing plainly.

### 8.2 Opening patterns (PDF)
**Watch:** scene-setting ("Picture this:", "Imagine:"), in-medias-res ("You're staring at…"), temporal
("In today's world,", "In recent years,"), question openers ("Have you ever wondered…?").
**Fix:** open on the actual subject.

### 8.3 Title-case headings (WP)
> **Before:** ## Strategic Negotiations And Global Partnerships  **After:** ## Strategic negotiations and global partnerships

### 8.4 Boldface overuse (WP)
**Problem:** Mechanical bolding of terms/acronyms.
> **Before:** It blends **OKRs**, **KPIs**, and the **BMC**.  **After:** It blends OKRs, KPIs, and the Business Model Canvas.

### 8.5 Inline-header vertical lists (WP)
**Problem:** Lists where each item is **Bold Header:** followed by a restating sentence.
> **Before:** - **Performance:** Performance was improved through optimization.  **After:** (prose) The update speeds up load times through optimized queries.

### 8.6 Em-dash overuse (WP) — *weak signal alone*
**Problem:** Em dashes used as a crutch before reveals / for pseudo-profound contrasts ("not X — but Y").
**Fix:** replace the *crutch* uses with commas/periods; **keep** a genuine em dash. A lone em dash is
not proof of AI — only its over-frequency + the "not X — but Y" pattern.

### 8.7 Emojis (WP)
**Problem:** Decorating headings/bullets (🚀 Launch, 💡 Key Insight). **Fix:** remove.

### 8.8 Curly quotes / apostrophes (WP)
**Problem:** ChatGPT outputs " " ' instead of straight quotes; a tell when the surrounding doc uses straight ones. **Fix:** match the document's convention.

### 8.9 Unusual use of tables (WP)
**Problem:** AI defaults to tables for content that should be prose or a short list. **Fix:** convert to prose unless the data is genuinely tabular.

### 8.10 Markdown leaking into non-markdown targets (WP)
**Problem:** `**bold**`, `## headings`, `- bullets` pasted into a wiki/plaintext/CMS that doesn't render them. **Fix:** convert to the target's markup (or plain text).

### 8.11 Skipped heading levels & thematic breaks before headings (WP)
**Watch:** jumping H2→H4; a `---` rule placed right before every heading. **Fix:** sequential levels; drop the decorative rules.

### 8.12 Paragraph uniformity & mechanical structure (PDF)
**Problem:** Every paragraph 3–5 sentences, topic→2-3 support→transition. No one-line paragraphs, no long ones. **Fix:** vary length deliberately; use a one-sentence paragraph for emphasis.

### 8.13 Information-architecture tells (PDF)
**Watch:** setup paragraph → bulleted list → philosophical ending; hedging-then-certainty ("Of course,
these still err" → "but AI will…"); contrived specificity ("build a REST endpoint for products by tag");
relatability bait ("while your coffee cools"). **Fix:** break the template; cut the staged moves.

### 8.14 List-label periods (avoid-ai-writing)
**Problem:** In labeled bullet lists, LLMs end the label with a period where a person writes a colon.
**Carve-out:** a label that is a full sentence on its own keeps its period.
> **Before:** - **Intros.** Years of conferences and operator network.
> **After:** - **Intros:** years of conferences and operator network.

### 8.15 Diff-anchored writing (avoid-ai-writing) — *judgment-only*
**Watch:** docs or comments narrating the change instead of the artifact: "This function was added to
replace the previous approach…". Assistants write docs anchored to the edit they just made; a person
documenting later writes from the artifact. **Fix:** describe current behavior and why it is that way;
history belongs in the changelog. **Carve-outs:** changelogs, release notes, migration guides, and
decision records narrate change correctly. Judgment-only — telling a version-scoped document from a
misanchored one needs the register, which a regex cannot read.

---

## Family 9 — Chatbot residue (prose) & artifacts

### 9.1 Collaborative-communication artifacts (WP/SS)
**Watch:** "I hope this helps", "Of course!", "Certainly!", "Would you like…", "let me know", "here is a…".
> **Before:** Here is an overview. I hope this helps! Let me know if you'd like more.  **After:** (just the overview.)

### 9.2 Sycophantic / servile tone (SS)
**Watch:** "Great question!", "You're absolutely right!", "That's an excellent point."
> **Before:** Great question! You're absolutely right that this is complex.  **After:** (answer the question.)

### 9.3 Knowledge-cutoff disclaimers (WP)
**Watch:** "as of my last update", "Up to my last training update", "While specific details are limited/scarce…", "based on available information".
> **Before:** While specific details are limited in available sources, it was likely founded in the 1990s.  **After:** It was founded in 1994 (registration records).

### 9.4 Section summaries (WP, historical-but-recurring)
**Watch:** "In summary", "In conclusion", "Overall" + a paragraph restating what was just said. **Fix:** delete the restatement.

### 9.5 Didactic disclaimers (WP, historical-but-recurring)
**Watch:** "it's important/crucial to note/remember/consider", "worth noting", "may vary". **Fix:** delete or state the fact directly.

### 9.6 Sudden English-variety shift (WP)
**Problem:** US/UK spelling mixed within one text (organize + colour) — a stitching tell. **Fix:** pick one variety and make it consistent (for this user: American — see workspace wiki rules).

### 9.7 Artifact tokens & placeholder text
Dead-giveaway leakage (`citeturn0search0`, `:contentReference[oaicite:N]`, `oai_citation`, `grok_card`,
`【85†…】`, AI-referrer URL params such as `utm_source=chatgpt.com` / `utm_source=claude.ai` /
`referrer=grok.com`, `[Your Name]`, `2025-XX-XX`): **see `reference/llm-artifacts.md`**
for the full list and detection regexes. These are deterministic — sweep for them every time.

### 9.8 Roleplay action markers
**Watch:** `*nods*`, `*sighs*`, `*pauses thoughtfully*` — paired-asterisk action beats from a
chat persona, pasted into prose. Verb-anchored; ordinary `*italic emphasis*` is not this tell.
**Fix:** delete the marker (llm-artifacts.md §10).

### 9.9 Detector-bypass characters
**Watch:** zero-width characters inside words; Cyrillic/Greek lookalike letters spliced into Latin
words. These arrive from "humanizer" bypass tools, not from authors. The audit CLI normalizes them
before matching and flags `artifact.bypass_characters` (llm-artifacts.md §11). Treat any hit as the
strongest possible signal that the text was machine-processed to evade scanners.

### 9.10 Wall-of-text replies (avoid-ai-writing) — *judgment-only*
**Watch:** in conversational registers only (chat, Discord, forum/issue replies): a reply-length
text (~under 150 words) with four or more sentences and no line break anywhere. Humans break replies
at thought boundaries; LLMs default to one dense block. **Fix:** break at thought boundaries, one
idea per line-group. **Never** flag continuous long-form prose for lacking internal breaks — a tight
single paragraph is the correct shape in formal registers, which is exactly why this stays
judgment-only (a regex cannot read the register).


