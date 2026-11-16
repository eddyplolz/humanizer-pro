"""Gate CI on `claude plugin validate --json` output.

The repo keeps CLAUDE.md at its root for contributors. The validator reports
that file as a warning, because a plugin does not load it. This gate allows
exactly that warning, matched by its full text, and fails on any other error,
warning, blocking directory finding, or failed run.

Usage: claude plugin validate . --json > report.json
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


def _shape(what: str, value: object) -> str:
    return f"unexpected report shape: {what} is a {type(value).__name__}"


def problems(report: object) -> list[str]:
    """Return one line per finding the gate does not allow; empty means pass.

    A report missing the sections the gate reads fails too: if the validator
    renames or moves them, a silent pass would hide every new warning.
    """
    if not isinstance(report, dict):
        return [_shape("top level", report)]
    found = []
    if report.get("success") is not True:
        found.append("validator reported success: false")
    manifest = report.get("manifest")
    contents = report.get("contents")
    if not isinstance(manifest, dict):
        found.append(_shape("manifest", manifest))
        manifest = {}
    if not isinstance(contents, list) or not contents:
        found.append("unexpected report shape: contents is missing or empty")
        contents = []
    seen_allowed = False
    for section in [manifest, *contents]:
        if not isinstance(section, dict):
            found.append(_shape("a contents entry", section))
            continue
        where = section.get("file") or section.get("type") or "manifest"
        for error in section.get("errors") or []:
            if not isinstance(error, dict):
                found.append(_shape(f"an error in {where}", error))
                continue
            found.append(f"error in {where}: {error.get('message')}")
        for warning in section.get("warnings") or []:
            if not isinstance(warning, dict):
                found.append(_shape(f"a warning in {where}", warning))
                continue
            message = warning.get("message")
            if message in ALLOWED_WARNINGS:
                seen_allowed = True
            else:
                found.append(f"warning in {where}: {message}")
    if contents and not seen_allowed:
        found.append(
            "the expected CLAUDE.md warning is missing; "
            "the report shape may have changed"
        )
    directory = report.get("directory") or {}
    if not isinstance(directory, dict):
        found.append(_shape("directory", directory))
        directory = {}
    for finding in directory.get("findings") or []:
        if not isinstance(finding, dict):
            found.append(_shape("a directory finding", finding))
            continue
        if finding.get("blocking") or finding.get("severity") == "error":
            found.append(
                f"blocking finding {finding.get('code')}: {finding.get('message')}"
            )
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_plugin_validate.py REPORT.json", file=sys.stderr)
        return 2
    try:
        text = Path(argv[0]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read validator output {argv[0]}: {exc}", file=sys.stderr)
        return 1
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
