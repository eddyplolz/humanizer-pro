# Improvement Loop

Humanizer Pro can improve over time, but only through review. Do not add automatic memory
accumulation, detector APIs, autonomous optimize-until-green loops, large scripts, or one-off clever
observations directly into `SKILL.md`.

## Promotion Path

Observation -> Candidate -> Fixture -> Review -> Promotion -> Regression check

## 1. Observation

Record the concrete miss:

- What text failed?
- What did the skill do wrong or miss?
- Which existing family or mode should have caught it?
- Was it repeated, serious, or only a one-off?

## 2. Candidate

Turn the observation into a candidate rule only if it appears repeatedly or caused a serious miss. Map
it to an existing family, mode, or reference file whenever possible.

Reject candidates that:

- Encourage over-editing.
- Duplicate an existing rule.
- Depend on a single user's one-off taste.
- Require a detector API or external service.
- Need more than about 80 words to state.

## 3. Fixture

Add a representative example under `eval/fixtures/` or extend `eval/cases.md`. The fixture should show
the failure without leaking the intended solution into the input text.

Include at least one before/after example in the candidate note. Keep examples synthetic unless the
source text is owned or safe to quote.

## 4. Review

Before promotion, check:

- Does it fit an existing family or justify a small sub-rule?
- Does it improve the failure without damaging clean human prose?
- Does it preserve source discipline?
- Does it avoid fake voice and anti-swap failures?
- Does it pass the clean-human restraint fixture?

## 5. Promotion

Promote to the smallest durable home:

- `SKILL.md` only for routing, core principles, or compact checklist hooks.
- `reference/tell-catalog.md` for a new tell family detail.
- `reference/style-principles.md` for style guidance.
- `reference/wiki-mode.md` for article/source-bound guidance.
- `eval/cases.md` for regression expectations.

## 6. Regression Check

After promotion, manually run the relevant fixtures:

- `clean-human.md` must remain mostly unchanged.
- `ai-slop-general.md` must become plainer and less formulaic.
- `wiki-promotional.md` must become neutral and source-bound.
- `over-humanized.md` must lose fake-casual performance without becoming stiff.
- `artifact-leakage.md` must produce source-risk notes.

If the rule only passes by making every fixture more aggressively edited, reject it.
