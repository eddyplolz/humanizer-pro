# Humanizer Audit CLI

`humanizer-audit` is a deterministic, zero-dependency companion to Humanizer Pro. It audits text; it
does not rewrite it.

## Usage

```bash
py -3 scripts/humanizer_audit.py eval/fixtures/ai-slop-general.md
py -3 scripts/humanizer_audit.py eval/fixtures --json
type draft.md | py -3 scripts/humanizer_audit.py --stdin --json
```

Use `python3` instead of `py -3` on POSIX systems.

## Exit Codes

| Code | Meaning |
|---:|---|
| 0 | Pass: no blocker and risk score is below the threshold. |
| 1 | Review: no blocker, but the risk score met or exceeded `--fail-score`. |
| 2 | Block: artifact, placeholder, citation stub, or tracking URL found. |
| 3 | CLI usage or read error. |

The default review threshold is `--fail-score 60`.

## JSON Output

`--json` emits schema `humanizer-audit.v1` with:

- `summary`: document count, max risk score, max severity, finding counts, and exit code.
- `documents[].stats`: rhythm and structure metrics.
- `documents[].findings`: family hits, source-risk flags, artifacts, severity, line/column, and
  quoted evidence.

The schema is intentionally compact so it can be used in CI, pre-publish checks, or agent workflows.

