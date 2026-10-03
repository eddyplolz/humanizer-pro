#!/usr/bin/env python3
"""Measure false-positive and catch rates over the corpus, by register.

Every corpus document predates ChatGPT (see corpus/manifest.json), so any
flag the audit raises on one is a false positive by construction. This
script converts the skill's restraint principle from a promise into a
number. Design adapted from avoid-ai-writing's fp-measure (MIT).

Rates are reported by register because an aggregate hides exactly the
failure this exists to catch: a rule set can be gentle on chat and harsh
on technical prose at the same time. Wilson 95% intervals accompany every
rate — small slices get honest, wide intervals rather than false precision.

Machine-labelled entries (RAID, WildChat, current-model generations) give
the other direction: the catch rate, measured with the same "flagged"
definition on the held-out test split only. The dev split feeds the rule
scorecard, the one place rule tuning may look. `--include-fixture-tp`
audits the repo's own AI fixtures, but those tuned the rules, so that
readout is anecdotal and labelled as such.
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
PRIVATE_MANIFEST_PATH = ROOT / "corpus" / "manifest.private.json"  # gitignored
CACHE_DIR = ROOT / "corpus" / "cache"
RESULT_SCHEMA = "humanizer-fp-measure.v2"
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
_corpus_spec = importlib.util.spec_from_file_location("corpus", Path(__file__).resolve().parent / "corpus.py")
_corpus = importlib.util.module_from_spec(_corpus_spec)
sys.modules.setdefault("corpus", _corpus)
_corpus_spec.loader.exec_module(_corpus)


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
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]
    # The maintainer's own forum and wiki entries are kept out of the public
    # manifest; they are measured only on a machine that has the private file.
    if PRIVATE_MANIFEST_PATH.exists():
        entries = entries + json.loads(PRIVATE_MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]
    rows, missing = [], []
    for entry in entries:
        path = CACHE_DIR / f"{entry['id']}.txt"
        if not path.exists():
            missing.append(entry["id"])
            continue
        # Bytes, not read_text(): audit exactly the text the digest covers.
        text = path.read_bytes().decode("utf-8")
        result = _audit.audit_text(text, entry["id"])
        rows.append(
            {
                "id": entry["id"],
                "label": entry.get("label", "human"),
                "split": entry.get("split") or _corpus.digest_split(entry["sha256"]),
                "model": entry.get("model"),
                "register": entry["register"],
                "author": entry["author"],
                "words": entry["words"],
                "risk": int(result["risk_score"]),
                "blocked": any(f["severity"] == "error" for f in result["findings"]),
                "rule_ids": sorted({f["id"] for f in result["findings"]}),
            }
        )
    return rows, missing


def is_flagged(row: dict, threshold: int) -> bool:
    """Any non-pass CLI outcome on human text is a false positive.

    A block (exit 2) fails a CI gate as surely as a review (exit 1), so it
    counts whatever the risk score. The fixture readout below already counts
    blocks as detections; leaving them out here hid human blocks.
    """
    return row["risk"] >= threshold or row["blocked"]


def median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def slice_stats(rows: list[dict], threshold: int) -> dict:
    n = len(rows)
    flagged = sum(1 for r in rows if is_flagged(r, threshold))
    blocked = sum(1 for r in rows if r["blocked"])
    low, high = wilson_interval(flagged, n)
    return {
        "n": n,
        "flagged": flagged,
        "fpr": round(flagged / n, 4) if n else None,
        "fpr_ci95": [round(low, 4), round(high, 4)],
        "blocked": blocked,
        "median_risk": median([r["risk"] for r in rows]),
    }


def catch_stats(rows: list[dict], threshold: int) -> dict:
    """Share of machine documents the CLI would not pass, with a Wilson CI."""
    n = len(rows)
    caught = sum(1 for r in rows if is_flagged(r, threshold))
    low, high = wilson_interval(caught, n)
    return {
        "n": n,
        "caught": caught,
        "rate": round(caught / n, 4) if n else None,
        "rate_ci95": [round(low, 4), round(high, 4)],
    }


def catch_rates(machine_rows: list[dict], threshold: int) -> dict | None:
    """Catch rate on the test split, overall, by register, and by model."""
    test = [r for r in machine_rows if r["split"] == "test"]
    if not test:
        return None
    return {
        "split": "test",
        "overall": catch_stats(test, threshold),
        "by_register": {
            reg: catch_stats([r for r in test if r["register"] == reg], threshold)
            for reg in sorted({r["register"] for r in test})
        },
        "by_model": {
            model: catch_stats([r for r in test if r["model"] == model], threshold)
            for model in sorted({str(r["model"]) for r in test})
        },
    }


def rule_scorecard(human_rows: list[dict], machine_rows: list[dict]) -> list[dict]:
    """Per rule: share of human dev documents vs share of machine dev documents.

    A rule whose machine share is not clearly above its human share costs
    false positives without catching AI text. Both sides use the dev split
    only, so acting on it touches neither published rate.
    """
    human_rows = [r for r in human_rows if r["split"] == "dev"]
    dev = [r for r in machine_rows if r["split"] == "dev"]
    if not human_rows or not dev:
        return []
    human_hits: Counter[str] = Counter()
    machine_hits: Counter[str] = Counter()
    for row in human_rows:
        human_hits.update(row["rule_ids"])
    for row in dev:
        machine_hits.update(row["rule_ids"])
    card = []
    for rule in sorted(set(human_hits) | set(machine_hits)):
        human_share = human_hits[rule] / len(human_rows)
        machine_share = machine_hits[rule] / len(dev)
        card.append(
            {
                "rule": rule,
                "human_share": round(human_share, 4),
                "machine_share": round(machine_share, 4),
                # None when the rule never fires on human text.
                "ratio": round(machine_share / human_share, 2) if human_share else None,
            }
        )
    # Weakest evidence first: lowest machine-to-human ratio.
    card.sort(key=lambda item: (item["ratio"] is None, item["ratio"] or 0.0, item["rule"]))
    return card


def measure(threshold: int, include_fixture_tp: bool) -> dict:
    all_rows, missing = audit_corpus(threshold)
    # False-positive rates are about human text only; a machine row in these
    # tables would count a correct catch as a false alarm. They are published
    # on the human test split, so rule tuning on the dev split cannot grade
    # itself.
    human_rows = [r for r in all_rows if r["label"] == "human"]
    rows = [r for r in human_rows if r["split"] == "test"]
    machine_rows = [r for r in all_rows if r["label"] == "machine"]
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
        "human_dev_documents": len(human_rows) - len(rows),
        "machine_documents": len(machine_rows),
        "missing_cache": missing,
        "overall": slice_stats(rows, threshold),
        "by_register": by_register,
        "by_author": by_author,
        "threshold_sweep_fpr": sweep,
        "top_rules_on_human_text": [
            {"rule": rule, "documents": count} for rule, count in rule_hits.most_common(12)
        ],
        "catch_rate": catch_rates(machine_rows, threshold),
        "rule_scorecard": rule_scorecard(human_rows, machine_rows),
    }
    if include_fixture_tp:
        tp_rows = []
        for rel in FIXTURE_TP:
            audit = _audit.audit_text((ROOT / rel).read_text(encoding="utf-8"), rel)
            tp_rows.append(
                {
                    "path": rel,
                    "risk": int(audit["risk_score"]),
                    "detected": is_flagged(
                        {
                            "risk": int(audit["risk_score"]),
                            "blocked": any(f["severity"] == "error" for f in audit["findings"]),
                        },
                        threshold,
                    ),
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
        f"FP measurement over {result['corpus_documents']} human-control documents, test split "
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
    lines.append("")
    catch = result["catch_rate"]
    if catch is None:
        lines.append("Catch rate: not measured (no machine documents in the test split are cached).")
    else:
        lines.append(f"Catch rate on {catch['overall']['n']} machine documents (test split):")
        for name, stats in [("overall", catch["overall"])] + [
            (f"register:{reg}", stats) for reg, stats in catch["by_register"].items()
        ] + [(f"model:{model}", stats) for model, stats in catch["by_model"].items()]:
            low, high = stats["rate_ci95"]
            lines.append(
                f"  {name:30} {stats['n']:>5} {stats['caught']:>6} {pct(stats['rate']):>7} "
                f"{pct(low):>7}-{pct(high):<8}"
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
        "# Measured error rates",
        "",
        "Generated by `scripts/fp_measure.py` over the hash-only corpus",
        "(`corpus/manifest.json`). Every human document predates ChatGPT, so every",
        "flag on one is a false positive by construction. Machine documents are",
        "labelled by source. Both rates use only the held-out test split (about three",
        "quarters of each pool, chosen by digest); the dev split is for rule tuning.",
        "",
        f"- Human documents (test split): **{result['corpus_documents']}**; "
        f"{result['human_dev_documents']} more form the dev split behind the rule scorecard",
        f"- Machine documents: **{result['machine_documents']}** (catch rate uses the test split)",
        f"- Review threshold: **{result['threshold']}**"
        + (" (the CLI default)" if result["threshold"] == DEFAULT_THRESHOLD else ""),
        "- Flagged means any non-pass exit: risk at or above the threshold, or a",
        "  block (exit 2) at any score.",
    ]
    if result["missing_cache"]:
        lines.append(
            f"- Manifest entries with no cached text on this machine, skipped: "
            f"**{len(result['missing_cache'])}** — the manifest still counts them; "
            "rates below cover the cached documents only."
        )
    lines += [
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
    # With nothing cached there are no register columns, and an empty table
    # renders as broken Markdown.
    if result["by_register"]:
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
    lines.extend(["", "## Catch rate on machine text (test split)", ""])
    catch = result["catch_rate"]
    if catch is None:
        lines.append(
            "Not measured yet: no machine documents in the test split are cached. Build them with"
        )
        lines.append(
            "`corpus.py build-raid`, `build-wildchat`, and `scripts/generate_machine.py`, then rerun."
        )
    else:
        lines += ["| Slice | n | Caught | Rate | 95% CI |", "|---|---|---|---|---|"]
        for name, stats in [("overall", catch["overall"])] + [
            (f"register: {reg}", stats) for reg, stats in catch["by_register"].items()
        ] + [(f"model: `{model}`", stats) for model, stats in catch["by_model"].items()]:
            low, high = stats["rate_ci95"]
            lines.append(
                f"| {name} | {stats['n']} | {stats['caught']} | {pct(stats['rate'])} | "
                f"{pct(low)}–{pct(high)} |"
            )
    if result["rule_scorecard"]:
        lines.extend(
            [
                "",
                "## Rule scorecard (dev split, machine vs human)",
                "",
                "Share of documents each rule fires on. A ratio near or below 1 means the rule",
                "fires about as often on human text as on AI text: it costs false positives",
                "without evidence. Tune rules from this table only; both published rates use",
                "the test split, which this table never reads.",
                "",
                "| Rule | Human share | Machine share | Ratio |",
                "|---|---|---|---|",
            ]
        )
        for item in result["rule_scorecard"]:
            ratio = "only on machine" if item["ratio"] is None else f"{item['ratio']:.2f}"
            lines.append(
                f"| `{item['rule']}` | {pct(item['human_share'])} | {pct(item['machine_share'])} | {ratio} |"
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
            "  Internet Archive newspaper issues (1900–1922) and OpenCulture",
            "  US-PD-Newspapers pages (dated up to 1928) → news. The essay and",
            "  news slices measure century-old prose, stated rather than hidden.",
            "- The news pool is OCR of old newsprint: an alphabetic-ratio",
            "  quality gate bounds the OCR noise but does not eliminate it, so a news",
            "  flag can reflect the scan rather than the writing.",
            "- A wiki entry is the whole page at the maintainer's last pre-cutoff",
            "  revision, so it can include other editors' text; hence the `mixed`",
            "  author tier.",
            "- Machine text comes from RAID (2023 generators), WildChat (GPT-3.5 and",
            "  GPT-4 replies), and current Claude models on committed prompts. The",
            "  catch rate describes those models only; tells change between model",
            "  generations.",
            "- Era confound: human essays and news are a century old, while machine",
            "  essays and news are modern. A gap between the two rates there is partly",
            "  era, not authorship. The wiki, chat, and docs slices compare",
            "  contemporaries more closely.",
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
