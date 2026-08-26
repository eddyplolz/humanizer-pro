#!/usr/bin/env python3
"""Self-scan: run the Humanizer Pro audit over this repo's own documentation.

A tool that flags AI tells should survive its own pass. Two scores are reported
per document, and both are published on purpose:

- raw: every match, including the tells this repo quotes in order to warn about
  them. That number is noise, and it is shown so nobody wonders what was hidden.
- exempt: the score after the self-reference escape hatch (SKILL.md) is applied
  mechanically — fenced code, inline code, tables, blockquotes, and quoted
  spans are blanked before scoring, because quoted examples of bad writing are
  the product, not the prose.

Budgets in self_scan_budgets.json gate the exempt score. They are regression
ceilings set from measured values with headroom, not quality claims, and they
should only move down. Idea adapted from avoid-ai-writing's PROOF.md (MIT).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGETS_PATH = Path(__file__).resolve().parent / "self_scan_budgets.json"

_spec = importlib.util.spec_from_file_location(
    "humanizer_audit", Path(__file__).resolve().parent / "humanizer_audit.py"
)
_audit = importlib.util.module_from_spec(_spec)
# dataclass processing on Python 3.13+ resolves the defining module through
# sys.modules, so the module must be registered before exec.
sys.modules["humanizer_audit"] = _audit
_spec.loader.exec_module(_audit)

FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
TABLE_ROW_RE = re.compile(r"^\s*\|.*$", re.M)
BLOCKQUOTE_RE = re.compile(r"^\s*>.*$", re.M)
QUOTED_RE = re.compile(r'"[^"\n]+"|“[^”\n]+”')


def scan_targets() -> list[Path]:
    targets = [
        ROOT / "README.md",
        ROOT / "WARP.md",
        ROOT / "SKILL.md",
        ROOT / "eval" / "cases.md",
        ROOT / "scripts" / "README.md",
    ]
    targets.extend(
        sorted(
            path
            for path in (ROOT / "reference").glob("*.md")
            # Strunk's 1918 text is imported public-domain material, not this
            # repo's prose; scanning it would only measure 1918.
            if path.name != "elements-of-style-1918.md"
        )
    )
    return targets


def blank(match: re.Match[str]) -> str:
    return "".join(char if char == "\n" else " " for char in match.group(0))


def apply_exemptions(text: str) -> str:
    for regex in (FENCE_RE, INLINE_CODE_RE, TABLE_ROW_RE, BLOCKQUOTE_RE, QUOTED_RE):
        text = regex.sub(blank, text)
    return text


def scan(budgets: dict[str, int]) -> dict[str, object]:
    rows = []
    failures = []
    for path in scan_targets():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        raw = _audit.audit_text(text, rel)
        exempt = _audit.audit_text(apply_exemptions(text), rel)
        budget = budgets.get(rel)
        over = budget is not None and int(exempt["risk_score"]) > budget
        if budget is None:
            failures.append(f"{rel}: no budget recorded in {BUDGETS_PATH.name}")
        elif over:
            failures.append(f"{rel}: exempt risk {exempt['risk_score']} exceeds budget {budget}")
        rows.append(
            {
                "path": rel,
                "raw_risk": raw["risk_score"],
                "exempt_risk": exempt["risk_score"],
                "exempt_findings": len(exempt["findings"]),
                "budget": budget,
                "over_budget": over,
            }
        )
    return {"schema": "humanizer-self-scan.v1", "documents": rows, "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit this repo's own docs against budgets.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    args = parser.parse_args(argv)
    budgets = json.loads(BUDGETS_PATH.read_text(encoding="utf-8"))
    result = scan(budgets)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{'document':40} {'raw':>4} {'exempt':>7} {'budget':>7}")
        for row in result["documents"]:
            budget = "-" if row["budget"] is None else row["budget"]
            flag = "  OVER" if row["over_budget"] else ""
            print(f"{row['path']:40} {row['raw_risk']:>4} {row['exempt_risk']:>7} {budget:>7}{flag}")
        for failure in result["failures"]:
            print(f"FAIL {failure}")
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
