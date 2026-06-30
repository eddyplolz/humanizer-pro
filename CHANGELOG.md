# Changelog

## Unreleased

- Added score-only AI check mode documentation for "check this," "score this," "audit only," and
  "do not rewrite" workflows.
- Documented Claude Code installs to `~/.claude/skills/humanizer-pro`, Codex/generic agent installs
  to `~/.agents/skills/humanizer-pro`, and Windows/POSIX audit CLI examples.
- Added `--compare original.md revised.md` fidelity guards for protected-content drift in numbers,
  dates, names, URLs, citations, quotes, fenced code blocks, and source-dependent statements.

## 4.2.0 - 2026-06-30

- Added the deterministic `humanizer-audit` CLI for artifact sweeps, tell-family hits, source-risk
  flags, rhythm/structure stats, JSON output, and threshold exit codes.
- Added automated scenario-contract tests for the existing Humanizer Pro fixtures.
