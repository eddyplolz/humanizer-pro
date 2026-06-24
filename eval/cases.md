# Humanizer Pro v4.1 Manual Evaluation Cases

Use these fixtures after skill changes. They are not automated tests; they are small regression prompts
for checking behavior, restraint, and source discipline.

## Fixtures

| Fixture | Expected behavior |
|---|---|
| `fixtures/clean-human.md` | Leave mostly unchanged. At most suggest one optional clarity tweak. |
| `fixtures/ai-slop-general.md` | Return concise, specific prose with fewer formulas, less padding, and no fake-casual swap. |
| `fixtures/wiki-promotional.md` | Rewrite neutrally; remove unsupported significance; preserve or flag citation needs. |
| `fixtures/over-humanized.md` | Remove performed casualness, meta-commentary, ellipses, and decorative profanity without making the piece stiff. |
| `fixtures/artifact-leakage.md` | Flag artifact tokens and placeholders; remove chat wrapper; note unsupported citation-dependent claims. |
| `fixtures/style-elements.md` | Improve clarity, concrete language, paragraph unity, and emphasis without flattening the writer's legitimate voice. |

## Required Checks

- Simple "humanize this" returns only the final rewrite plus serious source-risk notes.
- Explicit "full audit" returns score, artifact flags, family-tagged rationale, draft rewrite, final
  rewrite, and what stayed on purpose.
- Wiki/article mode does not add personality, jokes, first person, or unsupported claims.
- Markdown leakage in wiki/plaintext targets is converted or flagged.
- Artifact leakage such as `oai_citation`, `contentReference`, `turn0search0`, or
  `utm_source=chatgpt.com` is flagged before prose editing.
- Candidate self-improvement lessons are rejected unless they pass the promotion gate in
  `reference/improvement-loop.md`.
