# Coverage Map: catalog prose ↔ audit CLI

The anti-drift contract between the human-readable rules (`SKILL.md`, `reference/tell-catalog.md`,
`reference/llm-artifacts.md`) and the executable subset in `scripts/humanizer_audit.py` — the idea
is adapted from avoid-ai-writing's `detector/CATEGORIES.md` (MIT). When you add a catalog rule,
decide here whether it is regex-detectable (give it a CLI rule id) or judgment-only (record why).
When you add a CLI rule, point it back at the catalog section it enforces.
`tests/test_humanizer_audit.py::test_every_cli_rule_id_is_in_the_coverage_map` enforces the
CLI-side half: every rule id the CLI can emit must appear in this file.

## A. CLI rule → catalog section

### Artifact rules (`llm-artifacts.md`; severity error, exit 2)

| CLI rule id | Section |
|---|---|
| `artifact.chatgpt_citation_stub` | §1 ChatGPT citation stubs |
| `artifact.content_reference` | §2 contentReference/oaicite markup |
| `artifact.oai_citation` | §2 OpenAI citation residue |
| `artifact.attribution_json` | §3 JSON attribution blocks |
| `artifact.perplexity_tag` | §4 Perplexity tags |
| `artifact.grok_card` | §5 Grok citation cards |
| `artifact.lenticular_reference` | §6 Lenticular-bracket references |
| `artifact.ai_tracking_url` | §7 AI-tool tracking parameters |
| `artifact.bracket_placeholder` | §8 Unfilled placeholders (bracket form) |
| `artifact.insert_placeholder` | §8 Unfilled placeholders (ALL-CAPS form) |
| `artifact.placeholder_comment` | §8 Unfilled placeholders (HTML-comment form) |
| `artifact.placeholder_date` | §9 Placeholder dates |
| `artifact.roleplay_marker` | §10 Roleplay action markers |
| `artifact.bypass_characters` | §11 Detector-bypass characters (emitted by the normalization pre-pass) |

### Tell-family rules (`tell-catalog.md`; sentinel phrases, severity warning)

Each family rule is a *sentinel subset* of its catalog family, not full coverage — the catalog
always says more than the regex.

| CLI rule id | Catalog sections |
|---|---|
| `family1.significance_inflation` | §1.1–1.3 significance, promotional tone, copula avoidance |
| `family2.vague_attribution` | §2.1–2.3 weasel attribution, notability padding |
| `family2.speculative_gap_filling` | §2.4 speculative gap-filling |
| `family2.vague_validation` | §2.5 vague third-party validation |
| `family3.filler_framing` | §3.1–3.6 filler, superficial -ing, formulaic sections |
| `family4.ai_vocab_cluster` | §4.1 tiered AI vocabulary (Tier 1A/2; cluster logic in `ai_vocab_findings`) |
| `family5.syntactic_tell` | §5.1–5.7 anticipatory it, existential there, hedged passives |
| `family6.verbosity_padding` | §6.1–6.8 nominalization, periphrasis |
| `family7.rhetorical_formula` | §7.1–7.11 binary contrasts, throat-clearing, forced triplets |
| `family8.markdown_structure` | §8.3–8.11 structure and markup tells |
| `family8.list_label_period` | §8.14 list-label periods |
| `family9.chatbot_residue` | §9.1–9.5, §9.11 chat wrappers, sycophancy, summaries, RLHF framing |

### Clarity rules (Tier 1B; info severity, zero risk weight)

| CLI rule id | Section |
|---|---|
| `clarity.wordiness` | §4.3 academic register inflation + §3.2 multi-word filler wrappers — a clarity edit, never authorship evidence |

### Source-risk rules (`wiki-mode.md` source discipline; verification needs, not tells)

| CLI rule id | Purpose |
|---|---|
| `source_risk.citation_markup` | Citation markup present — verify before editing near it |
| `source_risk.bare_url` | Bare URL — verify the target supports the claim |
| `source_risk.source_dependent_statement` | Reporting language — the claim leans on a source |

### Structure/stylometric rules (info severity; CLI-only, no single catalog phrase)

| CLI rule id | Basis |
|---|---|
| `structure.low_sentence_variance` | §8.12 paragraph/sentence uniformity, as a computed statistic |
| `structure.long_uniform_paragraphs` | §8.12, paragraph-level variant |
| `structure.uniform_length_run` | §7.13/§8.12 — 4+ consecutive sentences within 5 words of each other (HH countable proxy) |
| `structure.midband_dominance` | §8.12 — most sentences in the 10–20 word band with a narrow range (HH countable proxy) |
| `structure.anaphora` | §7.13 — 3+ consecutive sentences sharing an opening word |

### Compare mode (fidelity guards, not tells)

All ids under the `compare.` prefix (`compare.<kind>.dropped` / `.introduced` / `.changed` /
`compare.citation.changed_target` / `compare.source_statement.*`) enforce the source-discipline
promises in `wiki-mode.md` and the never-inject rules in `SKILL.md`. They judge protected-content
drift only, never style.

## B. Judgment-only (no CLI rule, on purpose)

Catalog rules that need the register or the meaning read, so they live in skill prose and are
applied by the model. Their absence from the CLI is a decision, not a gap:

- **Elegant variation / synonym cycling (§4.8)** — needs coreference ("is this the same referent?").
- **Copula-avoidance nuance (§1.3)** — the sentinel regex catches stock phrases; deciding whether
  "serves as" is inflated in context is a read.
- **Em-dash judgment (§8.6)** — a *rate and intent* call; a regex count would flag legitimate prose.
- **Title/opening patterns (§8.1–8.2)** — colon titles and scene-setting openers are common in
  human writing; only the combination with other tells convicts.
- **Rule of three (§7.3)** — real triads are fine; the CLI's naive triplet pattern inside
  `family7.rhetorical_formula` deliberately catches only the most mechanical form.
- **Diff-anchored writing (§8.15)** — changelog-register carve-outs cannot be read by a regex.
- **Wall-of-text replies (§9.10)** — fires only in conversational registers; tried as a detector
  upstream (avoid-ai-writing) and reverted because it flagged every ordinary short paragraph.
- **English-variety drift (§9.6)** — needs the document's dominant variety established first.
- **Paragraph uniformity as an *edit* (§8.12)** — the CLI reports the statistic; deciding whether
  to break rhythm is a meaning call.
