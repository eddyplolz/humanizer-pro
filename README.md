# Humanizer Pro

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

`scripts/humanizer_audit.py` is a single-file Python tool with no dependencies. It reads text, reports problems with line numbers and quoted evidence, and exits with a code your scripts can branch on. It never rewrites anything.

To score one file:

Windows:

```bat
py -3 scripts\humanizer_audit.py path\to\draft.md
```

Mac or Linux:

```bash
python3 scripts/humanizer_audit.py path/to/draft.md
```

Useful variations:

1. Point it at a folder and it audits every `.md` and `.txt` inside, recursively.
2. Add `--json` for machine-readable output (schema `humanizer-audit.v1`).
3. Run `--compare original.md revised.md` to check that a rewrite kept its facts: numbers, dates, names, link targets, citations, quotes, and code blocks. Compare mode judges fidelity only, never style.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Pass. |
| 1 | Review. The risk score reached the threshold (default 60; change it with `--fail-score`). |
| 2 | Block. A hard artifact was found: leaked AI tokens, placeholder text, invisible characters. |
| 3 | Usage or read error. |

In CI, treat 1 as "a human should look at this" and 2 as "do not ship."

## How it decides

Nine families of tells, learned from real cleanup work on Wikipedia and elsewhere. Three examples give the flavor:

- Significance inflation: "stands as a testament," "pivotal moment," brochure tone where plain description belongs.
- Rhetorical formulas: "not just X, but Y," forced rules of three, the fortune-cookie closing line.
- Chatbot residue: "I hope this helps," knowledge-cutoff disclaimers, leaked citation stubs like `oaicite`, tracking links from AI browsers.

All nine families, with watch-words and before/after examples, live in [`reference/tell-catalog.md`](reference/tell-catalog.md).

Two principles steer every edit. Density beats single instances: one "crucial" is a coincidence, a cluster is a tell. And restraint is scored: an edit that flattens working prose counts as a miss, and the fix is to put the original back.

Strictness also adapts to what you are writing. A chat message, an essay, a news piece, and an encyclopedia article are held to different bars ([`reference/registers.md`](reference/registers.md)).

## The evidence

Claims about false positives get measured here, not asserted. The repo carries a hash-only corpus of 2,151 human documents, all written before ChatGPT existed, so any flag on one is a false positive by construction. Rates at the default threshold ([full table and method](corpus/RESULTS.md)):

| Register | False-positive rate |
|---|---|
| Chat (forum posts) | 0.0% |
| Essays | 0.0% |
| News (1900–1922 newspapers) | 0.0% |
| Encyclopedia articles | 1.5% |

The corpus publishes digests, dates, and word counts, never text, names, or source locations. No true-positive rate is claimed: there is no machine-generated corpus here yet, and honest numbers beat impressive ones.

The repo also eats its own cooking. `scripts/self_scan.py` audits these very docs against recorded budgets, and both the raw and the exemption-adjusted scores are published on purpose: the raw number counts every tell this README quotes in order to warn you about it, and showing only the flattering column is the exact behavior this project exists to criticize.

## Project layout

| Path | What it is |
|---|---|
| `SKILL.md` | The skill's operating core: routing, principles, checklists, scoring. |
| `reference/` | The deep material: full tell catalog, worked examples, style and wiki guides, register profiles, improvement loop. |
| `scripts/humanizer_audit.py` | The audit and compare CLI. |
| `scripts/self_scan.py` | Audits this repo's own docs against recorded budgets. |
| `scripts/corpus.py` and `scripts/fp_measure.py` | Build the human-control corpus and measure false-positive rates. |
| `corpus/` | Hash-only corpus manifest and measured results. |
| `eval/` | Fixtures and machine-readable expectations for the CLI. |
| `tests/` | Pytest suite for the CLI. |
| `agents/openai.yaml` | Codex-facing name, description, and default prompt. |

## Contributing

New rules enter through a review loop, not a hot take: Observation, then Candidate, Fixture, Review, Promotion, and a Regression check. A candidate is rejected if it encourages over-editing, duplicates an existing rule, encodes one person's taste, or needs more than about 80 words to state. Details in [`reference/improvement-loop.md`](reference/improvement-loop.md).

Before a pull request, run the checks:

1. `py -3 -m pytest -q tests` (Mac or Linux: `python3 -m pytest -q tests`). Everything should pass.
2. `py -3 scripts/self_scan.py`. It should exit 0.

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

## Version history

Current release: **v4.10.1**, this plain-language README. Just before it, v4.10.0 recalibrated the wiki register: wiki false positives fell from 9.1% to 1.5%, with every other register unchanged. The full history back to 1.0.0 is in [CHANGELOG.md](CHANGELOG.md).
