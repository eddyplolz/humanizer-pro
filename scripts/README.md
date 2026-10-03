# Humanizer Audit CLI

## Self-Scan

`self_scan.py` runs the audit over this repository's own documentation and gates the
exemption-adjusted score against `self_scan_budgets.json` (exit 1 on any file over budget or
missing a budget). Fenced code, inline code, tables, blockquotes, and quoted spans are exempt —
they are the quoted examples the docs exist to show. Run `py -3 scripts/self_scan.py` (POSIX:
`python3 scripts/self_scan.py`; add `--json` for JSON). Budgets are measured regression ceilings; lower them when a doc improves, and treat
raising one as a decision that belongs in a reviewed change.

## Corpus and Error-Rate Measurement

`corpus.py` builds and verifies the hash-only corpus described by `corpus/manifest.json`. Every
human document predates ChatGPT (cutoff 2022-11-01), so any audit flag on one is a false positive
by construction. Machine documents carry `label: machine` and the generating `model`. Every
document falls in a dev or test split derived from its digest (about a quarter dev); machine
entries record it as `split`, and `fp_measure.py` derives it for human entries.

The manifest holds register, author tier, date, word count, SHA-256 digest, and a public pointer
per document, and no text. Every pool comes from a public source, so anyone can rebuild it and
check the published numbers; every document comes from a public source. The text
lives in the gitignored `corpus/cache/` on the machine that built it.

| Pool | Register | Source | Rebuild |
|---|---|---|---|
| Strunk chunks | essay | the in-repo *Elements of Style* text | `build-pd` (offline) |
| Gutenberg works | essay | Emerson, Thoreau, Twain (public domain) | `build-essays` |
| Newspaper OCR | news | Internet Archive issues; OpenCulture US-PD-Newspapers pages | `build-news`, `build-hf-news` |
| Wikipedia articles | wiki | random English Wikipedia articles at their last pre-cutoff revision (CC BY-SA 4.0; pointer is the revision id) | `build-wikipedia` |
| Stack Exchange answers | chat | top-voted pre-cutoff answers from hobby, language, and workplace sites, code and quotes removed (CC BY-SA 4.0; pointer is the answer id) | `build-stackexchange` |
| PEPs | docs | Python Enhancement Proposals at the python/peps commit current at the cutoff (public domain; set `GITHUB_TOKEN` to raise the API rate limit) | `build-peps` |
| RAID | wiki, news, chat (machine) | RAID's non-adversarial training file, streamed (MIT; test labels are hidden) | `build-raid` |
| WildChat | chat (machine) | WildChat-1M first replies through the Hugging Face rows API (ODC-BY; set `HF_TOKEN` if the dataset asks you to accept its terms) | `build-wildchat` |

`scripts/generate_machine.py` can add a pool of current Claude models answering the prompts in
`corpus/machine_prompts.json`. It needs `pip install anthropic` and an API key, and it is never
run by default; the published numbers do not depend on it. `--dry-run` prints the request count,
and `--limit N` is a trial run that saves nothing.

A builder that collects nothing keeps the existing pool. The news builds are OCR-quality-gated and
retry rate limits. A Stack Exchange answer edited after the cutoff is dropped, like a post-cutoff
one, because the edited text is what the API returns. `fetch` restores the Strunk pool offline and
the Wikipedia and Stack Exchange pools by id, and names the `build-*` command for any other missing
kind. `verify` checks every cached file against its digest; a test enforces, kind by kind, that
every manifest entry carries only a public pointer.

Extraction versions are recorded per entry. `fetch` rebuilds Wikipedia entries with the extractor
named in their `extraction` field (`wikitext-strip.v1` stays byte-for-byte for old digests); new
builds use the current version. A Wikipedia entry is a whole article, bounded at 4,000 words, so
it is many editors' text.

`fp_measure.py` audits the cached corpus. On human test documents it prints false-positive rates
by register and author slice with Wilson 95% intervals, a review-threshold sweep, and the rules that
fire most often. On machine test documents it prints the catch rate with the same "flagged"
definition, by register and by model. A rule scorecard compares each rule's firing rate on human
dev and machine dev documents. Tune rules from the scorecard, never from test-split numbers. Results are published in `corpus/RESULTS.md`. The
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

Installed with `pipx install git+https://github.com/eddyplolz/humanizer-pro`, the same tool is the
`humanizer-audit` command. It takes several files or folders at once, writes SARIF 2.1.0 with
`--sarif PATH`, and keeps its prose rules out of fenced and inline code unless you pass
`--include-code`. Artifact rules always read the whole text. The repo also
ships a pre-commit hook (`.pre-commit-hooks.yaml`) and a GitHub Action (`action.yml`, input
`fail-on: block|review|never`); README.md shows both configurations.

## AI Check Workflows

Use the CLI for score-only "AI check," "score this," "audit only," and "do not rewrite" requests.
Return the risk score, pass/review/block status, blocker flags, tell-family hits, source-risk notes,
and brief quoted evidence. Do not rewrite the text unless the user separately asks.

The CLI is local and deterministic.

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
| 2 | Block: artifact, placeholder, citation stub, tracking URL, or bypass characters found. In `--compare` mode, any protected-content drift. |
| 3 | CLI usage or read error (argparse usage errors included). |

The default review threshold is `--fail-score 60`.

## JSON Output

`--json` emits schema `humanizer-audit.v1` with:

- `summary`: document count, max risk score, max severity, finding counts, and exit code.
- `documents[].stats`: rhythm and structure metrics, plus `type_token_ratio` and `mattr_50`
  (diagnostic only; `null` below 50 tokens; see `reference/mattr-calibration.md`).
- `documents[].findings`: family hits, source-risk flags, artifacts, severity, line/column, and
  quoted evidence.
- `compare.findings`: protected-content drift findings when `--compare` is used.

The schema is intentionally compact so it can be used in CI, pre-publish checks, or agent workflows.
