# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## What this repo is
This repository is a **Claude Code skill** implemented entirely as Markdown.

The “runtime” artifact is `SKILL.md`: Claude Code reads the YAML frontmatter (metadata + allowed tools) and the prompt/instructions that follow.

`README.md` is for humans: installation, usage, and a compact overview of the patterns.

## Key files (and how they relate)
- `SKILL.md`
  - The actual skill definition and the lean operating core.
  - Starts with YAML frontmatter (`---` … `---`) containing `name`, `version`, `description`, and `allowed-tools`.
  - After the frontmatter: operating principles, a **compact 9-family index** (watch-words + one-line fixes), the checklists, scoring, and the multi-pass workflow. The detailed examples live in `reference/`, not here — keep this file lean (target under ~450 lines).
- `reference/` (loaded on demand by the skill)
  - `tell-catalog.md` — the full pattern library: every tell with watch-words and before/after, source-tagged. The index in `SKILL.md` points here by section (e.g. "§4.1").
  - `llm-artifacts.md` — deterministic detector for leaked tokens/placeholders, each with a regex plus a one-pass union sweep.
  - `worked-examples.md` — four full before → audit → after edits, including a restraint (don't-edit) case.
- `README.md`
  - Installation and usage instructions.
  - Contains the 9-family overview, a file-layout table, and the version history.

When changing behavior/content, treat `SKILL.md` as the source of truth. Add depth/examples to the matching `reference/` file (not into `SKILL.md`), and update `README.md` to stay consistent.

## Common commands
### Install the skill into Claude Code
Recommended (clone directly into Claude Code skills directory):
```bash
mkdir -p ~/.claude/skills
git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer
```

Manual install/update (only the skill file):
```bash
mkdir -p ~/.claude/skills/humanizer
cp SKILL.md ~/.claude/skills/humanizer/
```

## How to “run” it (Claude Code)
Invoke the skill:
- `/humanizer` then paste text

## Making changes safely
### Versioning (keep in sync)
- `SKILL.md` has a `version:` field in its YAML frontmatter.
- `README.md` has a “Version History” section.

If you bump the version, update both.

### Editing `SKILL.md`
- Preserve valid YAML frontmatter formatting and indentation.
- Keep the **family numbering** (1–9) and the `reference/tell-catalog.md` section numbers (e.g. §4.1) stable unless you’re intentionally re-numbering — the `SKILL.md` index, the README overview, and the catalog all cross-reference the same numbers.
- Add new tells/examples to the relevant `reference/` file; keep `SKILL.md` to the compact index entry only.

### Documenting non-obvious fixes
If you change the prompt to handle a tricky failure mode (e.g., a repeated mis-edit or an unexpected tone shift), add a short note to `README.md`’s version history describing what was fixed and why.