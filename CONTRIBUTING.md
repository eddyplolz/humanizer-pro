# Contributing

Thank you for helping. The project has two parts, and each has a short path in.

## Report a tell the checker missed, or a false positive

Open an issue with the template that fits. A false positive (human writing that was flagged) is
as useful as a miss, and the two issue templates ask for exactly what a fix needs: the text, what
happened, and what should have happened. Please paste only text you are free to share.

## Run the checks locally

You need Python 3.10 or newer. From a checkout:

```bash
python -m pip install pytest
python -m pytest -q tests
python scripts/self_scan.py
```

The first command runs the test suite (about 130 tests, under a minute). The second audits this
project's own documentation against its budgets in `scripts/self_scan_budgets.json`. Both must
pass before a pull request can merge; the same checks run in CI on Linux, macOS, and Windows.

## Change a rule in the checker

`scripts/humanizer_audit.py` is the whole command-line checker, with no dependencies. Every rule
change comes with a regression test in `tests/test_humanizer_audit.py` that fails before the change
and passes after it. `reference/coverage-map.md` is the contract between the prose catalog and the
checker; read it before adding a rule to either side, so the skill and the checker keep saying the
same thing.

## Change the skill

`SKILL.md` is the operating core and stays under 350 lines, with a description under 1,024
characters (a test enforces both). New guidance goes through the review path in
`reference/improvement-loop.md`: a repeated miss becomes a candidate, then a fixture in `eval/`,
then a rule. One-off observations do not go into `SKILL.md`.

## Pull requests

- One change per pull request, with a short title that says what changed.
- Keep `CHANGELOG.md` current: add your change under the top `## Unreleased` heading, or start one.
- CI must be green. A maintainer merges; branches are deleted on merge.

## Releases

A release is a version bump: `__version__` in `scripts/humanizer_audit.py`, the `version` in
`SKILL.md`, and a matching `## x.y.z` heading in `CHANGELOG.md`. When that lands on `main` and CI
passes, the Release workflow tags it and publishes the GitHub release, and the Publish workflow
uploads the package to PyPI.
