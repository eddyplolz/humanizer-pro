# Humanizer Pro

[![CI](https://github.com/eddyplolz/humanizer-pro/actions/workflows/ci.yml/badge.svg)](https://github.com/eddyplolz/humanizer-pro/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

AI drafts have habits. "In today's rapidly evolving landscape." A bold list where every line starts the same way. A "crucial" every third paragraph. Readers notice, and once they notice, they stop trusting the text.

Humanizer Pro finds those habits and removes them without touching the writing that was already good. It runs as a skill inside Claude Code, Codex, and similar coding agents, and it includes a small Python tool that scores any text file from your terminal. Everything runs on your machine. No accounts, no API keys, no network calls.

It will not help you fool AI detectors, and it will not bolt a fake personality onto your prose. It makes writing plainer, calmer, and easier to trust. That is the whole job.

*A standalone rebuild of [blader/humanizer](https://github.com/blader/humanizer) (MIT). See [Credits and licensing](#credits-and-licensing).*

## See it work

**Before**

> In today's rapidly evolving digital landscape, effective collaboration serves as a crucial cornerstone for organizations seeking to unlock their full potential. It is important to note that this approach is not just about tools, but about creating a vibrant culture of innovation.

**After**

> Good collaboration depends less on the tool than on whether people know what decisions they own, where work is tracked, and how quickly blockers get resolved.

The first version performs. The second one says something.

The terminal checker explains the first version line by line (abridged):

```text
$ humanizer-audit eval/fixtures/ai-slop-general.md
eval/fixtures/ai-slop-general.md — risk 60
  WARNING L3:C1 family3.filler_framing — Filler framing or superficial analysis [In today's]
  WARNING L3:C37 family4.ai_vocab_cluster — AI-vocabulary cluster [cornerstone, crucial, enhance, foster, landscape, robust, unlock, vibrant]
  WARNING L6:C29 family5.syntactic_tell — Syntactic tell or hedged construction [It is important to note]
  WARNING L6:C75 family7.rhetorical_formula — Rhetorical formula or forced cadence [not just about tools, but]
  WARNING L7:C80 family3.filler_framing — Filler framing or superficial analysis [In conclusion]
```

## Measured both ways

This project publishes its error rates in both directions, with 95% intervals and the method: how often it flags human writing, and how often it catches AI writing.

| Direction | Corpus | Result |
|---|---|---|
| Flags human writing | 2,145 documents written before ChatGPT (chat, wiki, news, essays) | 0.0% to 1.5% by register at the default threshold. Measured on 4.12.0; rerun pending ([table](corpus/RESULTS.md)). |
| Catches AI writing | Held-out test split of RAID, WildChat, and current Claude models | Not measured yet. The builders ship in 4.14.0; the first run is pending. |

Both numbers come from `scripts/fp_measure.py`, and the method is in [The evidence](#the-evidence). A rule earns its place only if it fires more on AI text than on human text, and that comparison uses a separate dev split so the published catch rate stays honest.

## What it will not do

Three refusals are built in on purpose:

- It does not try to beat AI detectors. No invisible characters, no synonym tricks, no "undetectable" claims.
- Fake voice is treated as a defect, not a fix. Swapping "Moreover" for "Here's the thing" trades one tell for another, and the skill refuses both.
- Over-editing counts as a failure. A restraint check protects clean human prose, so a draft that was fine comes back close to untouched.

One warning in the other direction. A high score is a signal about writing habits, not proof that a machine wrote the text, and never proof about a person. Independent research reports detector false-positive rates above 60% for people writing in English as a second language (Liang et al., Stanford, *Patterns* 2023). Do not use this tool's output as the only basis for an academic, hiring, or attribution decision.

## Get started in 2 minutes

You need git. If you also want the terminal checker, you need Python 3.10 or newer. That is the full list.

### Install for Claude Code

Mac or Linux:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

Windows:

```bat
mkdir "%USERPROFILE%\.claude\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.claude\skills\humanizer-pro"
```

To confirm it worked, open the folder and check that `SKILL.md` is there. Claude Code picks the skill up on its next session as `/humanizer-pro`.

### Install for Codex and other agents

Mac or Linux:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.agents/skills/humanizer-pro
```

Windows:

```bat
mkdir "%USERPROFILE%\.agents\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.agents\skills\humanizer-pro"
```

Codex users: if `CODEX_HOME` is set, use `$CODEX_HOME/skills` instead; otherwise `~/.codex/skills` also works. The repo ships `agents/openai.yaml`, so Codex shows a friendly name and a ready-made `$humanizer-pro` prompt.

### Your first three asks

Paste your text after any of these:

1. `Humanize this:` cleans the draft and returns it.
2. `Check this for AI tells. Do not rewrite it.` scores and explains, changes nothing.
3. `Full audit:` scores it, names each problem, then shows the rewrite.

## Everyday use

The skill routes itself by how you phrase the request. Plain words work; there is no command syntax to learn.

| If you want | Say something like |
|---|---|
| A cleaned-up draft | "Humanize this" or "make this less AI" |
| A score and reasons, no changes | "AI check," "score this," or "do not rewrite" |
| The full treatment | "Full audit" |
| Tighter sentences | "Style edit" or "tighten this" |
| Neutral encyclopedia prose | "Wiki mode," or just mention wikitext or citations |

Details worth knowing:

- The full audit scores six dimensions (directness, rhythm, trust, authenticity, density, restraint) and shows its reasoning before the rewrite.
- Wiki mode neutralizes promotional tone, keeps citations intact, and flags unsupported claims instead of smoothing them over.
- Style edits use a compact Elements of Style checklist. The complete 1918 Strunk text ships in the repo and loads only when you ask for it.
- The skill quietly audits its own drafts before handing them to you.

## The audit command

This section is for people who want checks in scripts, CI, or the terminal. You do not need it to use the skill.

`humanizer-audit` is a single-file Python tool with no dependencies. It reads text, reports problems with line numbers and quoted evidence, and exits with a code your scripts can branch on. It never rewrites anything.

Install it as a command (Python 3.10 or newer):

```bash
pipx install git+https://github.com/eddyplolz/humanizer-pro
humanizer-audit path/to/draft.md
```

Or run it from a clone without installing anything:

Windows:

```bat
py -3 scripts\humanizer_audit.py path\to\draft.md
```

Mac or Linux:

```bash
python3 scripts/humanizer_audit.py path/to/draft.md
```

Useful variations:

1. Pass several files or folders; a folder means every `.md` and `.txt` inside, recursively.
2. Add `--json` for machine-readable output (schema `humanizer-audit.v1`).
3. Add `--sarif out.sarif` to also write SARIF 2.1.0, which GitHub code scanning shows as annotations on pull requests.
4. Code is skipped by default: `utilize()` inside backticks is an API name, not wordiness. Add `--include-code` to check code too.
5. Run `--compare original.md revised.md` to check that a rewrite kept its facts: numbers, dates, names, link targets, citations, quotes, and code blocks. Compare mode judges fidelity only, never style.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Pass. |
| 1 | Review. The risk score reached the threshold (default 60; change it with `--fail-score`). |
| 2 | Block. A hard artifact was found: leaked AI tokens, placeholder text, invisible characters. |
| 3 | Usage or read error. |

In CI, treat 1 as "a human should look at this" and 2 as "do not ship."

### In pre-commit

```yaml
repos:
  - repo: https://github.com/eddyplolz/humanizer-pro
    rev: main  # pin a release tag or commit once you adopt it
    hooks:
      - id: humanizer-audit
```

### In GitHub Actions

```yaml
permissions:
  contents: read
  security-events: write  # for the SARIF upload
steps:
  - uses: actions/checkout@v4
  - id: audit
    uses: eddyplolz/humanizer-pro@main  # pin a release tag or commit
    with:
      paths: docs README.md
      fail-on: block  # block | review | never
  - uses: github/codeql-action/upload-sarif@v3
    if: always()
    with:
      sarif_file: humanizer-audit.sarif
```

The action needs Python 3 on the runner; GitHub's Ubuntu and macOS runners have it.

## How it decides

Nine families of tells, learned from real cleanup work on Wikipedia and elsewhere. Three examples give the flavor:

- Significance inflation: "stands as a testament," "pivotal moment," brochure tone where plain description belongs.
- Rhetorical formulas: "not just X, but Y," forced rules of three, the fortune-cookie closing line.
- Chatbot residue: "I hope this helps," knowledge-cutoff disclaimers, leaked citation stubs like `oaicite`, tracking links from AI browsers.

All nine families, with watch-words and before/after examples, live in [`reference/tell-catalog.md`](reference/tell-catalog.md).

Two principles steer every edit. Density beats single instances: one "crucial" is a coincidence, a cluster is a tell. And restraint is scored: an edit that flattens working prose counts as a miss, and the fix is to put the original back.

Strictness also adapts to what you are writing. A chat message, an essay, a news piece, and an encyclopedia article are held to different bars ([`reference/registers.md`](reference/registers.md)).

## The evidence

Error rates get measured here, not asserted.

**False positives.** The repo carries a hash-only corpus of 2,145 human documents, all written before ChatGPT existed, so any flag on one is a false positive by construction. Rates at the default threshold, measured on the 1,912 documents cached at the time (news n=261) and before the 4.13.0 fixes ([full table and method](corpus/RESULTS.md)):

| Register | False-positive rate |
|---|---|
| Chat (forum posts) | 0.0% (plus 1 of 764 blocked; see note) |
| Essays | 0.0% |
| News (1898–1928 newspapers) | 0.0% |
| Encyclopedia articles | 1.5% |

Note: these rates count reviews (exit 1) only. One human chat post was blocked (exit 2); from 4.13.0, `fp_measure.py` counts a block as a false positive, so the next measurement will show it. The corpus publishes digests, dates, and word counts, never text, names, or source locations.

**Catch rate.** From 4.14.0 the corpus also takes machine-written documents, labelled by source: generations from [RAID](https://github.com/liamdugan/raid) (2023 models, non-adversarial), first replies from [WildChat](https://huggingface.co/datasets/allenai/WildChat-1M) (GPT-3.5 and GPT-4), and current Claude models answering [60 committed prompts](corpus/machine_prompts.json). About a quarter of them form a dev split. That split is the only one rule tuning may look at, through a per-rule scorecard. The published catch rate uses the remaining test split, with the same "flagged" definition as the false-positive rate. The first full run is pending, so no catch rate is claimed yet. Two caveats will travel with the number: it describes those models only, and human essays and news in the corpus are a century old, so a gap there is partly era.

A docs register joins the human side too: Python Enhancement Proposals read at the last commit before the cutoff.

The repo also eats its own cooking. `scripts/self_scan.py` audits these very docs against recorded budgets, and both the raw and the exemption-adjusted scores are published on purpose: the raw number counts every tell this README quotes in order to warn you about it, and showing only the flattering column is the exact behavior this project exists to criticize.

## Project layout

| Path | What it is |
|---|---|
| `SKILL.md` | The skill's operating core: routing, principles, checklists, scoring. |
| `reference/` | The deep material: full tell catalog, artifact detector, AI-check mode, worked examples, style and wiki guides, register profiles, coverage map, MATTR calibration, improvement loop. |
| `scripts/humanizer_audit.py` | The audit and compare CLI. |
| `scripts/self_scan.py` | Audits this repo's own docs against recorded budgets. |
| `scripts/corpus.py` and `scripts/fp_measure.py` | Build the corpus and measure false-positive and catch rates. |
| `scripts/generate_machine.py` | Maintainer tool: current-model machine text for the catch rate (needs the `anthropic` SDK and an API key). |
| `corpus/` | Hash-only corpus manifest, generation prompts, and measured results. |
| `pyproject.toml`, `action.yml`, `.pre-commit-hooks.yaml` | Packaging, the GitHub Action, and the pre-commit hook. |
| `eval/` | Fixtures and machine-readable expectations for the CLI. |
| `tests/` | Pytest suite for the CLI, compare mode, and corpus tools. |
| `CHANGELOG.md` | Full release history. |
| `WARP.md` | Maintainer guide: file roles, commands, change rules. |
| `agents/openai.yaml` | Codex-facing name, description, and default prompt. |

## Contributing

New rules enter through a review loop, not a hot take: Observation, then Candidate, Fixture, Review, Promotion, and a Regression check. A candidate is rejected if it encourages over-editing, duplicates an existing rule, encodes one person's taste, or needs more than about 80 words to state. Details in [`reference/improvement-loop.md`](reference/improvement-loop.md).

Before a pull request, run the checks:

1. `py -3 -m pytest -q tests` (Mac or Linux: `python3 -m pytest -q tests`). Everything should pass.
2. `py -3 scripts/self_scan.py` (Mac or Linux: `python3 scripts/self_scan.py`). It should exit 0.

## Credits and licensing

This project is released under the [MIT License](LICENSE).

It is a standalone rebuild of [**blader/humanizer**](https://github.com/blader/humanizer) by Siqi Chen
(MIT, Copyright (c) 2025), re-architected into a lean core plus a nine-family reference library and
extended with new layers for syntactic tells, verbosity, deterministic artifact detection, wiki/source
discipline, style editing, and the over-humanizing paradox. The `LICENSE` file carries both the
original and new copyright.

Pattern sources, with thanks:

- **[blader/humanizer](https://github.com/blader/humanizer)** by Siqi Chen - MIT.
- **[Stop Slop](https://github.com/hardikpandya/stop-slop)** by Hardik Pandya - MIT.
- **[avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing)** by Conor Bronsdon - MIT.
  Source of the vocabulary tiering, register-strictness, coverage-map, self-scan, and
  corpus/FP-measurement designs adopted in v4.3.0-v4.7.0.
- **[humanize](https://github.com/harshaneel/humanize)** by Harshaneel Gokhale - MIT. Source of the
  countable rhythm proxies, the written-counts gate, several rhetorical-scaffolding patterns
  (§7.12-7.15), and the RLHF helpful-assistant framing entry (§9.11) adopted in v4.8.0. Its
  detector-evasion techniques were deliberately not adopted.
- **[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**
  (WikiProject AI Cleanup) - available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- **[Project Gutenberg #37134](https://www.gutenberg.org/ebooks/37134)** - source for William Strunk
  Jr.'s public-domain *The Elements of Style* text.
- **[OpenCulture / US-PD-Newspapers](https://huggingface.co/datasets/PleIAs/US-PD-Newspapers)** by
  PleIAs - public-domain newspaper text used (hash-only) in the human-control corpus's news pool.
- **[RAID](https://github.com/liamdugan/raid)** by Dugan et al. (ACL 2024) - MIT. Machine-text pool.
- **[WildChat-1M](https://huggingface.co/datasets/allenai/WildChat-1M)** by Ai2 - ODC-BY. Machine-text
  pool.
- **[Python Enhancement Proposals](https://github.com/python/peps)** - public domain. Docs-register
  human pool.

## Version history

Current release: **v4.14.0**. It measures in both directions: the corpus takes labelled machine text with a held-out test split, and `fp_measure.py` reports a catch rate next to the false-positive rate, plus a per-rule scorecard. The audit installs as a command, runs as a pre-commit hook or a GitHub Action, writes SARIF for code scanning, and skips code by default. v4.13.0 before it was a bug-fix release from a full-repo review. The full history back to 1.0.0 is in [CHANGELOG.md](CHANGELOG.md).
