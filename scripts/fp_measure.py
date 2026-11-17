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
CACHE_DIR = ROOT / "corpus" / "cache"
RESULT_SCHEMA = "humanizer-fp-measure.v3"
DEFAULT_THRESHOLD = 60  # the CLI's default review threshold
# Every threshold from 0 to 100 in steps of 5 goes into the JSON; the
# results page prints every second one to stay readable.
SWEEP = tuple(range(0, 101, 5))
PAGE_SWEEP = tuple(range(10, 100, 10))
# A cap of 1% means one false positive per hundred human documents. A dev
# slice smaller than this cannot show whether a threshold holds the cap.
DEFAULT_FPR_CAP = 0.01
MIN_CAP_N = 50
# A human set frozen before the cutoff drifts: the further a document sits
# from the present, the less its prose says about the writing the tool meets
# today (Ren, Raghavan and Garg 2026 saw a 2010-trained estimator call 15% of
# 2020 abstracts machine-written). So the rate is also reported by period.
PERIODS = (("pre-1930", 0, 1929), ("1930-2017", 1930, 2017), ("2018-2022", 2018, 2022))


def period_of(date: str) -> str:
    """Band a manifest date ("1899", "2021-06", "pre-1923", "1900-1922")."""
    text = str(date or "")
    if text.startswith("pre-"):
        return PERIODS[0][0]
    year = int(text[:4]) if text[:4].isdigit() else None
    if year is None:
        return "undated"
    for name, low, high in PERIODS:
        if low <= year <= high:
            return name
    return "undated"
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
                "period": period_of(entry.get("date", "")),
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


def share_flagged(rows: list[dict], threshold: int) -> float | None:
    if not rows:
        return None
    return round(sum(1 for r in rows if is_flagged(r, threshold)) / len(rows), 4)


def rank_score(row: dict) -> int:
    """Risk for ranking; a block outranks every score, as it does at any threshold."""
    return 101 if row["blocked"] else row["risk"]


def auroc(human_rows: list[dict], machine_rows: list[dict]) -> float | None:
    """Chance a random machine document outranks a random human one; ties count half.

    0.5 means the score cannot tell the two apart; 1.0 means it always can.
    It needs no threshold, so it shows separation the threshold choice hides.
    """
    if not human_rows or not machine_rows:
        return None
    human = [rank_score(r) for r in human_rows]
    wins = 0.0
    for m in (rank_score(r) for r in machine_rows):
        wins += sum(1.0 if m > h else 0.5 if m == h else 0.0 for h in human)
    return round(wins / (len(human) * len(machine_rows)), 4)


def register_curves(
    human_rows: list[dict], machine_rows: list[dict], thresholds: tuple[int, ...] = SWEEP
) -> dict:
    """Per register: FPR and catch rate at every threshold, AUROC, and the mean-risk gap.

    Pass test-split rows only; the published curves never read the dev split.
    """
    curves = {}
    for reg in sorted({r["register"] for r in human_rows} | {r["register"] for r in machine_rows}):
        human = [r for r in human_rows if r["register"] == reg]
        machine = [r for r in machine_rows if r["register"] == reg]
        gap = None
        if human and machine:
            gap = round(
                sum(r["risk"] for r in machine) / len(machine)
                - sum(r["risk"] for r in human) / len(human),
                1,
            )
        curves[reg] = {
            "human_n": len(human),
            "machine_n": len(machine),
            "auroc": auroc(human, machine),
            "mean_risk_gap": gap,
            "points": [
                {"threshold": t, "fpr": share_flagged(human, t), "catch": share_flagged(machine, t)}
                for t in thresholds
            ],
        }
    return curves


def policy_caps(
    human_dev: list[dict],
    human_test: list[dict],
    machine_test: list[dict],
    cap: float = DEFAULT_FPR_CAP,
    thresholds: tuple[int, ...] = SWEEP,
    min_n: int = MIN_CAP_N,
) -> dict:
    """Per register: the lowest threshold whose dev-split FPR stays within the cap.

    The threshold is chosen on the dev split and graded on the test split, so
    the reported FPR and catch rate are not the numbers that picked it.
    """
    by_register = {}
    for reg in sorted({r["register"] for r in human_dev} | {r["register"] for r in human_test}):
        dev = [r for r in human_dev if r["register"] == reg]
        test = [r for r in human_test if r["register"] == reg]
        machine = [r for r in machine_test if r["register"] == reg]
        entry = {
            "dev_n": len(dev),
            "test_n": len(test),
            "machine_n": len(machine),
            "threshold": None,
            "reason": None,
            "test_fpr": None,
            "test_fpr_ci95": None,
            "catch": None,
            "catch_ci95": None,
        }
        blocked_share = sum(1 for r in dev if r["blocked"]) / len(dev) if dev else 0.0
        # Compare unrounded shares: a rounded 1.0040% would pass a 1% cap.
        chosen = next(
            (t for t in thresholds if dev and sum(1 for r in dev if is_flagged(r, t)) / len(dev) <= cap),
            None,
        )
        if len(dev) < min_n:
            entry["reason"] = (
                f"dev split has {len(dev)} human documents; the cap needs at least {min_n}"
            )
        elif blocked_share > cap:
            entry["reason"] = (
                f"blocks alone flag {pct(blocked_share)} of the dev split, above the {pct(cap)} cap"
            )
        elif chosen is None:
            entry["reason"] = f"no threshold up to {thresholds[-1]} holds the {pct(cap)} cap"
        else:
            entry["threshold"] = chosen
            if test:
                flagged = sum(1 for r in test if is_flagged(r, chosen))
                entry["test_fpr"] = share_flagged(test, chosen)
                entry["test_fpr_ci95"] = [round(v, 4) for v in wilson_interval(flagged, len(test))]
            if machine:
                caught = sum(1 for r in machine if is_flagged(r, chosen))
                entry["catch"] = share_flagged(machine, chosen)
                entry["catch_ci95"] = [round(v, 4) for v in wilson_interval(caught, len(machine))]
        by_register[reg] = entry
    return {"cap": cap, "min_dev_n": min_n, "by_register": by_register}


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


def measure(threshold: int, include_fixture_tp: bool, fpr_cap: float = DEFAULT_FPR_CAP) -> dict:
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
    by_period = {
        period: slice_stats([r for r in rows if r["period"] == period], threshold)
        for period in [name for name, _lo, _hi in PERIODS] + ["undated"]
        if any(r["period"] == period for r in rows)
    }
    machine_test = [r for r in machine_rows if r["split"] == "test"]
    human_dev = [r for r in human_rows if r["split"] == "dev"]
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
        "by_period": by_period,
        "register_curves": register_curves(rows, machine_test),
        "policy_caps": policy_caps(human_dev, rows, machine_test, cap=fpr_cap),
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


def sweep_cell(curve: dict, threshold: int) -> str:
    point = next(p for p in curve["points"] if p["threshold"] == threshold)
    fpr = "-" if point["fpr"] is None else pct(point["fpr"])
    catch = "-" if point["catch"] is None else pct(point["catch"])
    return f"{fpr} / {catch}"


def separation_cells(curve: dict) -> str:
    if curve["auroc"] is None:
        return f"human n {curve['human_n']}, machine n {curve['machine_n']}: one pool is empty"
    return (
        f"human n {curve['human_n']}, machine n {curve['machine_n']}, "
        f"AUROC {curve['auroc']:.2f}, mean risk gap {curve['mean_risk_gap']:+.1f}"
    )


def cap_summary(entry: dict) -> str:
    if entry["threshold"] is None:
        return f"dev n {entry['dev_n']}: no threshold ({entry['reason']})"
    fpr = "-" if entry["test_fpr"] is None else pct(entry["test_fpr"])
    catch = "-" if entry["catch"] is None else pct(entry["catch"])
    return f"dev n {entry['dev_n']}: threshold {entry['threshold']}, test FPR {fpr}, catch {catch}"


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
    for period, stats in result.get("by_period", {}).items():
        lines.append(row(f"period:{period}", stats))
    lines.append("")
    curves = result["register_curves"]
    lines.append("FPR / catch rate by review threshold (test split):")
    lines.append("  threshold " + " ".join(f"{reg:>15}" for reg in curves))
    for t in PAGE_SWEEP:
        lines.append(
            f"  {t:>9} " + " ".join(f"{sweep_cell(curves[reg], t):>15}" for reg in curves)
        )
    lines.append("")
    lines.append("Separation by register (test split):")
    for reg, curve in curves.items():
        lines.append(f"  {reg:10} {separation_cells(curve)}")
    caps = result["policy_caps"]
    lines.append("")
    lines.append(f"Threshold under a {pct(caps['cap'])} FPR cap (chosen on dev, graded on test):")
    for reg, entry in caps["by_register"].items():
        lines.append(f"  {reg:10} {cap_summary(entry)}")
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
    for period, stats in result.get("by_period", {}).items():
        lines.append(row(f"period: {period}", stats))
    # With nothing cached there are no register columns, and an empty table
    # renders as broken Markdown.
    curves = result["register_curves"]
    if curves:
        lines.extend(
            [
                "",
                "## Error rates by review threshold",
                "",
                "Each cell is false-positive rate / catch rate at that threshold, test split.",
                "Raising the threshold lowers both; a dash means the register has no",
                "text in that pool. The JSON output carries every threshold in steps of 5.",
                "",
                "| Threshold | " + " | ".join(curves) + " |",
                "|---|" + "|".join("---" for _ in curves) + "|",
            ]
        )
        for t in PAGE_SWEEP:
            lines.append(f"| {t} | " + " | ".join(sweep_cell(curves[reg], t) for reg in curves) + " |")
        lines.extend(
            [
                "",
                "## Separation by register",
                "",
                "AUROC is the chance a random machine document ranks above a random human",
                "one (0.5 = no better than a coin, 1.0 = always). It needs no threshold.",
                "Ties count half, and a blocked document ranks above every score, as it is",
                "flagged at every threshold. The mean risk gap is machine mean risk minus",
                "human mean risk, in score points; it ignores blocks.",
                "",
                "| Register | Human n | Machine n | AUROC | Mean risk gap |",
                "|---|---|---|---|---|",
            ]
        )
        for reg, curve in curves.items():
            auc = "-" if curve["auroc"] is None else f"{curve['auroc']:.2f}"
            gap = "-" if curve["mean_risk_gap"] is None else f"{curve['mean_risk_gap']:+.1f}"
            lines.append(
                f"| {reg} | {curve['human_n']} | {curve['machine_n']} | {auc} | {gap} |"
            )
    caps = result["policy_caps"]
    if caps["by_register"]:
        lines.extend(
            [
                "",
                f"## Threshold under a {pct(caps['cap'])} false-positive cap",
                "",
                "For each register, the lowest threshold whose false-positive rate on the",
                "dev split stays at or under the cap. The rates shown are from the test",
                "split, so the numbers that picked the threshold do not grade it.",
                "",
                "| Register | Dev n | Threshold | Test FPR | Catch rate |",
                "|---|---|---|---|---|",
            ]
        )
        for reg, entry in caps["by_register"].items():
            if entry["threshold"] is None:
                lines.append(f"| {reg} | {entry['dev_n']} | none: {entry['reason']} | - | - |")
                continue
            fpr = "-" if entry["test_fpr"] is None else pct(entry["test_fpr"])
            catch = "-" if entry["catch"] is None else pct(entry["catch"])
            lines.append(f"| {reg} | {entry['dev_n']} | {entry['threshold']} | {fpr} | {catch} |")
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
            "- Register mapping: Stack Exchange answers (hobby, language, and",
            "  workplace sites) → chat, English Wikipedia articles at their last",
            "  pre-cutoff revision → wiki, public-domain prose (Strunk 1918, Emerson,",
            "  Thoreau, Twain) → essay, Internet Archive newspaper issues and",
            "  OpenCulture US-PD-Newspapers pages → news, Python Enhancement",
            "  Proposals → docs. The essay and news slices measure century-old",
            "  prose, stated rather than hidden.",
            "- The news pool is OCR of old newsprint: an alphabetic-ratio",
            "  quality gate bounds the OCR noise but does not eliminate it, so a news",
            "  flag can reflect the scan rather than the writing.",
            "- A Wikipedia entry is a whole article (bounded at 4,000 words), so",
            "  it is many editors' text; a Stack Exchange entry is one answer, with",
            "  code and quoted blocks removed. Answers are top-voted, so the chat",
            "  slice leans toward careful writers.",
            "- Machine text comes from RAID (2023 generators) and WildChat (GPT-3.5",
            "  and GPT-4 replies). An optional pool from current Claude models",
            "  (scripts/generate_machine.py) is not part of the published numbers.",
            "  The catch rate describes those models only; tells change between",
            "  model generations.",
            "- Era confound: human essays and news are a century old, while machine",
            "  essays and news are modern. A gap between the two rates there is partly",
            "  era, not authorship. The wiki, chat, and docs slices compare",
            "  contemporaries more closely.",
            "- Every pool is public and rebuildable from the manifest's pointers",
            "  (`corpus.py fetch` or the named `build-*` command); every document",
            "  comes from a public source.",
            "- Registers are measured separately because rates differ by register;",
            "  quoting the overall number alone misrepresents the tool.",
            "- Periods are measured separately because a human set frozen before the",
            "  cutoff drifts away from today's writing; the 2018–2022 band is the one",
            "  closest to the prose the tool meets, and the one to watch.",
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
    parser.add_argument(
        "--fpr-cap",
        type=float,
        default=DEFAULT_FPR_CAP,
        help="False-positive cap for the per-register threshold table (default 0.01).",
    )
    args = parser.parse_args(argv)
    if not 0.0 <= args.fpr_cap <= 1.0:  # also rejects nan
        parser.error(f"--fpr-cap must be between 0 and 1, got {args.fpr_cap}")
    result = measure(args.threshold, args.include_fixture_tp, args.fpr_cap)
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
