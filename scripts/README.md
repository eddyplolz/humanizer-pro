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
by construction. Machine documents carry `label: machine`, the generating `model`, and a `split`
(`dev` or `test`) derived from the digest, so about a quarter are dev. The manifest is anonymous by design: it holds
register, author tier, date, word count, and SHA-256 digest per document — no text, no usernames,
no source locators. Entry ids derive from the digest, so they name content without describing it.
The text lives in the gitignored `corpus/cache/` and the source locators in the gitignored
`corpus/sources.local.json`; both stay on the maintainer's machine. The public-domain pools are
the exception: the in-repo Strunk chunks (`build-pd`, offline), the Gutenberg essay works
(`build-essays`), the Internet Archive news chunks (`build-news`), and the OpenCulture
US-PD-Newspapers pages (`build-hf-news`), and the PEPs (`build-peps`, read at the python/peps commit
current at the cutoff; set `GITHUB_TOKEN` to raise the API rate limit) publish their sources so
those slices can be rebuilt. The machine pools publish theirs too: `build-raid` streams RAID's
non-adversarial training file (MIT; its test labels are hidden), `build-wildchat` reads WildChat-1M
first replies through the Hugging Face rows API (ODC-BY; set `HF_TOKEN` if the dataset asks you to
accept its terms), and `scripts/generate_machine.py` asks current Claude models the prompts in
`corpus/machine_prompts.json`. That script needs `pip install anthropic` and an API key, uses no
refusal fallbacks so every label names the model that wrote the text, and replaces the generated
pool on each run (`--dry-run` prints the request count first). The news builds are OCR-quality-gated and retry rate limits. `fetch` restores the Strunk
pool and wiki revisions and names the `build-*` command for any other missing kind. `verify` checks every cached
file against its digest; a test enforces the anonymity contract on every entry.

Anonymity has one known limit. Full SHA-256 digests, the `maintainer` author tier, and the
deterministic extraction code are all public, so someone who already holds a candidate forum post
or wiki revision can extract and hash it and confirm that it is in the corpus. The manifest names
no one, but it can confirm a guess. Truncated or salted digests would close this and would also
end independent verification of the public-domain pools, so the trade-off is left to the
maintainer.

Extraction versions are recorded per entry. `fetch` rebuilds wiki entries with the extractor named
in their `extraction` field (`wikitext-strip.v1` stays byte-for-byte for existing digests); new
builds use the current version. A wiki entry is the whole page at the maintainer's last pre-cutoff
revision, so it can hold other editors' text.

`fp_measure.py` audits the cached corpus. On human documents it prints false-positive rates by
register and author slice with Wilson 95% intervals, a review-threshold sweep, and the rules that
fire most often. On machine documents it prints the catch rate, using the same "flagged" definition
on the test split only, by register and by model. It also prints a rule scorecard, built from the dev
split only, comparing each rule's human and machine firing rates. Tune rules from the scorecard,
never from test-split numbers. Results are published in `corpus/RESULTS.md`. The
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
`--sarif PATH`, and skips fenced and inline code unless you pass `--include-code`. The repo also
ships a pre-commit hook (`.pre-commit-hooks.yaml`) and a GitHub Action (`action.yml`, input
`fail-on: block|review|never`); README.md shows both configurations.

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
