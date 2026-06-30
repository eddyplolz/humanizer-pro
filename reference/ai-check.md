# AI Check Mode

AI check is a score-only companion mode for Humanizer Pro. Use it when the user asks to inspect text
without rewriting it.

## Triggers

Use this mode for:

- "check this"
- "score this"
- "audit only"
- "AI check"
- "do not rewrite"
- "check only"
- file-based pre-publish or CI review

If the user asks for a rewrite in the same request, use full audit instead and keep the rewrite
separate from the score.

## Non-Goals

Do not:

- rewrite the text
- optimize against an AI detector
- promise detector bypass, invisibility, or "human score" guarantees
- run external detector APIs
- loop until a score turns green
- add fake-casual voice, synonym spinning, obfuscation, typos, or translation tricks

The score is a deterministic risk readout for writing tells, artifacts, source-risk patterns, and
rhythm. It is not a claim about any third-party detector.

## Process

1. Run the artifact sweep first. Artifact, placeholder, citation-stub, and tracking-source hits are
   blockers.
2. If the local repo is available, run the audit CLI:

   Windows:

   ```bat
   py -3 scripts\humanizer_audit.py path\to\draft.md --json
   ```

   POSIX:

   ```bash
   python3 scripts/humanizer_audit.py path/to/draft.md --json
   ```

3. If only pasted text is available, audit the text directly with the nine-family checklist and the
   same output categories.
4. Quote short evidence. Do not quote more than needed to identify the issue.
5. Stop at diagnosis. Offer a rewrite only if the user asks for one after seeing the check.

## Output

Return:

1. **Score:** `pass`, `review`, or `block`, plus the numeric risk score when the CLI produced one.
2. **Blockers:** artifact leakage, placeholders, citation stubs, tracking URLs, or fidelity drift.
3. **Family hits:** the strongest tell families by number and name.
4. **Source-risk notes:** unsupported claims, vague attribution, citation-shaped text, source-bound
   language, and evidence markers that need preservation.
5. **Evidence:** brief quoted phrases with line numbers when available.
6. **No rewrite:** a one-line note that no rewrite was performed.

Keep the response compact. The user asked for a check, not an essay about writing theory.

## Compare Requests

When the user asks whether a revision preserved the original, use compare mode:

```bat
py -3 scripts\humanizer_audit.py --compare original.md revised.md --json
```

Compare mode is fidelity-only. It flags drift in protected numbers, dates, names, URL targets,
citations, quotes, code blocks, and source-dependent statements. It must not judge style.
