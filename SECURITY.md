# Security policy

The checker runs locally, makes no network connections, and has no dependencies, so the attack
surface is small: a crafted input file, the SARIF output, or the GitHub Action's handling of its
inputs.

## Reporting

Please report a vulnerability privately through GitHub's
[private vulnerability reporting](https://github.com/eddyplolz/humanizer-pro/security/advisories/new)
rather than a public issue. Include the input that triggers it and the version
(`humanizer-audit --version`). You will get a reply within a week, and a fix release once it is
confirmed.

## Supported versions

Only the latest release on PyPI and on `main` receives fixes.
