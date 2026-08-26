#!/usr/bin/env python3
"""Deterministic audit CLI for Humanizer Pro."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA = "humanizer-audit.v1"
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

AI_REFERRER_HOSTS = {
    "chatgpt.com",
    "claude.ai",
    "copilot.com",
    "grok.com",
    "openai",
    "perplexity.ai",
}

ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿]")
HOMOGLYPH_LATIN = {
    # Cyrillic lookalikes
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "к": "k", "м": "m", "н": "h", "в": "b", "т": "t",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "Х": "X",
    "У": "Y", "К": "K", "М": "M", "Н": "H", "В": "B", "Т": "T",
    # Greek lookalikes
    "ο": "o", "Ο": "O", "α": "a", "Α": "A", "ρ": "p", "Ρ": "P",
}
WORD_WITH_HOMOGLYPH_RE = re.compile(
    "[A-Za-z{h}]*[A-Za-z][A-Za-z{h}]*".format(h="".join(HOMOGLYPH_LATIN))
)


@dataclass(frozen=True)
class Rule:
    id: str
    family: int | None
    regex: re.Pattern[str]
    message: str
    severity: str = "warning"
    source_risk: bool = False


@dataclass(frozen=True)
class ProtectedToken:
    kind: str
    value: str
    evidence: str
    offset: int


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
        "artifact.ai_tracking_url",
        9,
        re.compile(
            r"[?&](?:utm_source=(?:chatgpt\.com|claude\.ai|copilot\.com|openai|perplexity\.ai)"
            r"|referrer=grok\.com)",
            re.I,
        ),
        "AI-tool tracking parameter in URL",
        "error",
        True,
    ),
    Rule(
        "artifact.roleplay_marker",
        9,
        re.compile(
            r"(?<!\*)\*(?:nods|sighs|laughs|smiles|frowns|shrugs|grins|winks|chuckles|gasps|"
            r"pauses|whispers|shouts|glances|smirks|blinks)(?:[^*\n]{0,60})?\*(?!\*)",
            re.I,
        ),
        "Chat roleplay action marker leaked into text",
        "error",
        False,
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
        "family2.speculative_gap_filling",
        2,
        re.compile(
            r"\b(?:is|was|are|were)\s+(?:widely\s+)?believed\s+to\s+have\b|"
            r"\blikely\s+(?:began|started|joined|studied|served|worked)\b|"
            r"\bappears?\s+to\s+have\s+(?:been|begun|studied|worked|served)\b|"
            r"\bmaintains\s+a\s+relatively\s+low\s+(?:public\s+)?profile\b",
            re.I,
        ),
        "Speculative gap-filling presented as fact",
        source_risk=True,
    ),
    Rule(
        "family2.vague_validation",
        2,
        re.compile(
            r"\b(?:independent\s+(?:testing|tests|analysis|audits?)\s+(?:confirm|confirms|show|shows|validate|validates)|"
            r"third-party\s+benchmarks?\s+(?:show|confirm|place|put)|"
            r"analysts\s+(?:agree|say|note|believe)|"
            r"studies\s+consistently\s+show)\b",
            re.I,
        ),
        "Unnamed third-party validation",
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
        "family8.list_label_period",
        8,
        re.compile(r"^\s*[-*+]\s+\*\*[^*\n]{1,40}?\.\*\*\s+\S", re.M),
        "List label ends with a period instead of a colon",
    ),
    Rule(
        "family9.chatbot_residue",
        9,
        re.compile(
            r"\b(?:great question|here's a polished|i hope this helps|certainly|of course!|best regards|"
            r"let me know if|would you like me|let me walk you through|here's how i'd think about|"
            r"while i understand the appeal|as of my (?:last|training) (?:update|cutoff)|"
            r"on the one hand\b.{0,120}\bon the other)\b",
            re.I,
        ),
        "Chatbot wrapper or collaborative residue",
    ),
]

# Tier 1A: words reported far more frequent in machine text than human text. The
# frequency claim is inherited from the source catalogs, not measured here; a
# cluster of these is still the strongest vocabulary evidence this CLI has.
AI_VOCAB_TIER1 = {
    "delve",
    "emphasizing",
    "enduring",
    "garner",
    "interplay",
    "intricate",
    "landscape",
    "meticulous",
    "pivotal",
    "robust",
    "showcase",
    "showcasing",
    "tapestry",
    "testament",
    "underscore",
    "vibrant",
}

# Tier 2: legitimate on their own; evidence only in clusters.
AI_VOCAB_TIER2 = {
    "additionally",
    "align",
    "boasts",
    "bolstered",
    "cornerstone",
    "crucial",
    "enhance",
    "foster",
    "fostering",
    "highlight",
    "highlighting",
    "leverage",
    "unlock",
    "valuable",
}

AI_VOCAB = AI_VOCAB_TIER1 | AI_VOCAB_TIER2

# Tier 1B: wordiness and register inflation. Replacing these is good writing
# regardless of who wrote the sentence, so they are reported as clarity edits,
# carry no tell family, and contribute nothing to the risk score — a wordiness
# fix must never push a document toward an AI classification.
CLARITY_RULES = [
    Rule(
        "clarity.wordiness",
        None,
        re.compile(
            r"\b(?:utiliz(?:e|es|ed|ing|ation)|commenc(?:e|es|ed|ing)|"
            r"facilitat(?:e|es|ed|ing)|endeavor(?:s|ed|ing)?|ascertain(?:s|ed|ing)?|"
            # Multi-word wrappers around a one-word meaning (HH). "due to the
            # fact that" stays family3-only; listing it here too would
            # double-count one phrase across tiers.
            r"in the event that|for the purpose of|"
            r"with regard to|with respect to|in light of the fact that|"
            r"despite the fact that|has the ability to)\b",
            re.I,
        ),
        "Inflated register (a clarity edit, not authorship evidence)",
        "info",
    ),
]

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

CODE_BLOCK_RE = re.compile(r"```[^\n`]*(?:\n.*?)?```", re.S)
URL_RE = re.compile(r"https?://[^\s<>\]\)\"'|{}]+", re.I)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\s]+(?:\s+\"[^\"]*\")?)\)")
FOOTNOTE_REF_RE = re.compile(r"\[\^[^\]\n]+\]")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]\n]+\]:.*$", re.M)
REF_TAG_RE = re.compile(r"<ref\b[^>]*(?:/>|>.*?</ref>)", re.I | re.S)
CITE_TEMPLATE_RE = re.compile(r"{{\s*cite\b.*?}}", re.I | re.S)
QUOTE_RE = re.compile(r'"[^"\n]{3,}"|“[^”\n]{3,}”')
BLOCKQUOTE_RE = re.compile(r"^(?:>\s?.+(?:\n|$))+", re.M)
DATE_RE = re.compile(
    r"\b(?:20XX|\d{4}-(?:\d{2}|XX)-(?:\d{2}|XX)|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
    r"\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
    r"\d{4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{4}|"
    r"(?:1[6-9]\d{2}|20\d{2}|21\d{2}))\b",
    re.I,
)
CURRENCY_RE = re.compile(
    r"(?:[$€£]|USD|EUR|GBP)\s?\d[\d,]*(?:\.\d+)?"
    r"(?:\s?(?:million|billion|trillion|thousand|m|bn|k))?",
    re.I,
)
PERCENT_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?%")
RANGE_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:-|–|—|to)\s*\d[\d,]*(?:\.\d+)?\b", re.I)
NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
NAME_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9'.&-]+(?:\s+(?:of|the|and|for|de|del|la|le|du|van|von|&|"
    r"[A-Z][A-Za-z0-9'.&-]+)){1,}",
)
ORG_HINT_RE = re.compile(
    r"\b(?:Agency|Association|Bureau|Committee|Commission|Company|Corporation|Council|Department|"
    r"Foundation|Group|Institute|LLC|Ltd|Ministry|Office|Organization|Research|University)\b"
)
SOURCE_MARKER_RE = re.compile(
    r"https?://|<ref\b|{{\s*cite\b|\[\^[^\]]+\]|\[[^\]]+\]\(|"
    r"\b(?:according to|reported|reports|study|studies|survey|records|cited|evidence|data|"
    r"researchers|observers|experts|said|announced|published|filed)\b",
    re.I,
)
REPORTING_LANGUAGE_RE = re.compile(
    r"\b(?:according to|reported|reports|study|studies|survey|records|cited|evidence|data|"
    r"researchers|observers|experts|said|announced|published|filed)\b",
    re.I,
)
NAME_CONNECTORS = {"and", "de", "del", "du", "for", "la", "le", "of", "the", "van", "von"}
NAME_EXCLUDE_START = {"A", "An", "As", "At", "By", "For", "From", "If", "In", "It", "On", "Or", "The", "This", "To"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "with",
}


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


def regex_spans(text: str, regex: re.Pattern[str]) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in regex.finditer(text)]


def blank_spans(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(start, min(end, len(chars))):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(raw_url: str) -> str:
    trimmed = raw_url.strip().rstrip(").,;:!?")
    parsed = urlsplit(trimmed)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and not (key.lower() == "referrer" and value.lower() in AI_REFERRER_HOSTS)
        ],
        doseq=True,
    )
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, query, parsed.fragment))


def normalize_bypass_text(text: str) -> tuple[str, dict[str, int], int]:
    """Undo detector-bypass tricks before pattern matching.

    Returns (normalized_text, counts, first_offset). Zero-width characters are
    removed (a single leading BOM is ordinary file encoding, not a trick, and is
    exempt); Cyrillic/Greek Latin-lookalike characters are mapped back to Latin
    only inside mixed-script words, so genuine Cyrillic or Greek prose is never
    rewritten. Findings that follow are located in the normalized text: line
    numbers are unaffected, columns can shift only on lines that contained
    zero-width characters.
    """
    counts = {"zero_width": 0, "homoglyph": 0}
    first_offset = -1
    lead_bom = text.startswith("﻿")
    body = text[1:] if lead_bom else text
    offset_base = 1 if lead_bom else 0

    for match in ZERO_WIDTH_RE.finditer(body):
        counts["zero_width"] += 1
        if first_offset < 0:
            first_offset = match.start() + offset_base

    def swap_word(match: re.Match[str]) -> str:
        nonlocal first_offset
        word = match.group(0)
        if not any(char in HOMOGLYPH_LATIN for char in word):
            return word
        counts["homoglyph"] += sum(1 for char in word if char in HOMOGLYPH_LATIN)
        if first_offset < 0 or match.start() + offset_base < first_offset:
            first_offset = match.start() + offset_base
        return "".join(HOMOGLYPH_LATIN.get(char, char) for char in word)

    normalized = WORD_WITH_HOMOGLYPH_RE.sub(swap_word, body)
    normalized = ZERO_WIDTH_RE.sub("", normalized)
    if lead_bom:
        normalized = "﻿" + normalized
    return normalized, counts, first_offset


def normalize_citation(value: str) -> str:
    normalized = URL_RE.sub(lambda match: normalize_url(match.group(0)), value)
    return normalize_space(normalized).lower()


def normalize_date(value: str) -> str:
    return normalize_space(value.replace(",", "")).lower()


def normalize_number(value: str) -> str:
    normalized = normalize_space(value).lower().replace(",", "")
    return re.sub(r"\s*(?:-|–|—|to)\s*", "-", normalized)


def normalize_name(value: str) -> str:
    return normalize_space(value).strip(".,:;").lower()


def normalize_quote(value: str) -> str:
    return normalize_space(value)


def citation_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for regex in (MARKDOWN_LINK_RE, FOOTNOTE_DEF_RE, FOOTNOTE_REF_RE, REF_TAG_RE, CITE_TEMPLATE_RE):
        spans.extend(regex_spans(text, regex))
    return spans


def masked_for_prose(text: str) -> str:
    return blank_spans(text, regex_spans(text, CODE_BLOCK_RE) + citation_spans(text) + regex_spans(text, URL_RE))


def token_from_match(kind: str, match: re.Match[str], value: str | None = None) -> ProtectedToken:
    raw = match.group(0)
    return ProtectedToken(kind, value if value is not None else normalize_space(raw), evidence(raw), match.start())


def extract_url_tokens(text: str) -> list[ProtectedToken]:
    return [
        token_from_match("url", match, normalize_url(match.group(0)))
        for match in URL_RE.finditer(blank_spans(text, regex_spans(text, CODE_BLOCK_RE)))
    ]


def extract_date_tokens(text: str) -> list[ProtectedToken]:
    masked = masked_for_prose(text)
    return [token_from_match("date", match, normalize_date(match.group(0))) for match in DATE_RE.finditer(masked)]


def extract_number_tokens(text: str) -> list[ProtectedToken]:
    masked = blank_spans(masked_for_prose(text), regex_spans(masked_for_prose(text), DATE_RE))
    tokens = []
    occupied: list[tuple[int, int]] = []
    for regex in (CURRENCY_RE, PERCENT_RE, RANGE_RE):
        for match in regex.finditer(blank_spans(masked, occupied)):
            tokens.append(token_from_match("number", match, normalize_number(match.group(0))))
            occupied.append((match.start(), match.end()))
    for match in NUMBER_RE.finditer(blank_spans(masked, occupied)):
        tokens.append(token_from_match("number", match, normalize_number(match.group(0))))
    return tokens


def extract_name_tokens(text: str) -> list[ProtectedToken]:
    prose = masked_for_prose(text)
    masked_lines = []
    for line in prose.splitlines(keepends=True):
        if not line.lstrip().startswith("#"):
            masked_lines.append(line)
            continue
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        masked_lines.append(" " * len(body) + newline)
    prose = "".join(masked_lines)
    tokens = []
    for match in NAME_RE.finditer(prose):
        raw = normalize_space(match.group(0))
        words_in_name = re.findall(r"[A-Za-z][A-Za-z0-9'.&-]*", raw)
        semantic_words = [word for word in words_in_name if word.lower() not in NAME_CONNECTORS]
        if len(semantic_words) < 2:
            continue
        if semantic_words[0] in NAME_EXCLUDE_START and not ORG_HINT_RE.search(raw):
            continue
        tokens.append(ProtectedToken("name", normalize_name(raw), evidence(raw), match.start()))
    return tokens


def extract_citation_tokens(text: str) -> list[ProtectedToken]:
    masked = blank_spans(text, regex_spans(text, CODE_BLOCK_RE))
    tokens = []
    for match in MARKDOWN_LINK_RE.finditer(masked):
        label = normalize_space(match.group(1)).lower()
        target = normalize_url(match.group(2).split()[0])
        tokens.append(ProtectedToken("citation", f"markdown:{label}->{target}", evidence(match.group(0)), match.start()))
    for regex, prefix in (
        (FOOTNOTE_DEF_RE, "footnote_def"),
        (FOOTNOTE_REF_RE, "footnote_ref"),
        (REF_TAG_RE, "ref"),
        (CITE_TEMPLATE_RE, "cite"),
    ):
        for match in regex.finditer(masked):
            tokens.append(
                ProtectedToken("citation", f"{prefix}:{normalize_citation(match.group(0))}", evidence(match.group(0)), match.start())
            )
    return tokens


def extract_quote_tokens(text: str) -> list[ProtectedToken]:
    masked = blank_spans(text, regex_spans(text, CODE_BLOCK_RE))
    tokens = [token_from_match("quote", match, normalize_quote(match.group(0))) for match in QUOTE_RE.finditer(masked)]
    for match in BLOCKQUOTE_RE.finditer(masked):
        tokens.append(token_from_match("quote", match, normalize_quote(match.group(0))))
    return tokens


def extract_code_block_tokens(text: str) -> list[ProtectedToken]:
    tokens = []
    for match in CODE_BLOCK_RE.finditer(text):
        block = match.group(0)
        digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
        first_line = block.splitlines()[0] if block.splitlines() else "```"
        tokens.append(ProtectedToken("code_block", digest, evidence(first_line), match.start()))
    return tokens


def compare_finding(
    finding_id: str,
    message: str,
    token: ProtectedToken,
    starts: list[int],
    side: str,
    source_risk: bool = False,
) -> dict[str, object]:
    line, column = line_column(starts, token.offset)
    return {
        "id": finding_id,
        "family": None,
        "severity": "error",
        "line": line,
        "column": column,
        "evidence": token.evidence,
        "message": message,
        "source_risk": source_risk,
        "side": side,
    }


def token_buckets(tokens: list[ProtectedToken]) -> dict[str, list[ProtectedToken]]:
    buckets: dict[str, list[ProtectedToken]] = {}
    for token in tokens:
        buckets.setdefault(token.value, []).append(token)
    return buckets


def compare_token_sets(
    kind: str,
    original_tokens: list[ProtectedToken],
    revised_tokens: list[ProtectedToken],
    original_starts: list[int],
    revised_starts: list[int],
) -> list[dict[str, object]]:
    labels = {
        "citation": "citation marker",
        "date": "date",
        "name": "name",
        "number": "number",
        "url": "URL target",
    }
    source_kinds = {"citation", "url"}
    original_counts = Counter(token.value for token in original_tokens)
    revised_counts = Counter(token.value for token in revised_tokens)
    original_buckets = token_buckets(original_tokens)
    revised_buckets = token_buckets(revised_tokens)
    findings = []
    for value, count in (original_counts - revised_counts).items():
        for token in original_buckets[value][:count]:
            findings.append(
                compare_finding(
                    f"compare.{kind}.dropped",
                    f"Dropped protected {labels[kind]}",
                    token,
                    original_starts,
                    "original",
                    kind in source_kinds,
                )
            )
    for value, count in (revised_counts - original_counts).items():
        for token in revised_buckets[value][:count]:
            findings.append(
                compare_finding(
                    f"compare.{kind}.introduced",
                    f"Introduced protected {labels[kind]}",
                    token,
                    revised_starts,
                    "revised",
                    kind in source_kinds,
                )
            )
    return findings


def markdown_link_targets(text: str) -> dict[str, ProtectedToken]:
    masked = blank_spans(text, regex_spans(text, CODE_BLOCK_RE))
    targets = {}
    for match in MARKDOWN_LINK_RE.finditer(masked):
        label = normalize_space(match.group(1)).lower()
        target = normalize_url(match.group(2).split()[0])
        targets[label] = ProtectedToken("citation", target, evidence(match.group(0)), match.start())
    return targets


def compare_markdown_targets(
    original_text: str,
    revised_text: str,
    original_starts: list[int],
) -> list[dict[str, object]]:
    original_links = markdown_link_targets(original_text)
    revised_links = markdown_link_targets(revised_text)
    findings = []
    for label, original_token in original_links.items():
        revised_token = revised_links.get(label)
        if revised_token and revised_token.value != original_token.value:
            findings.append(
                compare_finding(
                    "compare.citation.changed_target",
                    f"Changed Markdown link target for [{label}]",
                    original_token,
                    original_starts,
                    "original",
                    True,
                )
            )
    return findings


def compare_ordered_tokens(
    kind: str,
    original_tokens: list[ProtectedToken],
    revised_tokens: list[ProtectedToken],
    original_starts: list[int],
    revised_starts: list[int],
) -> list[dict[str, object]]:
    changed_messages = {
        "code_block": "Changed fenced code block",
        "quote": "Changed quoted text or blockquote",
    }
    findings = []
    for original_token, revised_token in zip(original_tokens, revised_tokens, strict=False):
        if original_token.value != revised_token.value:
            findings.append(
                compare_finding(
                    f"compare.{kind}.changed",
                    changed_messages[kind],
                    original_token,
                    original_starts,
                    "original",
                    False,
                )
            )
    if len(original_tokens) > len(revised_tokens):
        for token in original_tokens[len(revised_tokens) :]:
            findings.append(
                compare_finding(
                    f"compare.{kind}.dropped",
                    f"Dropped protected {kind.replace('_', ' ')}",
                    token,
                    original_starts,
                    "original",
                    False,
                )
            )
    elif len(revised_tokens) > len(original_tokens):
        for token in revised_tokens[len(original_tokens) :]:
            findings.append(
                compare_finding(
                    f"compare.{kind}.introduced",
                    f"Introduced protected {kind.replace('_', ' ')}",
                    token,
                    revised_starts,
                    "revised",
                    False,
                )
            )
    return findings


def sentence_records(text: str) -> list[dict[str, object]]:
    records = []
    pattern = re.compile(r".+?(?:(?<=[.!?])\s+(?=[A-Z0-9\"“'])|\n{2,}|$)", re.S)
    for match in pattern.finditer(text):
        sentence = match.group(0).strip()
        if not sentence or not SOURCE_MARKER_RE.search(sentence):
            continue
        records.append(
            {
                "text": sentence,
                "normalized": normalize_sentence(sentence),
                "terms": meaningful_terms(sentence),
                "markers": evidence_markers(sentence),
                "offset": match.start() + len(match.group(0)) - len(match.group(0).lstrip()),
            }
        )
    return records


def normalize_sentence(sentence: str) -> str:
    normalized = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), sentence)
    normalized = URL_RE.sub(" ", normalized)
    normalized = REF_TAG_RE.sub(" ", normalized)
    normalized = CITE_TEMPLATE_RE.sub(" ", normalized)
    normalized = FOOTNOTE_REF_RE.sub(" ", normalized)
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def meaningful_terms(sentence: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", normalize_sentence(sentence))
        if len(term) > 2 and term not in STOPWORDS
    }


def evidence_markers(sentence: str) -> set[str]:
    markers = set()
    if URL_RE.search(sentence):
        markers.add("url")
    if MARKDOWN_LINK_RE.search(sentence):
        markers.add("markdown_link")
    if REF_TAG_RE.search(sentence):
        markers.add("ref")
    if CITE_TEMPLATE_RE.search(sentence):
        markers.add("cite_template")
    if FOOTNOTE_REF_RE.search(sentence):
        markers.add("footnote")
    if REPORTING_LANGUAGE_RE.search(sentence):
        markers.add("reporting_language")
    return markers


def overlap_score(left_terms: set[str], right_terms: set[str]) -> float:
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def best_sentence_match(record: dict[str, object], candidates: list[dict[str, object]]) -> tuple[dict[str, object] | None, float]:
    best_record = None
    best_score = 0.0
    for candidate in candidates:
        score = overlap_score(set(record["terms"]), set(candidate["terms"]))
        if score > best_score:
            best_score = score
            best_record = candidate
    return best_record, best_score


def source_statement_token(record: dict[str, object]) -> ProtectedToken:
    return ProtectedToken("source_statement", str(record["normalized"]), evidence(str(record["text"])), int(record["offset"]))


def compare_source_statements(
    original_text: str,
    revised_text: str,
    original_starts: list[int],
    revised_starts: list[int],
) -> list[dict[str, object]]:
    original_records = sentence_records(original_text)
    revised_records = sentence_records(revised_text)
    revised_norms = {record["normalized"] for record in revised_records}
    original_norms = {record["normalized"] for record in original_records}
    findings = []
    for record in original_records:
        if record["normalized"] in revised_norms:
            continue
        candidate, score = best_sentence_match(record, revised_records)
        token = source_statement_token(record)
        if candidate and score >= 0.4:
            dropped_markers = set(record["markers"]) - set(candidate["markers"])
            if dropped_markers:
                findings.append(
                    compare_finding(
                        "compare.source_statement.evidence_marker_dropped",
                        "Source-dependent sentence changed without preserving its evidence marker",
                        token,
                        original_starts,
                        "original",
                        True,
                    )
                )
        else:
            findings.append(
                compare_finding(
                    "compare.source_statement.dropped",
                    "Dropped source-dependent statement",
                    token,
                    original_starts,
                    "original",
                    True,
                )
            )
    for record in revised_records:
        if record["normalized"] in original_norms:
            continue
        candidate, score = best_sentence_match(record, original_records)
        if not candidate or score < 0.4:
            findings.append(
                compare_finding(
                    "compare.source_statement.introduced",
                    "Introduced source-dependent statement",
                    source_statement_token(record),
                    revised_starts,
                    "revised",
                    True,
                )
            )
    return findings


def compare_texts(original_text: str, revised_text: str, original_path: str, revised_path: str) -> dict[str, object]:
    original_starts = line_starts(original_text)
    revised_starts = line_starts(revised_text)
    findings: list[dict[str, object]] = []
    findings.extend(compare_markdown_targets(original_text, revised_text, original_starts))
    for kind, extractor in (
        ("number", extract_number_tokens),
        ("date", extract_date_tokens),
        ("name", extract_name_tokens),
        ("url", extract_url_tokens),
        ("citation", extract_citation_tokens),
    ):
        findings.extend(compare_token_sets(kind, extractor(original_text), extractor(revised_text), original_starts, revised_starts))
    findings.extend(
        compare_ordered_tokens(
            "quote",
            extract_quote_tokens(original_text),
            extract_quote_tokens(revised_text),
            original_starts,
            revised_starts,
        )
    )
    findings.extend(
        compare_ordered_tokens(
            "code_block",
            extract_code_block_tokens(original_text),
            extract_code_block_tokens(revised_text),
            original_starts,
            revised_starts,
        )
    )
    findings.extend(compare_source_statements(original_text, revised_text, original_starts, revised_starts))
    findings.sort(key=lambda item: (str(item["side"]), int(item["line"]), int(item["column"]), str(item["id"])))
    return {
        "original": original_path,
        "revised": revised_path,
        "findings": findings,
    }


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


def max_uniform_run(sentence_lengths: list[int]) -> int:
    """Longest run of consecutive sentences whose lengths stay within 5 words."""
    best = run_start = 0
    for index in range(len(sentence_lengths)):
        window = sentence_lengths[run_start : index + 1]
        while max(window) - min(window) > 5:
            run_start += 1
            window = sentence_lengths[run_start : index + 1]
        best = max(best, index - run_start + 1)
    return best


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
        "sentence_length_range": (max(sentence_lengths) - min(sentence_lengths)) if sentence_lengths else 0,
        "midband_sentence_share": round(
            sum(1 for length in sentence_lengths if 10 <= length <= 20) / len(sentence_lengths), 2
        ) if sentence_lengths else 0,
        "max_uniform_run": max_uniform_run(sentence_lengths),
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
    tier1_terms = {term for term, _offset in matched if term in AI_VOCAB_TIER1}
    if len(matched) < 3 and len(tier1_terms) < 2:
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
    # Threshold calibrated against the human-control corpus (corpus/RESULTS.md):
    # >=4 fires on 40% of human documents, >=6 on 11% — comparable to the other
    # structure signals. Info severity either way; this is a rhythm nudge.
    if stats["max_uniform_run"] >= 6:
        findings.append(
            {
                "id": "structure.uniform_length_run",
                "family": 8,
                "severity": "info",
                "line": 1,
                "column": 1,
                "evidence": f"max_uniform_run={stats['max_uniform_run']}",
                "message": "Run of consecutive sentences within 5 words of each other",
                "source_risk": False,
            }
        )
    if (
        stats["sentences"] >= 8
        and stats["midband_sentence_share"] >= 0.6
        and stats["sentence_length_range"] < 20
    ):
        findings.append(
            {
                "id": "structure.midband_dominance",
                "family": 8,
                "severity": "info",
                "line": 1,
                "column": 1,
                "evidence": (
                    f"midband_sentence_share={stats['midband_sentence_share']}, "
                    f"sentence_length_range={stats['sentence_length_range']}"
                ),
                "message": "Most sentences sit in the 10-20 word band with a narrow range",
                "source_risk": False,
            }
        )
    return findings


ANAPHORA_SKIP_WORDS = {
    "the", "a", "an", "it", "i", "in", "this", "that", "he", "she", "they", "we", "you",
}


def anaphora_findings(text: str) -> list[dict[str, object]]:
    """Three or more consecutive sentences opening with the same word (§7.13)."""
    openers = []
    for sentence in sentences(text):
        tokens = words(sentence)
        openers.append(tokens[0].lower() if tokens else "")
    findings = []
    index = 0
    while index < len(openers):
        run = 1
        while index + run < len(openers) and openers[index + run] == openers[index]:
            run += 1
        opener = openers[index]
        if run >= 3 and opener and opener not in ANAPHORA_SKIP_WORDS:
            findings.append(
                {
                    "id": "structure.anaphora",
                    "family": 8,
                    "severity": "info",
                    "line": 1,
                    "column": 1,
                    "evidence": f"opener='{opener}' x{run} consecutive sentences",
                    "message": "Consecutive sentences share the same opening word",
                    "source_risk": False,
                }
            )
        index += run
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


def bypass_findings(counts: dict[str, int], first_offset: int, starts: list[int]) -> list[dict[str, object]]:
    total = counts["zero_width"] + counts["homoglyph"]
    if total == 0:
        return []
    line, column = line_column(starts, max(first_offset, 0))
    return [
        {
            "id": "artifact.bypass_characters",
            "family": 9,
            "severity": "error",
            "line": line,
            "column": column,
            "evidence": f"zero_width={counts['zero_width']}, homoglyph={counts['homoglyph']}",
            "message": "Zero-width or homoglyph characters consistent with detector-bypass tricks",
            "source_risk": False,
        }
    ]


def audit_text(text: str, path: str) -> dict[str, object]:
    original_starts = line_starts(text)
    text, bypass_counts, bypass_offset = normalize_bypass_text(text)
    starts = line_starts(text)
    stats = stats_for(text)
    findings = []
    findings.extend(bypass_findings(bypass_counts, bypass_offset, original_starts))
    findings.extend(regex_findings(text, ARTIFACT_RULES, starts))
    findings.extend(regex_findings(text, FAMILY_RULES, starts))
    findings.extend(ai_vocab_findings(text, starts))
    findings.extend(regex_findings(text, SOURCE_RISK_RULES, starts))
    findings.extend(regex_findings(text, CLARITY_RULES, starts))
    findings.extend(rhythm_findings(stats))
    findings.extend(anaphora_findings(text))
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
        "clarity_hit_count": sum(1 for finding in all_findings if str(finding["id"]).startswith("clarity.")),
        "exit_code": exit_code,
    }


def summarize_compare(compare: dict[str, object]) -> dict[str, object]:
    findings = list(compare["findings"])
    exit_code = 2 if findings else 0
    return {
        "documents": 2,
        "comparisons": 1,
        "max_risk_score": 0,
        "max_severity": severity_for(findings),
        "artifact_count": 0,
        "source_risk_count": sum(1 for finding in findings if finding["source_risk"]),
        "family_hit_count": 0,
        "compare_finding_count": len(findings),
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


def compare_paths(original_path: Path, revised_path: Path) -> dict[str, object]:
    original_text = original_path.read_text(encoding="utf-8")
    revised_text = revised_path.read_text(encoding="utf-8")
    return compare_texts(original_text, revised_text, str(original_path), str(revised_path))


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


def render_compare_report(result: dict[str, object]) -> str:
    summary = result["summary"]
    compare = result["compare"]
    lines = [
        f"Humanizer compare: {compare['original']} -> {compare['revised']}, "
        f"{summary['compare_finding_count']} finding(s), severity {summary['max_severity']}, "
        f"exit {summary['exit_code']}"
    ]
    for finding in compare["findings"]:
        lines.append(
            f"  {finding['severity'].upper()} {finding['side']} L{finding['line']}:C{finding['column']} "
            f"{finding['id']} — {finding['message']} [{finding['evidence']}]"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit text for Humanizer Pro tells and source-risk artifacts.")
    parser.add_argument("target", nargs="?", help="File or directory to audit.")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin instead of a path.")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("ORIGINAL", "REVISED"),
        help="Compare an original and revised file for protected-content drift.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    parser.add_argument("--fail-score", type=int, default=60, help="Risk score that exits with review status 1.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if sum(1 for active in (args.stdin, bool(args.target), bool(args.compare)) if active) != 1:
        parser.error("provide exactly one input: <file-or-dir>, --stdin, or --compare ORIGINAL REVISED")
    try:
        if args.compare:
            compare = compare_paths(Path(args.compare[0]), Path(args.compare[1]))
            summary = summarize_compare(compare)
            result = {"schema": SCHEMA, "summary": summary, "documents": [], "compare": compare}
        elif args.stdin:
            documents = [audit_text(sys.stdin.read(), "<stdin>")]
            summary = summarize(documents, args.fail_score)
            result = {"schema": SCHEMA, "summary": summary, "documents": documents}
        else:
            documents = audit_paths(iter_input_files(Path(args.target)))
            summary = summarize(documents, args.fail_score)
            result = {"schema": SCHEMA, "summary": summary, "documents": documents}
    except (OSError, UnicodeDecodeError) as exc:
        print(f"humanizer-audit: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.compare:
        print(render_compare_report(result))
    else:
        print(render_text_report(result))
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
