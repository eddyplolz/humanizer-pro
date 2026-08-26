#!/usr/bin/env python3
"""Measure false-positive rates over the human-control corpus, by register.

Every corpus document predates ChatGPT (see corpus/manifest.json), so any
flag the audit raises on one is a false positive by construction. This
script converts the skill's restraint principle from a promise into a
number. Design adapted from avoid-ai-writing's fp-measure (MIT).

Rates are reported by register because an aggregate hides exactly the
failure this exists to catch: a rule set can be gentle on chat and harsh
on technical prose at the same time. Wilson 95% intervals accompany every
rate — small slices get honest, wide intervals rather than false precision.

There is no machine-generated corpus here yet, so no true-positive rate is
claimed. `--include-fixture-tp` audits the repo's own AI fixtures, but
those tuned the rules, so that readout is anecdotal and labeled as such.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "corpus" / "manifest.json"
CACHE_DIR = ROOT / "corpus" / "cache"
RESULT_SCHEMA = "humanizer-fp-measure.v1"
DEFAULT_THRESHOLD = 60  # the CLI's default review threshold
SWEEP = (20, 40, 60, 80)
FIXTURE_TP = [
    "eval/fixtures/ai-slop-general.md",
    "eval/fixtures/artifact-leakage.md",
    "eval/fixtures/wiki-promotional.md",
    "eval/fixtures/over-humanized.md",
]

_spec = importlib.util.spec_from_file_location(
    "humanizer_audit", Path(__file__).resolve().parent / "humanizer_audit.py"
)
_audit = importlib.util.module_from_spec(_spec)
sys.modules["humanizer_audit"] = _audit
_spec.loader.exec_module(_audit)


def wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; (0, 1) bounds on n=0."""
    if total == 0:
        return (0.0, 1.0)
    p = hits / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def audit_corpus(threshold: int) -> tuple[list[dict], list[str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows, missing = [], []
    for entry in manifest["entries"]:
        path = CACHE_DIR / f"{entry['id']}.txt"
        if not path.exists():
            missing.append(entry["id"])
            continue
        result = _audit.audit_text(path.read_text(encoding="utf-8"), entry["id"])
        rows.append(
            {
                "id": entry["id"],
                "register": entry["register"],
                "author": entry["author"],
                "words": entry["words"],
                "risk": int(result["risk_score"]),
                "blocked": any(f["severity"] == "error" for f in result["findings"]),
                "rule_ids": sorted({f["id"] for f in result["findings"]}),
                "flagged": int(result["risk_score"]) >= threshold,
            }
        )
    return rows, missing


def slice_stats(rows: list[dict], threshold: int) -> dict:
    n = len(rows)
    flagged = sum(1 for r in rows if r["risk"] >= threshold)
    blocked = sum(1 for r in rows if r["blocked"])
    low, high = wilson_interval(flagged, n)
    return {
        "n": n,
        "flagged": flagged,
        "fpr": round(flagged / n, 4) if n else None,
        "fpr_ci95": [round(low, 4), round(high, 4)],
        "blocked": blocked,
        "median_risk": sorted(r["risk"] for r in rows)[n // 2] if n else None,
    }


def measure(threshold: int, include_fixture_tp: bool) -> dict:
    rows, missing = audit_corpus(threshold)
    registers = sorted({r["register"] for r in rows})
    by_register = {
        reg: slice_stats([r for r in rows if r["register"] == reg], threshold)
        for reg in registers
    }
    by_author = {
        author: slice_stats([r for r in rows if r["author"] == author], threshold)
        for author in sorted({r["author"] for r in rows})
    }
    sweep = {
        str(t): {
            reg: slice_stats([r for r in rows if r["register"] == reg], t)["fpr"]
            for reg in registers
        }
        for t in SWEEP
    }
    rule_hits: Counter[str] = Counter()
    for row in rows:
        rule_hits.update(row["rule_ids"])
    result: dict = {
        "schema": RESULT_SCHEMA,
        "threshold": threshold,
        "corpus_documents": len(rows),
        "missing_cache": missing,
        "overall": slice_stats(rows, threshold),
        "by_register": by_register,
        "by_author": by_author,
        "threshold_sweep_fpr": sweep,
        "top_rules_on_human_text": [
            {"rule": rule, "documents": count} for rule, count in rule_hits.most_common(12)
        ],
    }
    if include_fixture_tp:
        tp_rows = []
        for rel in FIXTURE_TP:
            audit = _audit.audit_text((ROOT / rel).read_text(encoding="utf-8"), rel)
            tp_rows.append(
                {
                    "path": rel,
                    "risk": int(audit["risk_score"]),
                    "detected": int(audit["risk_score"]) >= threshold
                    or any(f["severity"] == "error" for f in audit["findings"]),
                }
            )
        result["fixture_tp_anecdotal"] = {
            "note": (
                "In-repo AI fixtures; they tuned these rules, so this is a sanity "
                "check, not a true-positive rate."
            ),
            "detected": sum(1 for r in tp_rows if r["detected"]),
            "n": len(tp_rows),
            "rows": tp_rows,
        }
    return result


def pct(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def render_text(result: dict) -> str:
    lines = [
        f"FP measurement over {result['corpus_documents']} human-control documents "
        f"(review threshold {result['threshold']})",
        "",
        f"{'slice':22} {'n':>5} {'flagged':>8} {'FPR':>7} {'95% CI':>16} {'blocked':>8}",
    ]

    def row(name: str, stats: dict) -> str:
        low, high = stats["fpr_ci95"]
        return (
            f"{name:22} {stats['n']:>5} {stats['flagged']:>8} {pct(stats['fpr']):>7} "
            f"{pct(low):>7}-{pct(high):<8} {stats['blocked']:>8}"
        )

    lines.append(row("overall", result["overall"]))
    for reg, stats in result["by_register"].items():
        lines.append(row(f"register:{reg}", stats))
    for author, stats in result["by_author"].items():
        lines.append(row(f"author:{author}", stats))
    lines.append("")
    lines.append("FPR by review threshold:")
    header = "  threshold " + " ".join(f"{reg:>8}" for reg in result["by_register"])
    lines.append(header)
    for t, per_register in result["threshold_sweep_fpr"].items():
        lines.append(
            f"  {t:>9} " + " ".join(f"{pct(per_register[reg]):>8}" for reg in result["by_register"])
        )
    lines.append("")
    lines.append("Rules firing most often on human text (documents touched):")
    for item in result["top_rules_on_human_text"]:
        lines.append(f"  {item['documents']:>5}  {item['rule']}")
    if result["missing_cache"]:
        lines.append("")
        lines.append(
            f"WARNING: {len(result['missing_cache'])} manifest entries had no cached "
            "text and were skipped (run corpus.py fetch / build first)."
        )
    if "fixture_tp_anecdotal" in result:
        tp = result["fixture_tp_anecdotal"]
        lines.append("")
        lines.append(
            f"Fixture sanity check: {tp['detected']}/{tp['n']} in-repo AI fixtures "
            f"detected ({tp['note']})"
        )
    return "\n".join(lines)


def render_results_md(result: dict) -> str:
    lines = [
        "# Measured false-positive rates",
        "",
        "Generated by `scripts/fp_measure.py` over the hash-only human-control corpus",
        "(`corpus/manifest.json`). Every document predates ChatGPT, so every flag",
        "counted here is a false positive by construction. No true-positive rate is",
        "claimed: there is no machine-generated corpus in this repo yet.",
        "",
        f"- Documents: **{result['corpus_documents']}**",
        f"- Review threshold: **{result['threshold']}** (the CLI default)",
        "",
        "| Slice | n | Flagged | FPR | 95% CI | Blocked (exit 2) |",
        "|---|---|---|---|---|---|",
    ]

    def row(name: str, stats: dict) -> str:
        low, high = stats["fpr_ci95"]
        return (
            f"| {name} | {stats['n']} | {stats['flagged']} | {pct(stats['fpr'])} | "
            f"{pct(low)}–{pct(high)} | {stats['blocked']} |"
        )

    lines.append(row("overall", result["overall"]))
    for reg, stats in result["by_register"].items():
        lines.append(row(f"register: {reg}", stats))
    for author, stats in result["by_author"].items():
        lines.append(row(f"author: {author}", stats))
    lines.extend(
        [
            "",
            "## FPR by review threshold",
            "",
            "| Threshold | " + " | ".join(result["by_register"]) + " |",
            "|---|" + "|".join("---" for _ in result["by_register"]) + "|",
        ]
    )
    for t, per_register in result["threshold_sweep_fpr"].items():
        lines.append(
            f"| {t} | " + " | ".join(pct(per_register[reg]) for reg in result["by_register"]) + " |"
        )
    lines.extend(
        [
            "",
            "## Rules firing most often on human text",
            "",
            "| Documents touched | Rule |",
            "|---|---|",
        ]
    )
    for item in result["top_rules_on_human_text"]:
        lines.append(f"| {item['documents']} | `{item['rule']}` |")
    lines.extend(
        [
            "",
            "## Honest limits",
            "",
            "- Register mapping: forum posts → chat, wiki revisions → wiki,",
            "  public-domain prose (Strunk 1918, Emerson, Thoreau, Twain) → essay,",
            "  Internet Archive newspaper issues (1900–1922) → news. The essay and",
            "  news slices measure century-old prose, stated rather than hidden.",
            "- The news pool is OCR of old newsprint: an alphabetic-ratio",
            "  quality gate bounds the OCR noise but does not eliminate it, so a news",
            "  flag can reflect the scan rather than the writing.",
            "- The corpus skews toward one writer and one community; it measures",
            "  restraint on the registers this skill actually meets, not all prose.",
            "- Registers are measured separately because rates differ by register;",
            "  quoting the overall number alone misrepresents the tool.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--include-fixture-tp",
        action="store_true",
        help="Also audit the repo's own AI fixtures (anecdotal sanity check).",
    )
    parser.add_argument(
        "--write-results",
        metavar="PATH",
        help="Write a Markdown results page (e.g. corpus/RESULTS.md).",
    )
    args = parser.parse_args(argv)
    result = measure(args.threshold, args.include_fixture_tp)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    if args.write_results:
        Path(args.write_results).write_text(
            render_results_md(result), encoding="utf-8", newline="\n"
        )
        print(f"\nwrote {args.write_results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
