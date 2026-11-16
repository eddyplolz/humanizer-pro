"""Gate CI on `claude plugin validate --json` output.

The repo keeps CLAUDE.md at its root for contributors. The validator reports
that file as a warning, because a plugin does not load it. This gate allows
exactly that warning, matched by its full text, and fails on any other error,
warning, blocking directory finding, or failed run.

Usage: claude plugin validate .claude-plugin/marketplace.json --json > report.json
       python scripts/check_plugin_validate.py report.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ALLOWED_WARNINGS = frozenset(
    {
        "CLAUDE.md at the plugin root is not loaded as project context. To ship context "
        "with your plugin, use a skill (skills/<name>/SKILL.md) instead.",
    }
)


def problems(report: dict) -> list[str]:
    """Return one line per finding the gate does not allow; empty means pass."""
    found = []
    if report.get("success") is not True:
        found.append("validator reported success: false")
    sections = [report.get("manifest") or {}, *(report.get("contents") or [])]
    for section in sections:
        where = section.get("file") or section.get("type") or "manifest"
        for error in section.get("errors") or []:
            found.append(f"error in {where}: {error.get('message')}")
        for warning in section.get("warnings") or []:
            message = warning.get("message")
            if message not in ALLOWED_WARNINGS:
                found.append(f"warning in {where}: {message}")
    for finding in (report.get("directory") or {}).get("findings") or []:
        if finding.get("blocking"):
            found.append(
                f"blocking finding {finding.get('code')}: {finding.get('message')}"
            )
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_plugin_validate.py REPORT.json", file=sys.stderr)
        return 2
    text = Path(argv[0]).read_text(encoding="utf-8")
    try:
        report = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"validator output is not valid JSON: {exc}", file=sys.stderr)
        return 1
    found = problems(report)
    for line in found:
        print(line, file=sys.stderr)
    if found:
        return 1
    print("plugin validate: clean apart from the allowed CLAUDE.md warning")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
