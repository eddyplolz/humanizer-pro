# WARP.md

This file provides guidance to WARP (warp.dev) and other agents working in this repository.

## What This Repo Is

This repository is a Claude Code skill implemented as Markdown plus progressively loaded references
and manual eval fixtures.

The runtime artifact is `SKILL.md`: Claude Code reads the YAML frontmatter and the prompt/instructions
that follow. Keep it lean.

`README.md` is for humans: installation, usage, file layout, modes, validation, and version history.

## Key Files

- `SKILL.md`
  - Source of truth for routing, operating principles, compact nine-family index, quick checklist,
    scoring, workflow, and output formats.
  - Keep under 350 lines for v4.1.
  - Do not paste long examples, full Strunk guidance, or one-off improvement notes here.
- `reference/`
  - `tell-catalog.md` - full pattern library with watch-words and examples.
  - `llm-artifacts.md` - deterministic detector for leaked tokens/placeholders.
  - `worked-examples.md` - full before/audit/after edits, including the restraint case.
  - `style-principles.md` - compact Elements of Style operating checklist.
  - `elements-of-style-1918.md` - full public-domain Project Gutenberg text; do not load by default.
  - `wiki-mode.md` - neutral, source-bound article and wikitext workflow.
  - `improvement-loop.md` - controlled promotion process for recurring failures.
- `eval/`
  - `cases.md` - manual validation matrix.
  - `fixtures/*.md` - regression samples for clean human prose, AI slop, wiki promotional tone,
    over-humanizing, artifact leakage, and Elements-style edits.

## Common Commands

Install the skill:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

Manual install/update:

```bash
mkdir -p ~/.claude/skills/humanizer-pro
cp -r SKILL.md reference/ eval/ ~/.claude/skills/humanizer-pro/
```

Invoke in Claude Code:

```text
/humanizer-pro
```

## Making Changes Safely

- Preserve valid YAML frontmatter in `SKILL.md`.
- Keep the family numbering (1-9) and `reference/tell-catalog.md` section numbers stable unless the
  whole catalog is intentionally renumbered.
- Add depth and examples to `reference/`, not `SKILL.md`.
- Add regression examples to `eval/fixtures/` and expectations to `eval/cases.md`.
- Use `reference/improvement-loop.md` before promoting a recurring failure.
- Do not add detector APIs, automatic memory accumulation, autonomous optimization loops, large
  dependencies, or runtime scripts for v4.1.
- If behavior changes, update `README.md` version history.

## Validation

Before claiming a skill behavior change is done:

1. Check `SKILL.md` remains under 350 lines.
2. Run the manual cases in `eval/cases.md`.
3. Confirm `clean-human.md` is mostly unchanged.
4. Confirm artifact fixtures produce source-risk notes.
5. Confirm wiki/article mode stays neutral and source-bound.
