from __future__ import annotations

import json
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
