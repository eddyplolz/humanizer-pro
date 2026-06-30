# Humanizer Audit CLI

`humanizer-audit` is a deterministic, zero-dependency companion to Humanizer Pro. It audits text; it
does not rewrite it.

## Usage

Windows:

```bat
py -3 scripts\humanizer_audit.py eval\fixtures\ai-slop-general.md
py -3 scripts\humanizer_audit.py eval\fixtures --json
type draft.md | py -3 scripts\humanizer_audit.py --stdin --json
py -3 scripts\humanizer_audit.py --compare original.md revised.md --json
```

POSIX:

```bash
python3 scripts/humanizer_audit.py eval/fixtures/ai-slop-general.md
python3 scripts/humanizer_audit.py eval/fixtures --json
cat draft.md | python3 scripts/humanizer_audit.py --stdin --json
python3 scripts/humanizer_audit.py --compare original.md revised.md --json
```

## AI Check Workflows

Use the CLI for score-only "AI check," "score this," "audit only," and "do not rewrite" requests.
Return the risk score, pass/review/block status, blocker flags, tell-family hits, source-risk notes,
and brief quoted evidence. Do not rewrite the text unless the user separately asks.

The CLI is local and deterministic. It does not call detector APIs, make detector-bypass claims, or
support optimize-until-green loops.

## Compare Mode

`--compare original.md revised.md` checks protected-content fidelity only. It does not score style or
tell families. It flags drift in numbers, dates, names, URL targets, citation markers, quoted text,
fenced code blocks, and source-dependent sentences whose evidence markers were dropped.

URL comparison normalizes tracking parameters such as `utm_source`, so removing tracking noise from an
otherwise identical source URL is not treated as drift.

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
- `compare.findings`: protected-content drift findings when `--compare` is used.

The schema is intentionally compact so it can be used in CI, pre-publish checks, or agent workflows.
