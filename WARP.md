# WARP.md

This file provides guidance to WARP (warp.dev) and other agents working in this repository.

## What This Repo Is

This repository is a Claude Code and Codex skill implemented as Markdown plus progressively loaded
references and manual eval fixtures.

The shared runtime artifact is `SKILL.md`: Claude Code reads the YAML frontmatter and the
prompt/instructions that follow, while Codex uses the `name` and `description` fields plus
`agents/openai.yaml` UI metadata. Keep `SKILL.md` lean.

`README.md` is for humans: installation, usage, file layout, modes, validation, and version history.

## Key Files

- `SKILL.md`
  - Source of truth for routing, operating principles, compact nine-family index, quick checklist,
    scoring, workflow, and output formats.
  - Keep under 350 lines for v4.x.
  - Do not paste long examples, full Strunk guidance, or one-off improvement notes here.
- `agents/openai.yaml`
  - Codex-facing display metadata and default `$humanizer-pro` prompt.
  - Regenerate with `skill-creator` if the skill name, description, or primary invocation changes.
- `reference/`
  - `tell-catalog.md` - full pattern library with watch-words and examples.
  - `llm-artifacts.md` - deterministic detector for leaked tokens/placeholders.
  - `ai-check.md` - score-only audit mode for "check this," "score this," and "do not rewrite."
  - `worked-examples.md` - full before/audit/after edits, including the restraint case.
  - `style-principles.md` - compact Elements of Style operating checklist.
  - `elements-of-style-1918.md` - full public-domain Project Gutenberg text; do not load by default.
  - `wiki-mode.md` - neutral, source-bound article and wikitext workflow.
  - `improvement-loop.md` - controlled promotion process for recurring failures.
- `eval/`
  - `cases.md` - manual validation matrix.
  - `contracts/*.json` - automated expectations for deterministic audit behavior.
  - `fixtures/*.md` - regression samples for clean human prose, AI slop, wiki promotional tone,
    over-humanizing, artifact leakage, and Elements-style edits.
- `scripts/`
  - `humanizer_audit.py` - zero-dependency deterministic audit CLI.
- `tests/`
  - pytest coverage for the audit CLI and fixture contracts.

## Common Commands

Install for Claude Code on POSIX:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

Install for Claude Code on Windows:

```bat
mkdir "%USERPROFILE%\.claude\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.claude\skills\humanizer-pro"
```

Install for Codex or generic agents on POSIX:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.agents/skills/humanizer-pro
```

Install for Codex or generic agents on Windows:

```bat
mkdir "%USERPROFILE%\.agents\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.agents\skills\humanizer-pro"
```

Manual install/update on POSIX:

```bash
mkdir -p ~/.claude/skills/humanizer-pro
cp -r SKILL.md agents/ reference/ scripts/ eval/ ~/.claude/skills/humanizer-pro/
```

Invoke in Claude Code:

```text
/humanizer-pro
```

Invoke in Codex:

```text
Use $humanizer-pro to check this draft for AI-writing tells without rewriting it.
```

Run the deterministic audit CLI on Windows:

```bat
py -3 scripts\humanizer_audit.py eval\fixtures\ai-slop-general.md
py -3 scripts\humanizer_audit.py eval\fixtures --json
py -3 scripts\humanizer_audit.py --compare original.md revised.md --json
```

Run the deterministic audit CLI on POSIX:

```bash
python3 scripts/humanizer_audit.py eval/fixtures/ai-slop-general.md
python3 scripts/humanizer_audit.py eval/fixtures --json
python3 scripts/humanizer_audit.py --compare original.md revised.md --json
```

## Making Changes Safely

- Preserve valid YAML frontmatter in `SKILL.md`.
- Keep `agents/openai.yaml` aligned with `SKILL.md` when trigger wording or primary usage changes.
- Keep the family numbering (1-9) and `reference/tell-catalog.md` section numbers stable unless the
  whole catalog is intentionally renumbered.
- Add depth and examples to `reference/`, not `SKILL.md`.
- Add regression examples to `eval/fixtures/` and expectations to `eval/cases.md`.
- Use `reference/improvement-loop.md` before promoting a recurring failure.
- Runtime scripts must stay deterministic and zero-dependency unless a later approved plan changes
  that constraint.
- AI check mode is score-only. It reports blockers, family hits, source-risk notes, and evidence; it
  must not rewrite unless the user separately asks.
- Compare mode is a fidelity guard only. It checks protected facts and evidence markers; it must not
  become a style scorer or detector-bypass loop.
- Do not add detector APIs, automatic memory accumulation, autonomous optimization loops, or large
  dependencies for this audit-tooling slice.
- If behavior changes, update `README.md` version history.

## Validation

Before claiming a skill behavior change is done:

1. Check `SKILL.md` remains under 350 lines.
2. Run `py -3 -m pytest -q tests`.
3. Run `py -3 scripts/humanizer_audit.py eval/fixtures --json`.
4. Run `py -3 scripts/humanizer_audit.py --compare eval/fixtures/fidelity/original.md eval/fixtures/fidelity/revised-drift.md --json` when compare behavior changes.
5. Run the manual cases in `eval/cases.md` when edit behavior changes.
6. Confirm `clean-human.md` is mostly unchanged.
7. Confirm artifact fixtures produce source-risk notes.
8. Confirm wiki/article mode stays neutral and source-bound.
