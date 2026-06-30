# Humanizer Pro v4.1 Manual Evaluation Cases

Use these fixtures after skill changes. They serve two purposes: manual regression prompts for editing
behavior and automated contracts for the deterministic audit CLI.

## Fixtures

| Fixture | Expected behavior |
|---|---|
| `fixtures/clean-human.md` | Leave mostly unchanged. At most suggest one optional clarity tweak. |
| `fixtures/ai-slop-general.md` | Return concise, specific prose with fewer formulas, less padding, and no fake-casual swap. |
| `fixtures/wiki-promotional.md` | Rewrite neutrally; remove unsupported significance; preserve or flag citation needs. |
| `fixtures/over-humanized.md` | Remove performed casualness, meta-commentary, ellipses, and decorative profanity without making the piece stiff. |
| `fixtures/artifact-leakage.md` | Flag artifact tokens and placeholders; remove chat wrapper; note unsupported citation-dependent claims. |
| `fixtures/style-elements.md` | Improve clarity, concrete language, paragraph unity, and emphasis without flattening the writer's legitimate voice. |
| `fixtures/fidelity/original.md` + `revised-good.md` | `--compare` exits clean when protected facts and source targets are preserved, including normalized tracking parameters. |
| `fixtures/fidelity/original.md` + `revised-drift.md` | `--compare` blocks protected-content drift in numbers, dates, URLs, citations, quotes, code, and evidence markers. |

## Required Checks

- `py -3 -m pytest -q tests` passes for the automated `humanizer-audit` contracts.
- `py -3 scripts/humanizer_audit.py eval/fixtures --json` returns schema `humanizer-audit.v1`.
- `py -3 scripts/humanizer_audit.py --compare eval/fixtures/fidelity/original.md eval/fixtures/fidelity/revised-drift.md --json`
  returns protected-content drift findings without style scoring.
- Simple "humanize this" returns only the final rewrite plus serious source-risk notes.
- Explicit "full audit" returns score, artifact flags, family-tagged rationale, draft rewrite, final
  rewrite, and what stayed on purpose.
- Wiki/article mode does not add personality, jokes, first person, or unsupported claims.
- Markdown leakage in wiki/plaintext targets is converted or flagged.
- Artifact leakage such as `oai_citation`, `contentReference`, `turn0search0`, or
  `utm_source=chatgpt.com` is flagged before prose editing.
- Candidate self-improvement lessons are rejected unless they pass the promotion gate in
  `reference/improvement-loop.md`.
