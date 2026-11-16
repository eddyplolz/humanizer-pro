"""The CI gate over `claude plugin validate --json` output.

The repo keeps CLAUDE.md at its root, which the validator reports as a warning.
The gate allows exactly that one warning, matched by its full text, and fails
on everything else.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = load_module("check_plugin_validate")

ALLOWED = (
    "CLAUDE.md at the plugin root is not loaded as project context. To ship context "
    "with your plugin, use a skill (skills/<name>/SKILL.md) instead."
)

# Trimmed from a real `claude plugin validate . --json`
# run on this repo (Claude Code 2.1.311).
CLEAN_REPORT = {
    "success": True,
    "strict": False,
    "manifest": {"type": "marketplace", "errors": [], "warnings": [], "notes": []},
    "contents": [
        {
            "file": "CLAUDE.md",
            "type": "plugin",
            "errors": [],
            "warnings": [{"path": "root", "message": ALLOWED, "code": None}],
            "notes": [],
        }
    ],
    "directory": {
        "findings": [
            {
                "code": "ICON_MISSING",
                "severity": "warning",
                "blocking": False,
                "message": "No icon",
            }
        ],
    },
}


def _report(**changes):
    report = copy.deepcopy(CLEAN_REPORT)
    report.update(changes)
    return report


def test_the_known_claude_md_warning_is_the_only_thing_allowed():
    assert gate.problems(CLEAN_REPORT) == []


def test_a_different_warning_fails_the_gate():
    report = _report()
    report["contents"][0]["warnings"].append(
        {
            "path": "version",
            "message": "Version is set in both plugin.json and marketplace.json",
        }
    )
    found = gate.problems(report)
    assert len(found) == 1
    assert "Version is set in both" in found[0]


def test_a_different_warning_on_the_marketplace_manifest_fails_the_gate():
    report = _report()
    report["manifest"]["warnings"].append(
        {"path": "owner", "message": "Owner has no email"}
    )
    assert len(gate.problems(report)) == 1


def test_the_allowed_text_must_match_exactly():
    report = _report()
    report["contents"][0]["warnings"][0]["message"] = ALLOWED.replace("root", "top")
    found = gate.problems(report)
    assert len(found) == 2
    assert "at the plugin top" in found[0]
    assert "expected CLAUDE.md warning is missing" in found[1]


def test_any_error_fails_the_gate():
    report = _report()
    report["contents"][0]["errors"].append(
        {"path": "name", "message": "name is required"}
    )
    assert len(gate.problems(report)) == 1


def test_a_failed_validation_fails_the_gate():
    assert gate.problems(_report(success=False)) == [
        "validator reported success: false"
    ]


def test_a_blocking_directory_finding_fails_the_gate():
    report = _report()
    report["directory"]["findings"][0]["blocking"] = True
    assert len(gate.problems(report)) == 1


def test_an_error_severity_directory_finding_fails_even_when_not_blocking():
    report = _report()
    report["directory"]["findings"][0]["severity"] = "error"
    assert len(gate.problems(report)) == 1


def test_a_report_with_only_success_fails_the_gate():
    found = gate.problems({"success": True})
    assert any("manifest" in line for line in found)
    assert any("contents" in line for line in found)


def test_warnings_moved_to_a_new_key_fail_the_gate():
    report = _report(contents=[], warnings=[{"message": "X"}])
    assert any("contents" in line for line in gate.problems(report))


def test_a_missing_claude_md_warning_fails_the_gate():
    report = _report()
    report["contents"][0]["warnings"] = []
    assert gate.problems(report) == [
        "the expected CLAUDE.md warning is missing; the report shape may have changed"
    ]


def test_a_report_that_is_not_an_object_fails_cleanly():
    assert gate.problems([]) == ["unexpected report shape: top level is a list"]


def test_a_contents_entry_that_is_not_an_object_fails_cleanly():
    report = _report()
    report["contents"].append("CLAUDE.md")
    assert "unexpected report shape: a contents entry is a str" in gate.problems(report)


def test_main_exits_zero_on_a_clean_report(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(CLEAN_REPORT), encoding="utf-8")
    assert gate.main([str(path)]) == 0
    assert "clean apart from the allowed CLAUDE.md warning" in capsys.readouterr().out


def test_main_exits_one_and_names_the_problem(tmp_path, capsys):
    report = _report()
    report["manifest"]["warnings"].append(
        {"path": "owner", "message": "Owner has no email"}
    )
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert gate.main([str(path)]) == 1
    assert "Owner has no email" in capsys.readouterr().err


def test_main_fails_loud_on_output_that_is_not_json(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text("", encoding="utf-8")
    assert gate.main([str(path)]) == 1
    assert "not valid JSON" in capsys.readouterr().err
