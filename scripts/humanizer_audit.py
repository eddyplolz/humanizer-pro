#!/usr/bin/env python3
"""Deterministic audit CLI for Humanizer Pro."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA = "humanizer-audit.v1"
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True)
class Rule:
    id: str
    family: int | None
    regex: re.Pattern[str]
    message: str
    severity: str = "warning"
    source_risk: bool = False


ARTIFACT_RULES = [
    Rule(
        "artifact.chatgpt_citation_stub",
        9,
        re.compile(r"(?:cite)?turn\d+(?:search|image|news|file)\d+", re.I),
        "ChatGPT citation stub leaked into text",
        "error",
        True,
    ),
    Rule(
        "artifact.content_reference",
        9,
        re.compile(r":?contentReference\[oaicite:\d+\]\{index=\d+\}|contentReference", re.I),
        "ChatGPT contentReference citation residue",
        "error",
        True,
    ),
    Rule(
        "artifact.oai_citation",
        9,
        re.compile(r"oaicite|oai_citation(?::\d+)?", re.I),
        "OpenAI citation residue",
        "error",
        True,
    ),
    Rule(
        "artifact.attribution_json",
        9,
        re.compile(r'attributableIndex|\(\{"attribution":\{"attributableIndex":"\d+-\d+"\}\}\)|\^\[[^\]]+\]\('),
        "JSON attribution block leaked into prose",
        "error",
        True,
    ),
    Rule(
        "artifact.perplexity_tag",
        9,
        re.compile(r"\[(?:attached_file|web):\d+\]", re.I),
        "Perplexity source tag leaked into text",
        "error",
        True,
    ),
    Rule(
        "artifact.grok_card",
        9,
        re.compile(r"grok[_-]card|<grok-card[^>]*>|grok_render_citation_card_json=\{[^}]*\}", re.I),
        "Grok citation card leaked into text",
        "error",
        True,
    ),
    Rule(
        "artifact.lenticular_reference",
        9,
        re.compile(r"【\d+†[^】]*】"),
        "Line-reference citation marker leaked into prose",
        "error",
        True,
    ),
    Rule(
        "artifact.chatgpt_tracking_url",
        9,
        re.compile(r"[?&]utm_source=chatgpt\.com", re.I),
        "ChatGPT tracking parameter in URL",
        "error",
        True,
    ),
    Rule(
        "artifact.bracket_placeholder",
        9,
        re.compile(r"\[(?:Your Name|Entertainer's Name|insert[^\]]*|describe[^\]]*|link to[^\]]*)\]", re.I),
        "Unfilled bracket placeholder",
        "error",
        True,
    ),
    Rule(
        "artifact.insert_placeholder",
        9,
        re.compile(r"\b(?:INSERT|PASTE|SOURCE)_[A-Z0-9_]+(?:_HERE)?\b"),
        "Unfilled all-caps placeholder",
        "error",
        True,
    ),
    Rule(
        "artifact.placeholder_comment",
        9,
        re.compile(r"<!--\s*Add (?:if available|[^>]*)-->", re.I),
        "Unfilled HTML placeholder comment",
        "error",
        True,
    ),
    Rule(
        "artifact.placeholder_date",
        9,
        re.compile(r"20\d{2}-(?:XX|\d{2})-XX|\b20XX\b", re.I),
        "Placeholder date",
        "error",
        True,
    ),
]

FAMILY_RULES = [
    Rule(
        "family1.significance_inflation",
        1,
        re.compile(
            r"\b(?:stands as|serves as|pivotal role|pivotal moment|enduring commitment|lasting importance|"
            r"scientific landscape|rich heritage|renowned|groundbreaking|vibrant|breathtaking|boasts)\b",
            re.I,
        ),
        "Significance or promotional inflation",
    ),
    Rule(
        "family2.vague_attribution",
        2,
        re.compile(
            r"\b(?:experts (?:argue|believe)|observers note|studies show|researchers (?:say|believe)|"
            r"gained recognition|featured in|cited in|national media|praised by critics|active social media)\b",
            re.I,
        ),
        "Vague attribution or notability padding",
        source_risk=True,
    ),
    Rule(
        "family3.filler_framing",
        3,
        re.compile(
            r"\b(?:in today's|in conclusion|it is important to note|in order to|due to the fact that|"
            r"at its core|when it comes to|future belongs|exciting journey|journey toward excellence|"
            r"highlighting|underscoring|showcasing|fostering)\b",
            re.I,
        ),
        "Filler framing or superficial analysis",
    ),
    Rule(
        "family5.syntactic_tell",
        5,
        re.compile(
            r"\b(?:it is important to note|there are several|there exists|it can be argued|it has been shown|"
            r"it should be emphasized|what matters is|not insignificant)\b",
            re.I,
        ),
        "Syntactic tell or hedged construction",
    ),
    Rule(
        "family6.verbosity_padding",
        6,
        re.compile(
            r"\b(?:made the decision|has the ability to|is able to|general feeling|primary reason was the fact|"
            r"communication with customers should be improved|at this point in time|provide an explanation|"
            r"conduct an analysis)\b",
            re.I,
        ),
        "Verbosity, nominalization, or padding",
    ),
    Rule(
        "family7.rhetorical_formula",
        7,
        re.compile(
            r"\b(?:not just\b.+\bbut\b|not only\b.+\bbut also\b|here's the thing|you know what|watch this|"
            r"what if i told you|let that sink in|plot twist|full stop|see what i did there|"
            r"\w+\s+\w+,\s+\w+\s+\w+,\s+and\s+\w+\s+\w+)\b",
            re.I | re.S,
        ),
        "Rhetorical formula or forced cadence",
    ),
    Rule(
        "family8.markdown_structure",
        8,
        re.compile(r"^\s*(?:---\s*$|#{3,}\s+|\|\s*[^|\n]+\s*\||[-*+]\s+\*\*[^*\n]+:\*\*)", re.M),
        "Mechanical structure or Markdown formatting tell",
    ),
    Rule(
        "family9.chatbot_residue",
        9,
        re.compile(
            r"\b(?:great question|here's a polished|i hope this helps|certainly|of course!|best regards|"
            r"let me know if|would you like me)\b",
            re.I,
        ),
        "Chatbot wrapper or collaborative residue",
    ),
]

AI_VOCAB = {
    "additionally",
    "align",
    "boasts",
    "bolstered",
    "cornerstone",
    "crucial",
    "delve",
    "emphasizing",
    "enduring",
    "enhance",
    "foster",
    "fostering",
    "garner",
    "highlight",
    "highlighting",
    "interplay",
    "intricate",
    "landscape",
    "leverage",
    "meticulous",
    "pivotal",
    "robust",
    "showcase",
    "showcasing",
    "tapestry",
    "testament",
    "underscore",
    "unlock",
    "valuable",
    "vibrant",
}

SOURCE_RISK_RULES = [
    Rule(
        "source_risk.citation_markup",
        None,
        re.compile(r"<ref\b|</ref>|{{\s*cite\b|\[\^[^\]]+\]|\[[^\]]+\]\(https?://[^)]+\)", re.I),
        "Citation markup or linked claim needs source verification",
        source_risk=True,
    ),
    Rule(
        "source_risk.bare_url",
        None,
        re.compile(r"https?://[^\s)>\]]+", re.I),
        "Bare URL or linked source needs verification",
        source_risk=True,
    ),
    Rule(
        "source_risk.source_dependent_statement",
        None,
        re.compile(
            r"\b(?:according to|reported|reports|study|studies|survey|records|cited|praised by|critics|"
            r"observers note|experts|researchers|national media|available sources)\b",
            re.I,
        ),
        "Source-dependent statement needs verification",
        source_risk=True,
    ),
]


def line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def line_column(starts: list[int], offset: int) -> tuple[int, int]:
    low = 0
    high = len(starts) - 1
    while low <= high:
        mid = (low + high) // 2
        if starts[mid] <= offset:
            low = mid + 1
        else:
            high = mid - 1
    line_index = max(0, high)
    return line_index + 1, offset - starts[line_index] + 1


def evidence(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip()
    if len(collapsed) <= 120:
        return collapsed
    return collapsed[:117] + "..."


def make_finding(rule: Rule, match: re.Match[str], starts: list[int]) -> dict[str, object]:
    line, column = line_column(starts, match.start())
    return {
        "id": rule.id,
        "family": rule.family,
        "severity": rule.severity,
        "line": line,
        "column": column,
        "evidence": evidence(match.group(0)),
        "message": rule.message,
        "source_risk": rule.source_risk,
    }


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)


def paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def sentences(text: str) -> list[str]:
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", body)
    return [part.strip() for part in parts if words(part)]


def coefficient_of_variation(lengths: list[int]) -> float:
    if not lengths:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.0
    variance = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    return math.sqrt(variance) / mean


def title_case_heading_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+)$", line)
        if not match:
            continue
        heading_words = [word for word in re.findall(r"[A-Za-z][A-Za-z'-]*", match.group(1)) if len(word) > 2]
        if heading_words and sum(word[:1].isupper() for word in heading_words) / len(heading_words) >= 0.6:
            count += 1
    return count


def stats_for(text: str) -> dict[str, int | float]:
    token_list = words(text)
    sentence_list = sentences(text)
    sentence_lengths = [len(words(sentence)) for sentence in sentence_list]
    word_count = len(token_list)
    unique_words = {word.lower() for word in token_list}
    return {
        "words": word_count,
        "sentences": len(sentence_list),
        "avg_sentence_words": round(sum(sentence_lengths) / len(sentence_lengths), 2) if sentence_lengths else 0,
        "sentence_length_cv": round(coefficient_of_variation(sentence_lengths), 2),
        "paragraphs": len(paragraphs(text)),
        "type_token_ratio": round(len(unique_words) / word_count, 2) if word_count else 0,
        "em_dash_count": text.count("—"),
        "heading_count": len(re.findall(r"^\s{0,3}#{1,6}\s+", text, re.M)),
        "title_case_heading_count": title_case_heading_count(text),
        "bold_marker_count": text.count("**"),
        "table_line_count": len(re.findall(r"^\s*\|.+\|\s*$", text, re.M)),
        "bullet_count": len(re.findall(r"^\s*[-*+]\s+", text, re.M)),
        "code_block_count": text.count("```") // 2,
    }


def regex_findings(text: str, rules: Iterable[Rule], starts: list[int]) -> list[dict[str, object]]:
    found = []
    for rule in rules:
        for match in rule.regex.finditer(text):
            found.append(make_finding(rule, match, starts))
    return found


def ai_vocab_findings(text: str, starts: list[int]) -> list[dict[str, object]]:
    found_terms = [(match.group(0).lower(), match.start()) for match in re.finditer(r"[A-Za-z][A-Za-z'-]*", text)]
    matched = [(term, offset) for term, offset in found_terms if term in AI_VOCAB]
    if len(matched) < 3:
        paragraph_hits = []
        cursor = 0
        for paragraph in paragraphs(text):
            start = text.find(paragraph, cursor)
            cursor = start + len(paragraph)
            terms = [term for term in re.findall(r"[A-Za-z][A-Za-z'-]*", paragraph.lower()) if term in AI_VOCAB]
            if len(terms) >= 2:
                paragraph_hits.append((sorted(set(terms)), start))
        if not paragraph_hits:
            return []
        terms, offset = paragraph_hits[0]
    else:
        terms = sorted({term for term, _offset in matched})
        offset = matched[0][1]

    line, column = line_column(starts, offset)
    return [
        {
            "id": "family4.ai_vocab_cluster",
            "family": 4,
            "severity": "warning",
            "line": line,
            "column": column,
            "evidence": ", ".join(terms[:12]),
            "message": "AI-vocabulary cluster",
            "source_risk": False,
        }
    ]


def rhythm_findings(stats: dict[str, int | float]) -> list[dict[str, object]]:
    findings = []
    if stats["sentences"] >= 4 and stats["sentence_length_cv"] <= 0.2:
        findings.append(
            {
                "id": "structure.low_sentence_variance",
                "family": 8,
                "severity": "info",
                "line": 1,
                "column": 1,
                "evidence": f"sentence_length_cv={stats['sentence_length_cv']}",
                "message": "Low sentence-length variance can read mechanically even",
                "source_risk": False,
            }
        )
    if stats["paragraphs"] >= 4 and stats["sentences"] and stats["avg_sentence_words"] >= 18:
        findings.append(
            {
                "id": "structure.long_uniform_paragraphs",
                "family": 8,
                "severity": "info",
                "line": 1,
                "column": 1,
                "evidence": f"paragraphs={stats['paragraphs']}, avg_sentence_words={stats['avg_sentence_words']}",
                "message": "Long regular paragraphs may need rhythm review",
                "source_risk": False,
            }
        )
    return findings


def risk_score(findings: list[dict[str, object]]) -> int:
    artifact_count = sum(1 for finding in findings if str(finding["id"]).startswith("artifact."))
    source_count = sum(1 for finding in findings if finding["source_risk"])
    family_count = sum(1 for finding in findings if str(finding["id"]).startswith("family"))
    family_coverage = {finding["family"] for finding in findings if str(finding["id"]).startswith("family")}
    formula_count = sum(1 for finding in findings if finding["id"] == "family7.rhetorical_formula")
    structure_count = sum(1 for finding in findings if str(finding["id"]).startswith("structure."))
    score = 0
    score += min(40, artifact_count * 10)
    score += min(30, family_count * 5)
    score += min(20, source_count * 4)
    score += min(10, structure_count * 5)
    if len(family_coverage) >= 5 or family_count >= 10 or formula_count >= 3 or (source_count and family_count >= 6):
        score = max(score, 60)
    return min(100, score)


def audit_text(text: str, path: str) -> dict[str, object]:
    starts = line_starts(text)
    stats = stats_for(text)
    findings = []
    findings.extend(regex_findings(text, ARTIFACT_RULES, starts))
    findings.extend(regex_findings(text, FAMILY_RULES, starts))
    findings.extend(ai_vocab_findings(text, starts))
    findings.extend(regex_findings(text, SOURCE_RISK_RULES, starts))
    findings.extend(rhythm_findings(stats))
    findings.sort(key=lambda item: (int(item["line"]), int(item["column"]), str(item["id"])))
    return {
        "path": path,
        "risk_score": risk_score(findings),
        "stats": stats,
        "findings": findings,
    }


def severity_for(findings: list[dict[str, object]]) -> str:
    if not findings:
        return "info"
    return max((str(finding["severity"]) for finding in findings), key=lambda value: SEVERITY_ORDER[value])


def summarize(documents: list[dict[str, object]], fail_score: int) -> dict[str, object]:
    all_findings = [finding for document in documents for finding in document["findings"]]
    max_risk = max((int(document["risk_score"]) for document in documents), default=0)
    max_severity = severity_for(all_findings)
    has_error = any(finding["severity"] == "error" for finding in all_findings)
    exit_code = 2 if has_error else 1 if max_risk >= fail_score else 0
    return {
        "documents": len(documents),
        "max_risk_score": max_risk,
        "max_severity": max_severity,
        "artifact_count": sum(1 for finding in all_findings if str(finding["id"]).startswith("artifact.")),
        "source_risk_count": sum(1 for finding in all_findings if finding["source_risk"]),
        "family_hit_count": sum(1 for finding in all_findings if str(finding["id"]).startswith("family")),
        "exit_code": exit_code,
    }


def iter_input_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(path for path in target.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"})
    raise FileNotFoundError(f"No such file or directory: {target}")


def audit_paths(paths: list[Path]) -> list[dict[str, object]]:
    documents = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        documents.append(audit_text(text, str(path)))
    return documents


def render_text_report(result: dict[str, object]) -> str:
    lines = []
    summary = result["summary"]
    lines.append(
        f"Humanizer audit: {summary['documents']} document(s), max risk {summary['max_risk_score']}, "
        f"severity {summary['max_severity']}, exit {summary['exit_code']}"
    )
    for document in result["documents"]:
        lines.append("")
        lines.append(f"{document['path']} — risk {document['risk_score']}")
        for finding in document["findings"]:
            lines.append(
                f"  {finding['severity'].upper()} L{finding['line']}:C{finding['column']} "
                f"{finding['id']} — {finding['message']} [{finding['evidence']}]"
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit text for Humanizer Pro tells and source-risk artifacts.")
    parser.add_argument("target", nargs="?", help="File or directory to audit.")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin instead of a path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    parser.add_argument("--fail-score", type=int, default=60, help="Risk score that exits with review status 1.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stdin == bool(args.target):
        parser.error("provide exactly one input: <file-or-dir> or --stdin")
    try:
        if args.stdin:
            documents = [audit_text(sys.stdin.read(), "<stdin>")]
        else:
            documents = audit_paths(iter_input_files(Path(args.target)))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"humanizer-audit: {exc}", file=sys.stderr)
        return 3

    summary = summarize(documents, args.fail_score)
    result = {"schema": SCHEMA, "summary": summary, "documents": documents}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text_report(result))
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
