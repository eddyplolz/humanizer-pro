# Humanizer Pro

[![CI](https://github.com/eddyplolz/humanizer-pro/actions/workflows/ci.yml/badge.svg)](https://github.com/eddyplolz/humanizer-pro/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

Humanizer Pro finds the habits that make writing sound machine-made and removes them. It leaves good writing alone.

You can use it in 3 ways:

- as a skill inside Claude Code, Codex, and similar coding agents
- as a command that checks text files on your computer
- as an automatic check in Git or GitHub Actions

It runs on your computer. It does not need an account, an API key, or a network connection.

## Contents

1. [What it does](#what-it-does)
2. [What it does not do](#what-it-does-not-do)
3. [Your privacy](#your-privacy)
4. [Install the skill](#install-the-skill)
5. [Use the skill](#use-the-skill)
6. [Check files from the command line](#check-files-from-the-command-line)
7. [Check files automatically](#check-files-automatically)
8. [How well it works](#how-well-it-works)
9. [How it decides](#how-it-decides)
10. [Help improve it](#help-improve-it)
11. [Credits and license](#credits-and-license)
12. [Version history](#version-history)

## What it does

AI drafts repeat the same habits: stock phrases, inflated importance, and filler that sounds complete but says little. Readers notice, and then they stop trusting the text.

Humanizer Pro:

- finds those habits and explains each one
- rewrites the draft in plain language, if you ask it to
- checks that a rewrite kept the numbers, dates, full names, links, and quotes it can detect
- flags text that a chatbot left behind, such as citation codes and placeholder fields

Here is an example.

Before:

> In today's rapidly evolving digital landscape, effective collaboration serves as a crucial cornerstone for organizations seeking to unlock their full potential. It is important to note that this approach is not just about tools, but about creating a vibrant culture of innovation.

After:

> Good collaboration depends less on the tool than on whether people know what decisions they own, where work is tracked, and how quickly blockers get resolved.

The command-line checker explains the first version line by line (shortened):

```text
$ humanizer-audit eval/fixtures/ai-slop-general.md
eval/fixtures/ai-slop-general.md — risk 60
  WARNING L3:C1 family3.filler_framing — Filler framing or superficial analysis [In today's]
  WARNING L3:C37 family4.ai_vocab_cluster — AI-vocabulary cluster [cornerstone, crucial, enhance, foster, landscape, robust, unlock, vibrant]
  WARNING L6:C29 family5.syntactic_tell — Syntactic tell or hedged construction [It is important to note]
  WARNING L6:C75 family7.rhetorical_formula — Rhetorical formula or forced cadence [not just about tools, but]
  WARNING L7:C80 family3.filler_framing — Filler framing or superficial analysis [In conclusion]
```

## What it does not do

This project makes no claims about AI detectors.

It does not add a fake personality. Swapping one stock phrase for a casual one trades one habit for another, so the skill avoids both.

It does not rewrite text that is already clean. A built-in restraint check returns good writing close to how it arrived.

> [!IMPORTANT]
> A high score shows writing habits. It does not prove that a machine wrote the text, and it proves nothing about a person. Research has found that AI detectors wrongly flag more than 60% of essays by people writing in English as a second language (Liang et al., Stanford, *Patterns*, 2023). Do not use this tool as the only basis for an academic, hiring, or authorship decision.

## Your privacy

The command-line checker reads files on your computer and sends nothing anywhere. It makes no network connections and keeps no logs.

The skill runs inside your coding agent, such as Claude Code or Codex. Your text goes wherever your agent already sends it, and nowhere else.

Two features can put your text somewhere else, and only when you choose them:

- SARIF results contain short quotes from your text. If you upload them to GitHub code scanning, those quotes are stored with your repository's code scanning results.
- The GitHub Action runs in your own GitHub Actions workflow, so your files are read on GitHub's servers, as with any other check you run there.

## Install the skill

### Before you start

You need [git](https://git-scm.com/downloads). To use the command-line checker as well, you also need [Python](https://www.python.org/downloads/) 3.10 or newer.

### Install for Claude Code

On a Mac or Linux computer, run these commands in Terminal:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.claude/skills/humanizer-pro
```

On Windows, run these commands in Command Prompt:

```bat
mkdir "%USERPROFILE%\.claude\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.claude\skills\humanizer-pro"
```

To check it worked, open the new `humanizer-pro` folder and look for a file called `SKILL.md`. Claude Code loads the skill the next time you start it. You can then type `/humanizer-pro`.

### Install for Codex and other agents

On a Mac or Linux computer:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/eddyplolz/humanizer-pro.git ~/.agents/skills/humanizer-pro
```

On Windows:

```bat
mkdir "%USERPROFILE%\.agents\skills"
git clone https://github.com/eddyplolz/humanizer-pro.git "%USERPROFILE%\.agents\skills\humanizer-pro"
```

If you use Codex and have set `CODEX_HOME`, install into `$CODEX_HOME/skills` instead. Otherwise `~/.codex/skills` also works.

## Use the skill

Paste your text after a request in plain words. You do not need to learn any commands.

| What you want | What to say |
|---|---|
| A cleaned-up draft | "Humanize this" or "make this less AI" |
| A score and reasons, with no changes | "AI check," "score this," or "do not rewrite" |
| A score, reasons, and a rewrite | "Full audit" |
| Tighter sentences | "Style edit" or "tighten this" |
| Neutral, encyclopedia-style writing | "Wiki mode," or mention wikitext or citations |

The full audit rates the draft on 6 qualities: directness, rhythm, trust, authenticity, density, and restraint. It shows its reasoning before the rewrite.

Wiki mode removes promotional tone, keeps citations, and flags claims that have no source.

Style edits use a short checklist based on *The Elements of Style*. The full 1918 text is included, and the skill only loads it when you ask.

## Check files from the command line

The checker reads text files and lists each problem with its line number and the words that triggered it. It never changes your files.

### Install the checker

Install it with [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/eddyplolz/humanizer-pro
```

You can also run it from a downloaded copy of this repository, without installing anything:

```bash
python3 scripts/humanizer_audit.py path/to/draft.md
```

On Windows, use `py -3` instead of `python3`.

### Check a file

```bash
humanizer-audit path/to/draft.md
```

You can:

- check several files or folders at once (a folder means every `.md` and `.txt` file inside it)
- add `--json` to get results a program can read
- add `--sarif results.sarif` to save results in SARIF, the format GitHub uses to show problems on pull requests
- add `--include-code` to check code samples as well (they are skipped by default, but leaked chatbot text inside code is always caught)
- use `--compare original.md revised.md` to check that a rewrite kept the numbers, dates, names of 2 or more words, links, citations, quotes, and code samples in the original (it does not catch every change: a one-word name or a changed fact, such as "delayed" becoming "canceled," can pass)

### Understand the result

The checker ends with an exit code that scripts can act on.

| Code | Meaning | What to do |
|---|---|---|
| 0 | Pass | Nothing. |
| 1 | Review: the risk score reached the threshold (60 unless you set `--fail-score`) | Read the findings and decide. |
| 2 | Block: leaked chatbot text, a placeholder, or hidden characters | Fix before you publish. |
| 3 | The checker could not run, for example a wrong option or a missing file | Check the command. |

## Check files automatically

### Before each commit

[pre-commit](https://pre-commit.com/) is a tool that runs checks every time you commit. To add this check, put the following in a file called `.pre-commit-config.yaml` at the top of your project:

```yaml
repos:
  - repo: https://github.com/eddyplolz/humanizer-pro
    rev: v4.14.0
    hooks:
      - id: humanizer-audit
```

The check runs on Markdown and text files. A review or block result stops the commit.

### In GitHub Actions

This repository is also a GitHub Action. To check your writing on every pull request:

1. In your project, create the file `.github/workflows/writing.yml`.
2. Paste in the workflow below.
3. Change `paths` to the files or folders you want checked.
4. Commit the file.

```yaml
name: Writing check
on: pull_request

permissions:
  contents: read
  security-events: write  # needed to show results on the pull request

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: eddyplolz/humanizer-pro@v4.14.0
        with:
          paths: docs README.md
          fail-on: block
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: humanizer-audit.sarif
```

The last step shows each finding on the pull request, next to the line it refers to.

You can set these options:

| Option | What it does | Default |
|---|---|---|
| `paths` | Files or folders to check, separated by spaces or new lines | `.` (everything) |
| `fail-on` | When the step fails: `block`, `review`, or `never` | `block` |
| `fail-score` | Risk score that counts as a review | `60` |
| `sarif-file` | Where to save the SARIF results (leave empty to skip) | `humanizer-audit.sarif` |
| `include-code` | Set to `true` to check code samples too | `false` |

The action needs Python 3 on the runner. GitHub's Ubuntu and macOS runners have it.

## How well it works

This project measures its error rates instead of only describing them. It counts errors in both directions:

- false positives: how often it flags writing by people
- catch rate: how often it flags writing by AI

| What is measured | Writing used | Result |
|---|---|---|
| False positives | 2,145 documents written before ChatGPT existed: forum posts, encyclopedia articles, newspapers, and essays | 0.0% to 1.5%, depending on the type of writing ([full results](corpus/RESULTS.md)) |
| Catch rate | Writing from 2023 AI models, real ChatGPT replies, and current Claude models | Not measured yet |

### False positives

Every document in the human set was written before ChatGPT was released, so any flag on one is a mistake by definition. The latest rates, at the default threshold, are:

| Type of writing | False-positive rate |
|---|---|
| Forum posts | 0.0%, plus 1 post of 764 blocked |
| Essays | 0.0% |
| Newspapers (1898 to 1928) | 0.0% |
| Encyclopedia articles | 1.5% |

These rates come from version 4.12.0 and cover the 1,912 documents that were available then, including 261 newspaper pages. Later versions count a block as a false positive and change some rules. The next measurement will replace this table.

For documents from public sources, such as old books and newspapers, the project publishes a fingerprint of each one (a unique code), with its date and word count, so anyone can check them. For the forum and encyclopedia pools it publishes totals only. The project never publishes the text, an author's name, or where a document came from.

### Catch rate

From version 4.14.0, the collection also includes writing by AI, labeled by its source:

- text from [RAID](https://github.com/liamdugan/raid), a research benchmark of 2023 AI models
- first replies from [WildChat](https://huggingface.co/datasets/allenai/WildChat-1M), a public collection of real ChatGPT conversations
- answers from current Claude models to [60 published prompts](corpus/machine_prompts.json)

The catch rate has not been measured yet. When it is, 2 limits will apply:

- it describes those AI models only
- the human essays and newspapers are about 100 years old, so part of any gap there reflects the era, not the author

### How the results stay honest

Every document goes into one of 2 groups, chosen by its fingerprint. About a quarter go into a tuning group, and the rest into a test group.

Rules are adjusted using the tuning group only. Both published rates use the test group only. A rule cannot be tuned to make its own results look better.

This project also checks its own documentation with the same rules, using `scripts/self_scan.py`. It publishes 2 scores: one that counts every phrase this page quotes as a bad example, and one that leaves quotes and code out.

## How it decides

The checker looks for 9 families of habits, learned from cleanup work on Wikipedia and elsewhere. For example:

- inflated importance, such as "stands as a testament" or "pivotal moment"
- stock rhetorical patterns, such as "not just X, but Y" or lists that always come in threes
- text left behind by a chatbot, such as "I hope this helps," knowledge-cutoff notes, or citation codes like `oaicite`

The full list, with examples, is in the [catalog of habits](reference/tell-catalog.md).

2 principles guide every edit:

- a single instance proves nothing (one "crucial" is a coincidence, but a cluster is a pattern)
- over-editing is a failure (if a change makes good writing worse, the original goes back)

The checker is stricter for some kinds of writing than others. A chat message, an essay, a news story, and an encyclopedia article each have their own [rules for strictness](reference/registers.md).

## Help improve it

New rules go through a review process before they are added. A proposed rule is rejected if it:

- encourages over-editing
- repeats an existing rule
- reflects one person's taste
- takes more than about 80 words to state

The full process is in the [improvement guide](reference/improvement-loop.md).

Before you open a pull request, run these 2 checks. Both must pass.

```bash
python3 -m pytest -q tests
python3 scripts/self_scan.py
```

On Windows, use `py -3` instead of `python3`.

<details>
<summary>What each file and folder is for</summary>

| Path | What it is |
|---|---|
| `SKILL.md` | The skill itself: routing, principles, checklists, and scoring |
| `reference/` | Detailed guides: the catalog of habits, worked examples, style and wiki guides, strictness rules, and the improvement process |
| `scripts/humanizer_audit.py` | The checker |
| `scripts/self_scan.py` | Checks this project's own documentation |
| `scripts/corpus.py`, `scripts/fp_measure.py` | Build the test collection and measure error rates |
| `scripts/generate_machine.py` | Creates AI-written samples for the catch rate (maintainers only; needs an Anthropic API key) |
| `corpus/` | Document fingerprints, the published prompts, and measured results |
| `eval/` | Sample texts and the expected results for each |
| `tests/` | Automated tests |
| `pyproject.toml`, `action.yml`, `.pre-commit-hooks.yaml` | Packaging, the GitHub Action, and the pre-commit check |
| `agents/openai.yaml` | Display name and default prompt for Codex |
| `CHANGELOG.md` | Every change, by version |
| `WARP.md` | Guide for maintainers |

</details>

## Credits and license

This project uses the [MIT License](LICENSE).

It is a rebuild of [blader/humanizer](https://github.com/blader/humanizer) by Siqi Chen (MIT, copyright 2025). It adds a catalog of habits, detection of leaked chatbot text, a fact-checking compare mode, wiki and style modes, and measured error rates. The `LICENSE` file includes both copyright notices.

It draws on these sources:

- [blader/humanizer](https://github.com/blader/humanizer) by Siqi Chen (MIT)
- [Stop Slop](https://github.com/hardikpandya/stop-slop) by Hardik Pandya (MIT)
- [avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) by Conor Bronsdon (MIT): the vocabulary tiers, strictness rules, self-check, and error-rate measurement design
- [humanize](https://github.com/harshaneel/humanize) by Harshaneel Gokhale (MIT): rhythm counts and several patterns
- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) by WikiProject AI Cleanup ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/))
- [Project Gutenberg #37134](https://www.gutenberg.org/ebooks/37134): the public-domain text of *The Elements of Style* by William Strunk Jr.
- [US-PD-Newspapers](https://huggingface.co/datasets/PleIAs/US-PD-Newspapers) by PleIAs: public-domain newspapers in the human test set
- [RAID](https://github.com/liamdugan/raid) by Dugan and others (MIT): AI-written test set
- [WildChat-1M](https://huggingface.co/datasets/allenai/WildChat-1M) by Ai2 (ODC-BY): AI-written test set
- [Python Enhancement Proposals](https://github.com/python/peps) (public domain): technical writing in the human test set

## Version history

Current release: **v4.14.1**. It adds a section on where your text goes and tidies the corpus files. Version 4.14.0 before it measured errors in both directions and added the command, the pre-commit check, and the GitHub Action. Every change is listed in the [changelog](CHANGELOG.md).
