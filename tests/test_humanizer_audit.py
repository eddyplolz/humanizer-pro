from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "humanizer_audit.py"
CONTRACT = ROOT / "eval" / "contracts" / "task1.json"
COMPARE_CONTRACT = ROOT / "eval" / "contracts" / "task2_compare.json"


def run_audit(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=input_text,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def audit_json(*args: str, input_text: str | None = None) -> tuple[int, dict]:
    result = run_audit(*args, "--json", input_text=input_text)
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)


def finding_ids(document: dict) -> set[str]:
    return {finding["id"] for finding in document["findings"]}


def finding_families(document: dict) -> set[int]:
    return {finding["family"] for finding in document["findings"] if finding["family"] is not None}


def test_contract_fixtures() -> None:
    contracts = json.loads(CONTRACT.read_text(encoding="utf-8"))["fixtures"]
    for contract in contracts:
        returncode, payload = audit_json(contract["path"])
        document = payload["documents"][0]
        ids = finding_ids(document)
        families = finding_families(document)
        assert payload["schema"] == "humanizer-audit.v1"
        assert returncode == contract["expected_exit"], contract["path"]
        assert payload["summary"]["exit_code"] == contract["expected_exit"]
        assert "stats" in document
        assert "findings" in document
        if "max_score" in contract:
            assert document["risk_score"] <= contract["max_score"]
        for required_id in contract.get("required_ids", []):
            assert required_id in ids, contract["path"]
        for family in contract.get("required_families", []):
            assert family in families, contract["path"]
        for prefix in contract.get("forbidden_prefixes", []):
            assert not any(finding_id.startswith(prefix) for finding_id in ids), contract["path"]
        if contract.get("requires_source_risk"):
            assert any(finding["source_risk"] for finding in document["findings"]), contract["path"]


def test_compare_contract_fixtures() -> None:
    contracts = json.loads(COMPARE_CONTRACT.read_text(encoding="utf-8"))["fixtures"]
    for contract in contracts:
        returncode, payload = audit_json("--compare", contract["original"], contract["revised"])
        findings = payload["compare"]["findings"]
        ids = {finding["id"] for finding in findings}
        assert payload["schema"] == "humanizer-audit.v1"
        assert payload["documents"] == []
        assert payload["summary"]["comparisons"] == 1
        assert payload["summary"]["exit_code"] == contract["expected_exit"]
        assert payload["summary"]["compare_finding_count"] == len(findings)
        assert returncode == contract["expected_exit"], contract["name"]
        if "expected_findings" in contract:
            assert len(findings) == contract["expected_findings"], contract["name"]
        for required_id in contract.get("required_ids", []):
            assert required_id in ids, contract["name"]


def test_compare_mode_does_not_run_style_audit() -> None:
    returncode, payload = audit_json(
        "--compare",
        "eval/fixtures/fidelity/original.md",
        "eval/fixtures/fidelity/revised-good.md",
    )
    assert returncode == 0
    assert payload["summary"]["family_hit_count"] == 0
    assert payload["summary"]["max_risk_score"] == 0
    assert payload["compare"]["findings"] == []


def test_clean_human_has_no_artifact_or_source_risk_flags() -> None:
    returncode, payload = audit_json("eval/fixtures/clean-human.md")
    document = payload["documents"][0]
    assert returncode == 0
    assert document["risk_score"] <= 15
    assert payload["summary"]["artifact_count"] == 0
    assert payload["summary"]["source_risk_count"] == 0


def test_artifact_fixture_blocks_with_required_artifacts() -> None:
    returncode, payload = audit_json("eval/fixtures/artifact-leakage.md")
    ids = finding_ids(payload["documents"][0])
    assert returncode == 2
    assert payload["summary"]["max_severity"] == "error"
    assert "artifact.chatgpt_citation_stub" in ids
    assert "artifact.content_reference" in ids
    assert "artifact.ai_tracking_url" in ids
    assert "artifact.roleplay_marker" in ids
    assert "artifact.bracket_placeholder" in ids
    assert "artifact.placeholder_date" in ids


def test_ai_tracking_url_covers_multiple_ai_referrers() -> None:
    text = (
        "See https://example.org/a?utm_source=claude.ai and "
        "https://example.org/b?utm_source=copilot.com and "
        "https://example.org/c?referrer=grok.com for details."
    )
    returncode, payload = audit_json("--stdin", input_text=text)
    ids = [finding["id"] for finding in payload["documents"][0]["findings"]]
    assert returncode == 2
    assert ids.count("artifact.ai_tracking_url") == 3


def test_functional_query_params_are_not_tracking_flags() -> None:
    returncode, payload = audit_json("--stdin", input_text="Docs: https://example.org/a?page=2&v=4")
    ids = finding_ids(payload["documents"][0])
    assert "artifact.ai_tracking_url" not in ids


def test_zero_width_bypass_is_flagged_and_matching_still_hits() -> None:
    text = "A crucial, vibrant plan. We d​elve into the landscape."
    returncode, payload = audit_json("--stdin", input_text=text)
    document = payload["documents"][0]
    ids = finding_ids(document)
    assert returncode == 2
    assert "artifact.bypass_characters" in ids
    cluster = [f for f in document["findings"] if f["id"] == "family4.ai_vocab_cluster"]
    assert cluster and "delve" in cluster[0]["evidence"]


def test_homoglyph_bypass_is_flagged_and_matching_still_hits() -> None:
    text = "A cruсial, vibrant tapestry of pivotal outcomes."
    returncode, payload = audit_json("--stdin", input_text=text)
    document = payload["documents"][0]
    ids = finding_ids(document)
    assert returncode == 2
    assert "artifact.bypass_characters" in ids
    cluster = [f for f in document["findings"] if f["id"] == "family4.ai_vocab_cluster"]
    assert cluster and "crucial" in cluster[0]["evidence"]


def test_leading_bom_and_genuine_cyrillic_are_not_bypass_flags() -> None:
    text = "﻿The report quotes the phrase привет in one footnote."
    returncode, payload = audit_json("--stdin", input_text=text)
    ids = finding_ids(payload["documents"][0])
    assert "artifact.bypass_characters" not in ids


def test_roleplay_marker_flags_action_asterisks_not_italics() -> None:
    returncode, payload = audit_json("--stdin", input_text="*nods thoughtfully* The plan works.")
    assert returncode == 2
    assert "artifact.roleplay_marker" in finding_ids(payload["documents"][0])
    returncode, payload = audit_json("--stdin", input_text="This word gets *emphasis* only.")
    assert "artifact.roleplay_marker" not in finding_ids(payload["documents"][0])


def test_clarity_wordiness_is_reported_but_never_risky() -> None:
    text = "We will utilize the platform to facilitate onboarding and commence the rollout."
    returncode, payload = audit_json("--stdin", input_text=text)
    document = payload["documents"][0]
    assert returncode == 0
    assert "clarity.wordiness" in finding_ids(document)
    assert document["risk_score"] == 0
    assert payload["summary"]["clarity_hit_count"] == 3
    assert payload["summary"]["family_hit_count"] == 0


def test_two_tier1_words_fire_vocab_cluster_across_paragraphs() -> None:
    text = "A pivotal step for the region.\n\nIts opening was a testament, colleagues said."
    _returncode, payload = audit_json("--stdin", input_text=text)
    ids = finding_ids(payload["documents"][0])
    assert "family4.ai_vocab_cluster" in ids


def test_two_tier2_words_in_separate_paragraphs_do_not_fire_cluster() -> None:
    text = "A crucial step for the region.\n\nThe team will enhance the program."
    _returncode, payload = audit_json("--stdin", input_text=text)
    ids = finding_ids(payload["documents"][0])
    assert "family4.ai_vocab_cluster" not in ids


def test_speculative_gap_filling_and_vague_validation_flag_with_source_risk() -> None:
    text = (
        "The founder is believed to have studied in the capital. "
        "Independent testing confirms the institute's reputation."
    )
    _returncode, payload = audit_json("--stdin", input_text=text)
    document = payload["documents"][0]
    ids = finding_ids(document)
    assert "family2.speculative_gap_filling" in ids
    assert "family2.vague_validation" in ids
    assert all(
        finding["source_risk"]
        for finding in document["findings"]
        if finding["id"] in {"family2.speculative_gap_filling", "family2.vague_validation"}
    )


def test_list_label_period_flags_period_labels_only() -> None:
    _returncode, payload = audit_json("--stdin", input_text="- **Intros.** Years of conferences.")
    assert "family8.list_label_period" in finding_ids(payload["documents"][0])
    _returncode, payload = audit_json("--stdin", input_text="- **Intros:** years of conferences.")
    assert "family8.list_label_period" not in finding_ids(payload["documents"][0])


def _load_audit_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("humanizer_audit_under_test", CLI)
    module = importlib.util.module_from_spec(spec)
    sys.modules["humanizer_audit_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_every_cli_rule_id_is_in_the_coverage_map() -> None:
    module = _load_audit_module()
    coverage = (ROOT / "reference" / "coverage-map.md").read_text(encoding="utf-8")
    rule_ids = {
        rule.id
        for table in (module.ARTIFACT_RULES, module.FAMILY_RULES, module.SOURCE_RISK_RULES, module.CLARITY_RULES)
        for rule in table
    }
    rule_ids.update(
        {
            "family4.ai_vocab_cluster",
            "artifact.bypass_characters",
            "structure.low_sentence_variance",
            "structure.long_uniform_paragraphs",
        }
    )
    missing = {rule_id for rule_id in rule_ids if f"`{rule_id}`" not in coverage}
    assert not missing, f"CLI rule ids missing from reference/coverage-map.md: {sorted(missing)}"
    assert "compare." in coverage


def test_self_scan_passes_its_budgets() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "self_scan.py"), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "humanizer-self-scan.v1"
    assert result.returncode == 0, payload["failures"]
    assert {row["path"] for row in payload["documents"]} >= {"README.md", "SKILL.md"}


def test_compare_ignores_stripped_ai_referrer(tmp_path: Path) -> None:
    (tmp_path / "original.md").write_text(
        "Read [the report](https://example.org/r?referrer=grok.com) today.", encoding="utf-8"
    )
    (tmp_path / "revised.md").write_text(
        "Read [the report](https://example.org/r) today.", encoding="utf-8"
    )
    returncode, payload = audit_json(
        "--compare", str(tmp_path / "original.md"), str(tmp_path / "revised.md")
    )
    assert returncode == 0
    assert payload["compare"]["findings"] == []


def test_ai_slop_general_returns_review_and_expected_families() -> None:
    returncode, payload = audit_json("eval/fixtures/ai-slop-general.md")
    families = finding_families(payload["documents"][0])
    assert returncode == 1
    assert {1, 3, 4, 5, 7}.issubset(families)


def test_stdin_json_schema() -> None:
    returncode, payload = audit_json("--stdin", input_text="Great question! turn0search0 [Your Name]")
    document = payload["documents"][0]
    assert returncode == 2
    assert payload["schema"] == "humanizer-audit.v1"
    assert payload["summary"]["documents"] == 1
    assert document["path"] == "<stdin>"
    assert {"path", "risk_score", "stats", "findings"}.issubset(document)


def test_directory_input_audits_only_markdown_and_text(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("Great question! turn0search0", encoding="utf-8")
    (tmp_path / "b.txt").write_text("In today's robust landscape, teams foster vibrant outcomes.", encoding="utf-8")
    (tmp_path / "skip.py").write_text("print('turn0search0')", encoding="utf-8")
    returncode, payload = audit_json(str(tmp_path))
    assert returncode == 2
    paths = {Path(document["path"]).name for document in payload["documents"]}
    assert paths == {"a.md", "b.txt"}


def test_text_report_is_available() -> None:
    result = run_audit("eval/fixtures/ai-slop-general.md")
    assert result.returncode == 1
    assert "Humanizer audit:" in result.stdout
    assert "family4.ai_vocab_cluster" in result.stdout


def test_compare_text_report_is_available() -> None:
    result = run_audit(
        "--compare",
        "eval/fixtures/fidelity/original.md",
        "eval/fixtures/fidelity/revised-drift.md",
    )
    assert result.returncode == 2
    assert "Humanizer compare:" in result.stdout
    assert "compare.code_block.changed" in result.stdout


def test_anaphora_fires_on_three_consecutive_openers() -> None:
    text = (
        "Not every door has been tried. Not every version of this exists. "
        "Not every path leads home. The rest of the paragraph varies its openers "
        "with different words entirely."
    )
    _returncode, payload = audit_json("--stdin", input_text=text)
    ids = {finding["id"] for finding in payload["documents"][0]["findings"]}
    assert "structure.anaphora" in ids


def test_anaphora_ignores_two_openers_and_stopwords() -> None:
    two_only = "Not every door was tried. Not every path was walked. A third sentence differs."
    _returncode, payload = audit_json("--stdin", input_text=two_only)
    ids = {finding["id"] for finding in payload["documents"][0]["findings"]}
    assert "structure.anaphora" not in ids
    stopword = "The dog barked. The cat slept. The bird sang. A fox watched them all."
    _returncode, payload = audit_json("--stdin", input_text=stopword)
    ids = {finding["id"] for finding in payload["documents"][0]["findings"]}
    assert "structure.anaphora" not in ids


def test_family7_ignores_plain_enumeration_triplets() -> None:
    enumeration = (
        "The ministry oversees public works, regional transit, and rural development. "
        "Its board includes elected officials, appointed experts, and community delegates."
    )
    _returncode, payload = audit_json("--stdin", input_text=enumeration)
    ids = {finding["id"] for finding in payload["documents"][0]["findings"]}
    assert "family7.rhetorical_formula" not in ids
    phrase = "This is not just a report but a warning to every reader."
    _returncode, payload = audit_json("--stdin", input_text=phrase)
    ids = {finding["id"] for finding in payload["documents"][0]["findings"]}
    assert "family7.rhetorical_formula" in ids


def test_markdown_structure_fires_once_per_document() -> None:
    table_heavy = "\n".join(
        ["| Year | Event | Outcome |", "| --- | --- | --- |"]
        + [f"| 19{i:02} | Item {i} | Result {i} |" for i in range(20)]
    )
    _returncode, payload = audit_json("--stdin", input_text=table_heavy)
    findings = payload["documents"][0]["findings"]
    hits = [f for f in findings if f["id"] == "family8.markdown_structure"]
    assert len(hits) == 1


def test_uniform_length_run_calibrated_threshold() -> None:
    uniform = " ".join(
        "This sentence runs to about twelve words in total length here now." for _ in range(7)
    )
    _returncode, payload = audit_json("--stdin", input_text=uniform)
    document = payload["documents"][0]
    assert document["stats"]["max_uniform_run"] >= 6
    ids = {finding["id"] for finding in document["findings"]}
    assert "structure.uniform_length_run" in ids
    varied = (
        "Short one. This sentence stretches considerably further, unfolding across many more "
        "words than its neighbors ever attempt to reach in this text. Mid-length follows here "
        "with several words. Tiny. Another long construction now arrives, carrying clause after "
        "clause toward a conclusion that refuses to hurry itself along the way."
    )
    _returncode, payload = audit_json("--stdin", input_text=varied)
    ids = {finding["id"] for finding in payload["documents"][0]["findings"]}
    assert "structure.uniform_length_run" not in ids


def test_rlhf_framing_extends_family9() -> None:
    text = "Let me walk you through the deployment. On the one hand it is fast, but on the other it costs more."
    _returncode, payload = audit_json("--stdin", input_text=text)
    document = payload["documents"][0]
    hits = [f for f in document["findings"] if f["id"] == "family9.chatbot_residue"]
    assert len(hits) >= 2


def test_filler_wrappers_are_clarity_only() -> None:
    text = (
        "With regard to the deployment, the plan held. "
        "In the event that this recurs, page the on-call engineer."
    )
    _returncode, payload = audit_json("--stdin", input_text=text)
    document = payload["documents"][0]
    clarity_hits = [f for f in document["findings"] if f["id"] == "clarity.wordiness"]
    assert len(clarity_hits) == 2
    assert all(f["severity"] == "info" for f in clarity_hits)
    assert document["risk_score"] == 0


def test_unicode_tag_characters_are_stripped_and_flagged() -> None:
    text = "The plan is ready\U000E0068\U000E0069 for the vibrant, crucial rollout."
    returncode, payload = audit_json("--stdin", input_text=text)
    assert returncode == 2
    assert "artifact.bypass_characters" in finding_ids(payload["documents"][0])


def test_tag_character_hit_is_reported_as_invisible_not_zero_width() -> None:
    # A tag character is neither zero-width nor a homoglyph, so the finding must
    # label it as an invisible character rather than mislabeling it zero-width.
    text = "The plan is ready\U000E0068\U000E0069 for the vibrant, crucial rollout."
    _returncode, payload = audit_json("--stdin", input_text=text)
    bypass = next(
        f for f in payload["documents"][0]["findings"]
        if f["id"] == "artifact.bypass_characters"
    )
    assert bypass["evidence"].startswith("invisible=")
    assert "zero_width" not in bypass["evidence"]
    assert bypass["message"].startswith("Invisible or homoglyph")


def test_unicode_noncharacters_are_stripped_and_flagged() -> None:
    text = "A crucial￿and vibrant plan for the landscape ahead of us."
    returncode, payload = audit_json("--stdin", input_text=text)
    assert returncode == 2
    assert "artifact.bypass_characters" in finding_ids(payload["documents"][0])


def test_latin_zero_width_joiner_bypass_is_still_flagged() -> None:
    # A zero-width joiner or non-joiner between Latin letters has no legitimate
    # shaping role, so it is bypass residue and must still be caught.
    for joiner in ("‍", "‌"):
        text = f"A cru{joiner}cial and vibrant plan for the landscape."
        _returncode, payload = audit_json("--stdin", input_text=text)
        assert "artifact.bypass_characters" in finding_ids(payload["documents"][0])


def test_preserve_list_keeps_multilingual_joiners_byte_identical() -> None:
    module = _load_audit_module()
    for legit in (
        "\U0001f468‍\U0001f469‍\U0001f467",  # family emoji ZWJ sequence
        "❤️",  # heart followed by variation selector 16
        "1️⃣",  # keycap digit sequence
        "می‌خواهم",  # Persian "mikhaham" with ZWNJ
        "क्‍ष",  # Devanagari ligature held by a ZWJ
    ):
        normalized, counts, first_offset = module.normalize_bypass_text(legit)
        assert normalized == legit, legit.encode("unicode_escape")
        assert counts["invisible"] == 0
        assert first_offset == -1


def test_injected_zero_width_stripped_while_emoji_joiner_survives() -> None:
    module = _load_audit_module()
    # A zero-width SPACE injected after a legitimate emoji ZWJ pair: the joiner
    # is kept, the injected space is removed, and only the injection is counted.
    normalized, counts, _first = module.normalize_bypass_text(
        "\U0001f468‍\U0001f469​next"
    )
    assert normalized == "\U0001f468‍\U0001f469next"
    assert counts["invisible"] == 1


def test_variation_selector_stripped_between_letters_kept_after_emoji() -> None:
    module = _load_audit_module()
    stripped, counts, _first = module.normalize_bypass_text("a️b")
    assert stripped == "ab"
    assert counts["invisible"] == 1
    kept, kept_counts, _f2 = module.normalize_bypass_text("❤️")
    assert kept == "❤️"
    assert kept_counts["invisible"] == 0


def test_adjacent_variation_selectors_between_letters_do_not_shield() -> None:
    module = _load_audit_module()
    # Two variation selectors injected between plain Latin letters must not
    # vouch for each other: a selector's context has to be a real emoji base,
    # so both are bypass residue that is stripped and counted.
    normalized, counts, _first = module.normalize_bypass_text("a️️b")
    assert normalized == "ab"
    assert counts["invisible"] == 2
    # A longer run collapses completely rather than partially surviving.
    collapsed, run_counts, _f2 = module.normalize_bypass_text("a️️️b")
    assert collapsed == "ab"
    assert run_counts["invisible"] == 3


def test_invisible_math_operators_are_stripped_and_flagged() -> None:
    # U+2061-U+2064 (function application, invisible times/separator/plus) have
    # no place in this skill's registers, so each is always-strip bypass residue.
    module = _load_audit_module()
    for cp in (0x2061, 0x2062, 0x2063, 0x2064):
        text = f"a{chr(cp)}b"
        normalized, counts, _first = module.normalize_bypass_text(text)
        assert normalized == "ab", hex(cp)
        assert counts["invisible"] == 1, hex(cp)
    returncode, payload = audit_json(
        "--stdin", input_text="A crucial⁢and vibrant plan for the landscape ahead."
    )
    assert returncode == 2
    assert "artifact.bypass_characters" in finding_ids(payload["documents"][0])


def test_mongolian_vowel_separator_is_stripped_and_flagged() -> None:
    # U+180E renders as nothing in modern fonts and is a known bypass character.
    module = _load_audit_module()
    normalized, counts, _first = module.normalize_bypass_text("a᠎b")
    assert normalized == "ab"
    assert counts["invisible"] == 1
    returncode, payload = audit_json(
        "--stdin", input_text="A crucial᠎and vibrant plan for the landscape ahead."
    )
    assert returncode == 2
    assert "artifact.bypass_characters" in finding_ids(payload["documents"][0])


def test_mattr_matches_hand_computed_windows() -> None:
    # Independent hand-computed values, not a re-derivation of the code.
    # window=2 over [a,a,b,a]: TTRs 1/2, 2/2, 2/2 -> mean 0.8333 -> 0.83.
    module = _load_audit_module()
    mattr = module.moving_avg_type_token_ratio
    assert mattr(["a", "a", "b", "a"], 2) == 0.83
    # window=3 over [a,b,c,d]: every window all-unique -> 1.0.
    assert mattr(["a", "b", "c", "d"], 3) == 1.0
    # Shorter than one window: no windowed value exists, so None rather than a
    # plain TTR that would not be comparable with a real MATTR.
    assert mattr(["a", "a"], 50) is None
    assert mattr([]) is None
    # Exactly one window is the plain TTR of that window.
    assert mattr(["a", "a"], 2) == 0.5


def test_mattr_rejects_non_positive_window() -> None:
    mattr = _load_audit_module().moving_avg_type_token_ratio
    for window in (0, -1):
        try:
            mattr(["a", "b"], window)
        except ValueError:
            continue
        raise AssertionError(f"window={window} should raise ValueError")


def test_mattr_sliding_count_matches_per_window_sets() -> None:
    import random

    mattr = _load_audit_module().moving_avg_type_token_ratio
    rng = random.Random(7)
    for _ in range(200):
        tokens = [rng.choice("abcdeAB") for _ in range(rng.randint(1, 120))]
        window = rng.randint(1, len(tokens))
        lowered = [token.lower() for token in tokens]
        count = len(lowered) - window + 1
        types = sum(len(set(lowered[i : i + window])) for i in range(count))
        assert mattr(tokens, window) == round(types / (count * window), 2)


def test_short_document_reports_null_mattr() -> None:
    _returncode, payload = audit_json("--stdin", input_text="A short note about the plan.")
    assert payload["documents"][0]["stats"]["mattr_50"] is None


def test_mattr_50_is_a_stat_not_a_finding_or_score() -> None:
    module = _load_audit_module()
    # Low-diversity text scores far below high-diversity text (independent inputs).
    low = module.stats_for("cat dog " * 60)["mattr_50"]
    high = module.stats_for(" ".join(f"w{i}" for i in range(120)))["mattr_50"]
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert low < high
    # It is a diagnostic stat only: it appears in the stats block and never as
    # a finding, and changing its value moves neither findings nor score.
    _returncode, payload = audit_json("--stdin", input_text="cat dog " * 60)
    document = payload["documents"][0]
    assert "mattr_50" in document["stats"]
    assert not any("mattr" in fid for fid in finding_ids(document))
    text = (ROOT / "eval" / "fixtures" / "ai-slop-general.md").read_text(encoding="utf-8")
    baseline = module.audit_text(text, "x")
    original = module.moving_avg_type_token_ratio
    try:
        for forced in (0.0, 1.0, None):
            module.moving_avg_type_token_ratio = lambda *_args, value=forced: value
            forced_result = module.audit_text(text, "x")
            assert forced_result["stats"]["mattr_50"] == forced
            assert forced_result["findings"] == baseline["findings"]
            assert forced_result["risk_score"] == baseline["risk_score"]
    finally:
        module.moving_avg_type_token_ratio = original


# ------------------------------------------------- full-repo review fixes


def _ids_for(text: str) -> list[str]:
    return [f["id"] for f in _load_audit_module().audit_text(text, "x")["findings"]]


def test_usage_errors_exit_3_not_block() -> None:
    assert run_audit().returncode == 3
    assert run_audit("--bogus", "x").returncode == 3
    assert run_audit("--fail-score", "abc", "x").returncode == 3


def test_stdin_is_strict_utf8_and_newline_normalized() -> None:
    bad = subprocess.run(
        [sys.executable, str(CLI), "--stdin"], input=b"caf\xc3\xa9 \xff",
        cwd=ROOT, capture_output=True, check=False,
    )
    assert bad.returncode == 3
    good = subprocess.run(
        [sys.executable, str(CLI), "--stdin", "--json"], input="Ab café.\r\nNext line.\r\n".encode(),
        cwd=ROOT, capture_output=True, check=False,
    )
    assert good.returncode == 0
    stats = json.loads(good.stdout)["documents"][0]["stats"]
    assert stats["words"] == 4


def test_rhetorical_formula_stays_inside_one_sentence() -> None:
    far_apart = "This is not just a test.\n\nMuch later, but unrelated, the end."
    assert "family7.rhetorical_formula" not in _ids_for(far_apart)
    assert "family7.rhetorical_formula" in _ids_for("It is not just fast but cheap.")
    assert "family7.rhetorical_formula" in _ids_for("Not only fast, but also cheap.")


def test_of_course_bang_is_detected_before_a_space() -> None:
    assert "family9.chatbot_residue" in _ids_for("Of course! Here is the plan.")


def test_one_phrase_is_not_scored_twice() -> None:
    assert _ids_for("It is important to note the plan.") == ["family5.syntactic_tell"]
    assert _ids_for("The tool has the ability to parse files.") == ["family6.verbosity_padding"]


def test_one_repeated_vocab_word_is_not_a_cluster() -> None:
    assert "family4.ai_vocab_cluster" not in _ids_for(
        "The robust design was robust. We tested robust estimators."
    )
    assert "family4.ai_vocab_cluster" not in _ids_for("The landscape of the landscape.")
    assert "family4.ai_vocab_cluster" in _ids_for("A robust, vibrant tapestry.")


def test_word_tokenizer_handles_accents_and_curly_apostrophes() -> None:
    words = _load_audit_module().words
    assert words("café naïve don’t state-of-the-art") == [
        "café", "naïve", "don’t", "state-of-the-art",
    ]


def test_low_variance_message_is_a_full_sentence() -> None:
    text = "One two three four. " * 4
    findings = _load_audit_module().audit_text(text, "x")["findings"]
    message = next(f["message"] for f in findings if f["id"] == "structure.low_sentence_variance")
    assert not message.endswith(" even")


def _compare_ids(original: str, revised: str) -> list[tuple[str, str]]:
    result = _load_audit_module().compare_texts(original, revised, "a", "b")
    return [(f["id"], f["evidence"]) for f in result["findings"]]


def test_dropping_first_quote_does_not_shift_later_quotes() -> None:
    original = 'Intro "alpha beta gamma" mid "delta epsilon" end "zeta eta theta".'
    revised = 'Intro mid "delta epsilon" end "zeta eta theta".'
    quote_findings = [item for item in _compare_ids(original, revised) if ".quote." in item[0]]
    assert quote_findings == [("compare.quote.dropped", '"alpha beta gamma"')]


def test_changed_quote_is_still_reported_as_changed() -> None:
    quote_findings = [
        item
        for item in _compare_ids('A "one two three" B "four five six"', 'A "one two THREE" B "four five six"')
        if ".quote." in item[0]
    ]
    assert quote_findings == [("compare.quote.changed", '"one two three"')]


def test_repeated_link_label_retarget_is_reported() -> None:
    original = "See [docs](https://a.com/1) and [docs](https://a.com/2)."
    revised = "See [docs](https://a.com/9) and [docs](https://a.com/2)."
    ids = [item[0] for item in _compare_ids(original, revised)]
    assert "compare.citation.changed_target" in ids


def test_tilde_fences_are_code_blocks() -> None:
    original = "Text.\n\n~~~\nx = 1\n~~~\n"
    ids = [item[0] for item in _compare_ids(original, original.replace("1", "2"))]
    assert ids == ["compare.code_block.changed"]
    assert _load_audit_module().stats_for(original)["code_block_count"] == 1


def test_empty_directory_warns_on_stderr(tmp_path: Path) -> None:
    result = run_audit(str(tmp_path))
    assert result.returncode == 0
    assert "no .md or .txt files" in result.stderr


def test_skill_md_stays_under_line_limit() -> None:
    # WARP.md: "Keep under 350 lines for v4.x."
    lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 350, len(lines)


def test_text_report_survives_a_narrow_output_encoding(tmp_path: Path) -> None:
    sample = tmp_path / "cyr.md"
    sample.write_text("It is not just Привет but more.\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CLI), str(sample)],
        cwd=ROOT, capture_output=True, check=False,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 0, result.stderr
    assert b"family7.rhetorical_formula" in result.stdout


# ------------------------------------------------- v4.14.0: code, targets, SARIF


CODE_DOC = (
    "Call `utilize()` to start.\n\n"
    "```text\nIt is a delve into the vibrant, robust tapestry\n```\n"
)


def test_code_is_masked_for_prose_rules_and_restorable() -> None:
    module = _load_audit_module()
    masked = module.audit_text(CODE_DOC, "x")
    assert masked["findings"] == []
    assert masked["stats"]["code_block_count"] == 1
    raw = {f["id"] for f in module.audit_text(CODE_DOC, "x", include_code=True)["findings"]}
    assert {"clarity.wordiness", "family4.ai_vocab_cluster"} <= raw


def test_artifacts_inside_code_still_block() -> None:
    # A chatbot reply pasted with its ```markdown wrapper keeps its leaks.
    wrapped = (
        "```markdown\n# Erie Canal\n\nThe canal opened in 1825.citeturn0search3 "
        ":contentReference[oaicite:0]{index=0}\n```\n"
    )
    ids = {f["id"] for f in _load_audit_module().audit_text(wrapped, "x")["findings"]}
    assert {"artifact.chatgpt_citation_stub", "artifact.content_reference"} <= ids


def test_a_passing_mention_of_a_fence_does_not_mask_prose() -> None:
    text = (
        "To show code, wrap it in ``` fences.\n\n"
        "A delve into the vibrant, robust tapestry.\n\n```\ncode\n```\n"
    )
    ids = {f["id"] for f in _load_audit_module().audit_text(text, "x")["findings"]}
    assert "family4.ai_vocab_cluster" in ids


def test_bypass_characters_inside_code_are_still_flagged() -> None:
    text = "Plain intro.\n\n```\nab​cd\n```\n"
    ids = {f["id"] for f in _load_audit_module().audit_text(text, "x")["findings"]}
    assert "artifact.bypass_characters" in ids


def test_include_code_flag_on_the_cli(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(CODE_DOC, encoding="utf-8")
    assert run_audit(str(doc), "--json").returncode == 0
    _code, payload = audit_json(str(doc), "--include-code")
    assert "clarity.wordiness" in finding_ids(payload["documents"][0])


def test_several_targets_are_audited_once_each() -> None:
    clean = "eval/fixtures/clean-human.md"
    returncode, payload = audit_json(clean, "eval/fixtures/ai-slop-general.md", clean)
    assert [d["path"] for d in payload["documents"]] == [clean, "eval/fixtures/ai-slop-general.md"]
    assert returncode == 1


def test_version_flag() -> None:
    result = run_audit("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"humanizer-audit {_load_audit_module().__version__}"


def _sarif(tmp_path: Path, *args: str) -> dict:
    out = tmp_path / "out.sarif"
    run_audit(*args, "--sarif", str(out))
    return json.loads(out.read_text(encoding="utf-8"))


def test_sarif_for_an_audit(tmp_path: Path) -> None:
    log = _sarif(tmp_path, "eval/fixtures/artifact-leakage.md")
    assert log["version"] == "2.1.0"
    run = log["runs"][0]
    assert run["columnKind"] == "unicodeCodePoints"
    assert run["tool"]["driver"]["name"] == "humanizer-audit"
    rule_ids = [rule["id"] for rule in run["tool"]["driver"]["rules"]]
    assert len(rule_ids) == len(set(rule_ids))
    assert run["results"]
    for result in run["results"]:
        assert result["level"] in {"error", "warning", "note"}
        assert rule_ids[result["ruleIndex"]] == result["ruleId"]
        location = result["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == "eval/fixtures/artifact-leakage.md"
        assert location["region"]["startLine"] >= 1 and location["region"]["startColumn"] >= 1
    assert any(r["level"] == "error" for r in run["results"])


def test_sarif_for_compare_points_at_the_right_side(tmp_path: Path) -> None:
    log = _sarif(
        tmp_path,
        "--compare",
        "eval/fixtures/fidelity/original.md",
        "eval/fixtures/fidelity/revised-drift.md",
    )
    uris = {
        r["ruleId"].rsplit(".", 1)[-1]: r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in log["runs"][0]["results"]
    }
    assert uris["dropped"] == "eval/fixtures/fidelity/original.md"
    assert uris["introduced"] == "eval/fixtures/fidelity/revised-drift.md"


def test_sarif_write_failure_exits_3(tmp_path: Path) -> None:
    result = run_audit("eval/fixtures/clean-human.md", "--sarif", str(tmp_path / "missing" / "x.sarif"))
    assert result.returncode == 3


# ------------------------------------------------- distribution: action, hook, wheel


def _action_script() -> str:
    """The composite step's `run: |` block, de-indented."""
    lines = (ROOT / "action.yml").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "run: |") + 1
    body = []
    for line in lines[start:]:
        if line.strip() and not line.startswith(" " * 8):
            break
        body.append(line[8:])
    return "\n".join(body) + "\n"


def _run_action(tmp_path: Path, **inputs: str) -> tuple[int, dict[str, str]]:
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(output),
        "HA_SCRIPT": str(CLI),
        "HA_PATHS": inputs.get("paths", "."),
        "HA_FAIL_ON": inputs.get("fail_on", "block"),
        "HA_FAIL_SCORE": inputs.get("fail_score", "60"),
        "HA_SARIF": inputs.get("sarif", str(tmp_path / "out.sarif")),
        "HA_INCLUDE_CODE": inputs.get("include_code", "false"),
    }
    result = subprocess.run(
        ["bash", "-e", "-c", _action_script()], cwd=ROOT, env=env, capture_output=True, check=False
    )
    pairs = dict(
        line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line
    )
    return result.returncode, pairs


def test_action_fail_on_policies(tmp_path: Path) -> None:
    slop = "eval/fixtures/ai-slop-general.md"  # exit 1 (review)
    assert _run_action(tmp_path, paths=slop, fail_on="block")[0] == 0
    code, outputs = _run_action(tmp_path, paths=slop, fail_on="review")
    assert code == 1 and outputs["exit-code"] == "1"
    assert outputs["sarif-file"].endswith("out.sarif")
    assert _run_action(tmp_path, paths="eval/fixtures/artifact-leakage.md", fail_on="block")[0] == 2
    assert _run_action(tmp_path, paths="eval/fixtures/artifact-leakage.md", fail_on="never")[0] == 0
    assert _run_action(tmp_path, paths="no/such/file.md", fail_on="never")[0] == 3
    assert _run_action(tmp_path, paths=slop, fail_on="sometimes")[0] == 3


def test_action_inputs_are_not_shell_interpolated(tmp_path: Path) -> None:
    canary = tmp_path / "pwned"
    code, _outputs = _run_action(tmp_path, paths=f"eval/fixtures/clean-human.md; touch {canary}")
    assert not canary.exists()
    assert code == 3  # the literal "; touch ..." is just a missing path
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "${{ inputs." not in _action_script()
    assert "scripts/humanizer_audit.py" in text


def test_pre_commit_hook_points_at_the_console_script() -> None:
    hooks = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "entry: humanizer-audit" in hooks
    assert "language: python" in hooks
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'humanizer-audit = "humanizer_audit:main"' in pyproject


def test_wheel_installs_a_working_console_script(tmp_path: Path) -> None:
    import shutil
    import venv

    import importlib.util

    pytest = __import__("pytest")
    if importlib.util.find_spec("pip") is None:
        pytest.skip("pip is not installed in this interpreter")
    # An isolated build, as pip does for users. It fetches setuptools, so it
    # skips (rather than fails) only when no package index is reachable.
    # Build from a copy so setuptools' build/ and egg-info never touch the checkout.
    source = tmp_path / "src"
    (source / "scripts").mkdir(parents=True)
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy(ROOT / name, source / name)
    shutil.copy(CLI, source / "scripts" / "humanizer_audit.py")
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(source), "--no-deps",
         "-w", str(tmp_path / "dist"), "-q"],
        capture_output=True, text=True, check=False,
    )
    offline = ("No matching distribution found for setuptools", "Could not find a version")
    if build.returncode != 0 and any(marker in build.stderr for marker in offline):
        pytest.skip("no package index reachable for an isolated build")
    assert build.returncode == 0, build.stderr
    wheels = list((tmp_path / "dist").glob("humanizer_audit-*.whl"))
    assert len(wheels) == 1
    version = _load_audit_module().__version__
    assert wheels[0].name.startswith(f"humanizer_audit-{version}-")
    env_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    bindir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    install = subprocess.run(
        [str(bindir / "python"), "-m", "pip", "install", "--no-index", "-q", str(wheels[0])],
        capture_output=True, text=True, check=False,
    )
    assert install.returncode == 0, install.stderr
    exe = shutil.which("humanizer-audit", path=str(bindir))
    assert exe
    assert subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip() == (
        f"humanizer-audit {version}"
    )
    audited = subprocess.run(
        [exe, str(ROOT / "eval" / "fixtures" / "artifact-leakage.md"), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert audited.returncode == 2
    assert json.loads(audited.stdout)["schema"] == "humanizer-audit.v1"


def test_version_is_consistent_across_the_repo() -> None:
    import re

    version = _load_audit_module().__version__
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert f'version: "{version}"' in skill
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(r"^## (\S+)", changelog, re.M).group(1) == version
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"Current release: **v{version}**" in readme


def test_action_reads_multi_line_paths_and_drops_stale_sarif(tmp_path: Path) -> None:
    stale = tmp_path / "out.sarif"
    stale.write_text("stale", encoding="utf-8")
    paths = "eval/fixtures/clean-human.md\neval/fixtures/artifact-leakage.md"
    code, outputs = _run_action(tmp_path, paths=paths, fail_on="never")
    assert code == 0 and outputs["exit-code"] == "2"  # the second line was audited
    assert json.loads(stale.read_text(encoding="utf-8"))["version"] == "2.1.0"
    stale.write_text("stale", encoding="utf-8")
    code, outputs = _run_action(tmp_path, paths="no/such/file.md", fail_on="never")
    assert code == 3 and not stale.exists() and "sarif-file" not in outputs
