"""Hostile-input regressions: slow regexes, log injection, crash exit codes,
and file handling that could leak text from outside the audited tree."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "humanizer_audit.py"
sys.path.insert(0, str(ROOT / "scripts"))

import humanizer_audit as H  # noqa: E402

# Each input below ran past 15 seconds (most past a minute) before the scanners
# were made linear; all of them now finish in about a second. The limit is
# loose so a slow CI runner does not flake, and the subprocess timeout keeps a
# regression from hanging the suite.
TIME_LIMIT = 15

# (repeated unit, repeat count)
HOSTILE_AUDIT = {
    "unclosed backtick fences": ("```x\n", 40000),
    "whitespace-only lines": (" \n", 40000),
    "pipe then one long run of spaces": ("|" + " " * 40000, 1),
    "backtick runs of every length": ("".join("`" * k + "x" for k in range(1, 3000)), 1),
}

HOSTILE_COMPARE = {
    "repeated tilde fences": ("~~~\n", 40000),
    "unclosed ref tags": ("<ref>", 40000),
    "unclosed cite templates": ("{{cite ", 40000),
    "unclosed footnote brackets": ("[^", 40000),
    "unclosed curly quotes": ("“", 120000),
    "dotted capitals": ("A.", 50000),
    "comma-joined digits": ("1,", 50000),
    "one quote repeated": ('"abc" ', 20000),
}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=TIME_LIMIT,
    )


@pytest.mark.parametrize(("unit", "count"), HOSTILE_AUDIT.values(), ids=HOSTILE_AUDIT.keys())
def test_hostile_input_audits_in_bounded_time(tmp_path: Path, unit: str, count: int) -> None:
    target = tmp_path / "hostile.md"
    target.write_text(unit * count, encoding="utf-8", newline="")
    result = run_cli(str(target), "--json")
    assert result.returncode in (0, 1, 2), result.stderr
    json.loads(result.stdout)


@pytest.mark.parametrize(("unit", "count"), HOSTILE_COMPARE.values(), ids=HOSTILE_COMPARE.keys())
def test_hostile_input_compares_in_bounded_time(tmp_path: Path, unit: str, count: int) -> None:
    target = tmp_path / "hostile.md"
    target.write_text(unit * count, encoding="utf-8", newline="")
    result = run_cli("--compare", str(target), str(target), "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["compare"]["findings"] == []


def test_compare_aligns_a_dropped_block() -> None:
    fence = "~~~\n{}\n~~~\n"
    original = fence.format("keep") + fence.format("old") + fence.format("tail")
    revised = fence.format("keep") + fence.format("tail")
    findings = H.compare_texts(original, revised, "a.md", "b.md")["findings"]
    assert [item["id"] for item in findings] == ["compare.code_block.dropped"]
    assert findings[0]["line"] == 4


def test_compare_past_the_exact_diff_limit_reports_the_surplus() -> None:
    # 20,000 copies of one quote against 99 of it is 1,980,000 equal pairs,
    # past the limit, so tokens are matched by count instead.
    original = '"abc" ' * 20000
    revised = '"abc" "xyz" ' * 99
    findings = H.compare_texts(original, revised, "a.md", "b.md")["findings"]
    ids = [item["id"] for item in findings]
    assert ids.count("compare.quote.dropped") == 19901
    assert ids.count("compare.quote.introduced") == 99
    assert len(ids) == 20000


OLD_REGEXES = {
    "REF_TAG_RE": re.compile(r"<ref\b[^>]*(?:/>|>.*?</ref>)", re.I | re.S),
    "CITE_TEMPLATE_RE": re.compile(r"{{\s*cite\b.*?}}", re.I | re.S),
    "QUOTE_RE": re.compile(r'"[^"\n]{3,}"|“[^”\n]{3,}”'),
    "CODE_BLOCK_RE": re.compile(r"^[ \t]*(```|~~~)[^\n`~]*\n(?:.*?\n)?[ \t]*\1[ \t]*$", re.M | re.S),
    "INLINE_CODE_RE": re.compile(r"(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)"),
    "PERCENT_RE": re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?%"),
    "RANGE_RE": re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:-|–|—|to)\s*\d[\d,]*(?:\.\d+)?\b", re.I),
    "NAME_RE": re.compile(
        r"\b[A-Z][A-Za-z0-9'.&-]+(?:\s+(?:of|the|and|for|de|del|la|le|du|van|von|&|"
        r"[A-Z][A-Za-z0-9'.&-]+)){1,}",
    ),
}

# Characters each scanner's regex is sensitive to, for the random check.
FUZZ_PIECES = {
    "REF_TAG_RE": ["<ref", ">", "/>", "</ref>", " name=a", "x", "\n"],
    "CITE_TEMPLATE_RE": ["{{", "}}", "cite", " ", "x", "\n"],
    "QUOTE_RE": ['"', "“", "”", "a", "b", " ", "\n"],
    "CODE_BLOCK_RE": ["```", "~~~", "````", "```py", "\n", "x", " "],
    "INLINE_CODE_RE": ["`", "`", "a", " ", "\n"],
    "PERCENT_RE": ["1", "2", ",", ".", "%", " ", "-", "to", "A", "b"],
    "RANGE_RE": ["1", "2", ",", ".", "–", "-", " ", "to"],
    "NAME_RE": ["A", "b", "Z", ".", "'", "&", "-", " ", "of", "1", "\n"],
}


def spans(regex: object, text: str) -> list[tuple[int, int, str]]:
    return [(match.start(), match.end(), match.group(0)) for match in regex.finditer(text)]


def test_scanners_match_the_regexes_they_replace() -> None:
    # Characterization: the linear scanners must return the same matches the
    # old regexes did on ordinary markup.
    text = (
        "```py\ncode\n```\nprose ``` inline\n~~~\nunclosed\n"
        '<ref name="a" /> and <ref>x</ref> and <ref>open\n'
        "{{cite web|a}} {{ cite book }} {{cite\n"
        "“one” “ab” “two\nlines” \"plain\" \"ab\"\n"
        "a ``x`` b `y`` z` ``q\n`` w `` `k` ````\n"
        "Up 12% to 1,200.5 % from 3-4 and 5 to 6. St.John of the Bay met A.B. Smith & Co.\n"
    )
    for name, regex in OLD_REGEXES.items():
        assert spans(getattr(H, name), text) == spans(regex, text), name
    assert [match.group(0) for match in H.CODE_BLOCK_RE.finditer(text)] == ["```py\ncode\n```"]


@pytest.mark.parametrize("name", OLD_REGEXES)
def test_scanners_match_the_old_regexes_on_random_text(name: str) -> None:
    rng = random.Random(name)
    pieces = FUZZ_PIECES[name]
    for _ in range(3000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 30)))
        assert spans(getattr(H, name), text) == spans(OLD_REGEXES[name], text), repr(text)


def test_fence_closes_on_the_next_line_only_without_a_later_closer() -> None:
    # The old regex let an empty block close on the very next line only when
    # no closer existed further down.
    assert spans(H.CODE_BLOCK_RE, "```\n```\nprose\n```\n") == [(0, 17, "```\n```\nprose\n```")]
    assert spans(H.CODE_BLOCK_RE, "```\n```\n") == [(0, 7, "```\n```")]


def test_inline_code_known_values() -> None:
    text = "a ``x`` b `y`` z` ``q\n`` w `` `k` ````\n"
    assert [match.group(0) for match in H.INLINE_CODE_RE.finditer(text)] == ["``x``", "`y`` z`", "`` w ``", "`k`"]


def test_bullet_lengths_count_only_space_or_tab_bullets() -> None:
    # bullet_count matches "-" followed by a space or tab; the length list
    # used \s, which also took a no-break space.
    assert H.bullet_item_lengths("- not a bullet\n- a bullet\n") == [2]


def test_quote_spans_known_values() -> None:
    text = "“ab” “abc” “x\ny” “a “bcd”"
    assert H.QUOTE_RE.findall(text) == ["“abc”", "“a “bcd”"]


def test_display_safe_escapes_line_breaks_and_terminal_codes() -> None:
    assert H.display_safe("a\nb") == "a\\nb"
    assert H.display_safe("\x1b[31m") == "\\x1b[31m"
    assert H.display_safe("x y\u0085") == "x\\u2028y\\x85"
    assert H.display_safe("plain “text” é") == "plain “text” é"


def test_crafted_file_name_cannot_start_a_workflow_command(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Windows file names cannot contain a newline")
    target = tmp_path / "x\n::warning::injected.md"
    target.write_text("A plain sentence.\n", encoding="utf-8")
    result = run_cli(str(target))
    assert not any(line.startswith("::") for line in result.stdout.splitlines()), result.stdout
    assert "\\n::warning::injected.md" in result.stdout


def test_report_escapes_control_characters_in_paths_and_evidence() -> None:
    # \s+ collapsing already folded newlines out of evidence; an escape
    # sequence or a NUL is not whitespace and reached the terminal as-is.
    text = "Leftover <grok-card \x1b[2J\x00> card.\n"
    document = H.audit_text(text, "doc\x1b]0;title\x07.md")
    report = H.render_text_report(
        {
            "summary": {"documents": 1, "max_risk_score": 0, "max_severity": "info", "exit_code": 0},
            "documents": [document],
        }
    )
    assert any("grok" in str(finding["evidence"]) for finding in document["findings"])
    assert not H.CONTROL_CHAR_RE.search(report.replace("\n", ""))
    assert "\\x1b[2J" in report
    assert "doc\\x1b]0;title\\x07.md" in report


@pytest.mark.parametrize("path", ["::warning::y.md", "  ::error title=x::y.md"])
def test_report_line_cannot_open_with_a_workflow_command(path: str) -> None:
    # A file named "::warning::y.md" in an audited tree printed as its own
    # report line; the runner trims the indent before it reads a command.
    document = H.audit_text("A plain sentence.\n", path)
    report = H.render_text_report(
        {
            "summary": {"documents": 1, "max_risk_score": 0, "max_severity": "info", "exit_code": 0},
            "documents": [document],
        }
    )
    assert not any(line.lstrip().startswith("::") for line in report.splitlines()), report
    assert "\\x3a:" in report


def test_sarif_uri_survives_an_undecodable_file_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert H.sarif_uri(str(tmp_path / "bad\udcffname.md")) == "bad%FFname.md"


def test_internal_error_exits_3(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def explode(argv: list[str] | None = None) -> int:
        raise RuntimeError("boom\n::error::x")

    monkeypatch.setattr(H, "run", explode)
    assert H.main(["doc.md"]) == 3
    assert "internal error: RuntimeError: boom\\n::error::x" in capsys.readouterr().err


def test_directory_walk_skips_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret text\n", encoding="utf-8")
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "real.md").write_text("A plain sentence.\n", encoding="utf-8")
    try:
        (tree / "link.md").symlink_to(outside)
    except OSError:
        pytest.skip("this account cannot create symlinks")
    assert [path.name for path in H.iter_input_files(tree)] == ["real.md"]


def test_named_symlink_target_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret text\n", encoding="utf-8")
    tree = tmp_path / "tree"
    tree.mkdir()
    try:
        (tree / "link.md").symlink_to(outside)
        (tree / "linkdir").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("this account cannot create symlinks")
    monkeypatch.chdir(tree)
    assert H.iter_input_files(Path("link.md")) == []
    assert H.iter_input_files(Path("linkdir/outside.md")) == []
    assert H.iter_input_files(tree / "link.md") == []
    result = run_cli(str(tree / "link.md"), "--json")
    assert "secret text" not in result.stdout
    assert "skipped symlink" in result.stderr


def test_publish_checks_out_a_tag_ref() -> None:
    publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "ref: refs/tags/${{ inputs.tag || github.event.release.tag_name }}" in publish
    assert re.search(r"pip install build==\d", publish)


def test_action_pauses_workflow_commands_around_the_report() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    pause = action.index('echo "::stop-commands::$stop_token"')
    run = action.index('"$python_bin" "$HA_SCRIPT"')
    resume = action.index('echo "::$stop_token::"')
    assert pause < run < resume
    assert "secrets.token_hex" in action
