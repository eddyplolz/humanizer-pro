# Humanizer Audit CLI

## Self-Scan

`self_scan.py` runs the audit over this repository's own documentation and gates the
exemption-adjusted score against `self_scan_budgets.json` (exit 1 on any file over budget or
missing a budget). Fenced code, inline code, tables, blockquotes, and quoted spans are exempt —
they are the quoted examples the docs exist to show. Run `py -3 scripts/self_scan.py` (or with
`--json`). Budgets are measured regression ceilings; lower them when a doc improves, and treat
raising one as a decision that belongs in a reviewed change.

## Corpus and FP Measurement

`corpus.py` builds and verifies the hash-only human-control corpus described by
`corpus/manifest.json`. Every corpus document predates ChatGPT (cutoff 2022-11-01), so any audit
flag on one is a false positive by construction. The manifest is anonymous by design: it holds
register, author tier, date, word count, and SHA-256 digest per document — no text, no usernames,
no source locators. Entry ids derive from the digest, so they name content without describing it.
The text lives in the gitignored `corpus/cache/` and the source locators in the gitignored
`corpus/sources.local.json`; both stay on the maintainer's machine. The public-domain pools are
the exception: the in-repo Strunk chunks, the Gutenberg essay works (`build-essays`), and the
Internet Archive news chunks (`build-news`, OCR-quality-gated, rate-limit-aware) publish their
public-domain sources so those slices are independently rebuildable. `verify` checks every cached
file against its digest; a test enforces the anonymity contract on every entry.

`fp_measure.py` audits the cached corpus and prints false-positive rates by register and author
slice with Wilson 95% intervals, a review-threshold sweep, and the rules that fire most often on
human text. Results are published in `corpus/RESULTS.md`. It claims no true-positive rate: the
`--include-fixture-tp` flag audits this repo's own AI fixtures, but those tuned the rules, so that
readout is labeled anecdotal.

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
