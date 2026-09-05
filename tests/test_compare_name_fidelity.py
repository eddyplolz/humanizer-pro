"""Protected-name compare: a capital at a sentence head is grammar, not a name.

Two failure modes these pin, both measured on a real encyclopedia de-slop pass:

1. A sentence-initial capital was read as a proper noun, so removing a banned
   opening transition, fixing a determiner, or deleting a leading connective
   (which recapitalizes the next word) all reported dropped or introduced
   protected names.
2. Names were compared as a multiset, so trimming one of dozens of mentions of
   an article's own subject reported a dropped name even though the referent is
   still named throughout.

The value being protected is the referent, not the occurrence count. A name that
disappears from the revised text entirely must still be reported.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import humanizer_audit as H  # noqa: E402


def name_findings(original: str, revised: str) -> list[dict]:
    result = H.compare_texts(original, revised, "original.txt", "revised.txt")
    return [
        item
        for item in result["findings"]
        if str(item.get("id", "")).startswith("compare.name.")
    ]


def evidences(original: str, revised: str) -> set[str]:
    return {str(item.get("evidence")) for item in name_findings(original, revised)}


# --- direction (a): sentence-initial capitals are not names ----------------


def test_deleting_a_leading_connective_does_not_move_a_name():
    original = (
        "Performers have brought stories from Hato Rey to life. "
        "Additionally, comedian Luis Vilgarde has captured the hearts of many."
    )
    revised = (
        "Performers have brought stories from Hato Rey to life. "
        "Comedian Luis Vilgarde has also captured the hearts of many."
    )
    assert name_findings(original, revised) == []


def test_determiner_fix_does_not_move_a_name():
    original = (
        "Education is accessible through the Unified Hato Rey School District. "
        "These UHRSD is known for a curriculum that balances academic and arts education."
    )
    revised = (
        "Education is accessible through the Unified Hato Rey School District. "
        "The UHRSD is known for a curriculum that balances academic and arts education."
    )
    assert name_findings(original, revised) == []


def test_removing_a_banned_opener_does_not_move_a_name():
    original = (
        "The Port of Hato Rey handles cargo. "
        "Furthermore, the Aeropuerto de Boriquen handles freight."
    )
    revised = (
        "The Port of Hato Rey handles cargo. "
        "The Aeropuerto de Boriquen also handles freight."
    )
    assert name_findings(original, revised) == []


# --- direction (b): the referent, not the occurrence count ----------------


def test_trimming_one_of_many_mentions_is_not_a_dropped_name():
    original = (
        "Hato Rey is the capital. The Mayor of Hato Rey serves four years. "
        "In addition to day-to-day governance, the Mayor shapes the long-term "
        "vision for Hato Rey. The economy of Hato Rey is diversified."
    )
    revised = (
        "Hato Rey is the capital. The Mayor of Hato Rey serves four years. "
        "In addition to day-to-day governance, the Mayor shapes long-term "
        "planning priorities. The economy of Hato Rey is diversified."
    )
    assert name_findings(original, revised) == []


def test_losing_a_name_entirely_still_reports():
    original = "The canal drains into Lake Cherusken before reaching the sea."
    revised = "The canal drains into the estuary before reaching the sea."
    assert "Lake Cherusken" in evidences(original, revised)


def test_altering_a_name_still_reports_both_sides():
    original = "The bridge was opened by George Navarro in 1759."
    revised = "The bridge was opened by George Navarrete in 1759."
    found = evidences(original, revised)
    assert "George Navarro" in found
    assert "George Navarrete" in found


def test_a_wholly_new_name_still_reports():
    original = "The museum holds artifacts from the region."
    revised = "The museum holds artifacts donated by Yucah K. Busiri."
    assert any(
        str(item.get("id")) == "compare.name.introduced"
        for item in name_findings(original, revised)
    )


def test_a_sentence_initial_name_that_vanishes_still_reports():
    """Demotion needs evidence: an unrecognized opener stays a protected name.

    A single-word name is outside what NAME_RE tracks at all (it requires two
    or more words), so this uses a two-word name, which is what the check can
    actually see.
    """
    original = "Lake Cherusken anchors the corridor. The corridor carries most freight."
    revised = "The corridor carries most freight."
    found = evidences(original, revised)
    assert any("Lake Cherusken" in item for item in found)
