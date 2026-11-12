"""Family 10 (staging and the flat-verdict register): one positive and one negative literal per rule.

Rules that pass the corpus gate ship as `family10.*` warnings; the rest ship as
`register.*` info findings outside the risk score. See reference/coverage-map.md.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# name -> (sentence that must fire, near-miss that must not)
CASES = {
    "flat_certainty": (
        "The importer quietly drops rows with a blank date.",
        "The importer skips rows with a blank date and logs nothing.",
    ),
    "juridical_verb": (
        "The validator refuses any file without a header row.",
        "The validator exits with code 3 when the header row is missing.",
    ),
    "verification_compound": (
        "The output is byte-identical after the refactor.",
        "The output matches the old file for all 40 samples.",
    ),
    "exhaustive_negation": (
        "Nothing else touches the cache file.",
        "Two functions in load.py read the cache file.",
    ),
    "privative_coinage": (
        "The retry path is uncapped.",
        "The retry loop has no attempt limit.",
    ),
    "significance_designation": (
        "The real problem is the timezone.",
        "The job runs at midnight UTC, which is evening in Lima.",
    ),
    "performative_candour": (
        "Honestly, the old scheduler was faster.",
        "The old scheduler finished the batch in 12 minutes.",
    ),
    "bare_auxiliary": (
        "The first patch fixed the leak. The second one didn't.",
        "The first patch fixed the leak. The second left the socket open.",
    ),
    "retroactive_grading": (
        "That is why the cache layer matters.",
        "The cache layer cuts read time from 80 ms to 9 ms.",
    ),
    "totalizing": (
        "Latency is the only number that matters.",
        "We track page latency first because users leave after three seconds.",
    ),
    "obituary_header": (
        "## Polling is dead\n\nWe moved to webhooks in March.\n",
        "## Moving from polling to webhooks\n\nWe moved in March.\n",
    ),
    "verdict_header": (
        "## The cache is actually wrong here\n\nThe keys collide.\n",
        "## Cache key collisions\n\nThe keys collide.\n",
    ),
    "performed_humility": (
        "Probably nobody cares, but the build got faster.",
        "The build went from nine minutes to six.",
    ),
    "dev_cliche": (
        "The config loader is a footgun.",
        "The config loader overwrites the user file on every start.",
    ),
    "time_inflation": (
        "A while ago we switched the parser.",
        "In March we switched the parser.",
    ),
    "subjectless_fragment": (
        "Install the package. No setup needed.",
        "Install the package; it reads the defaults from setup.cfg.",
    ),
    "predicate_hyphenation": (
        "The new pipeline is data-driven.",
        "The new pipeline reads its thresholds from a table.",
    ),
    "contents_list_standfirst": (
        "The release notes, plus the bits the changelog skips.",
        "The release notes list four fixes and one new flag.",
    ),
}

# Rules promoted to scored warnings by the dev-split gate (see CHANGELOG).
# None for 4.17.0: no rule earned scoring on enough documents.
PROMOTED: set[str] = set()


def _module():
    spec = importlib.util.spec_from_file_location("humanizer_audit_register", ROOT / "scripts" / "humanizer_audit.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["humanizer_audit_register"] = module
    spec.loader.exec_module(module)
    return module


MODULE = _module()


def _rule_id(name: str) -> str:
    return f"family10.{name}" if name in PROMOTED else f"register.{name}"


def _ids(text: str) -> set[str]:
    return {f["id"] for f in MODULE.audit_text(text, "x")["findings"]}


def test_every_register_rule_has_a_case() -> None:
    shipped = {rule.id for rule in MODULE.REGISTER_RULES}
    assert shipped == {_rule_id(name) for name in CASES}


@pytest.mark.parametrize("name", sorted(CASES))
def test_rule_fires_on_positive(name: str) -> None:
    assert _rule_id(name) in _ids(CASES[name][0])


@pytest.mark.parametrize("name", sorted(CASES))
def test_rule_silent_on_negative(name: str) -> None:
    assert _rule_id(name) not in _ids(CASES[name][1])


@pytest.mark.parametrize("name", sorted(CASES))
def test_severity_and_family_match_promotion(name: str) -> None:
    rule = next(r for r in MODULE.REGISTER_RULES if r.id == _rule_id(name))
    if name in PROMOTED:
        assert (rule.severity, rule.family) == ("warning", 10)
    else:
        assert (rule.severity, rule.family) == ("info", None)


def test_unpromoted_register_rules_do_not_move_the_risk_score() -> None:
    names = sorted(set(CASES) - PROMOTED - {"obituary_header", "verdict_header"})[:4]
    text = " ".join(CASES[name][0] for name in names)
    assert all(_rule_id(name) in _ids(text) for name in names)
    assert MODULE.audit_text(text, "x")["risk_score"] == 0
