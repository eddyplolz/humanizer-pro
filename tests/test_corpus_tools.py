from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "corpus" / "manifest.json"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


corpus = load_module("corpus")
fp_measure = load_module("fp_measure")


# ------------------------------------------------------------- extraction


def test_bbcode_strip_removes_quotes_and_unwraps_tags() -> None:
    message = (
        "[quote=Someone]their words, not mine[/quote]"
        "My [b]own[/b] reply about the treaty.\\r\\n\\r\\nIt stands."
    )
    text = corpus.bbcode_strip(message)
    assert "their words" not in text
    assert "My own reply about the treaty." in text
    assert "It stands." in text
    assert "[b]" not in text and "\\r" not in text


def test_bbcode_strip_removes_nested_quotes_inside_out() -> None:
    message = "[quote=A][quote=B]inner[/quote]A's own words here[/quote]My reply."
    assert corpus.bbcode_strip(message) == "My reply."


def test_bbcode_strip_unescapes_sql_in_one_pass() -> None:
    # The dump text C:\\new is an escaped backslash followed by "n".
    assert corpus.bbcode_strip(r"C:\\new and \'q\' \"x\"\r\nnext") == 'C:\\new and \'q\' "x"\nnext'


def test_mybb_rows_carry_edittime_when_present(tmp_path) -> None:
    sql = (
        "INSERT INTO `mybb_posts` (`pid`) VALUES "
        "(1,2,0,3,'S',0,7,'alice',1500000000,'old post',0x7f000001,1,0,0,0,'',1),"
        "(2,2,0,3,'S',0,7,'alice',1500000000,'edited later',_binary 'ab',1,0,7,1700000000,'',1),"
        "(3,2,0,3,'S',0,7,'bob',1500000000,'no tail');\n"
    )
    dump = tmp_path / "x_sanitized.sql"
    dump.write_text(sql, encoding="utf-8")
    rows = list(corpus.iter_mybb_posts(dump))
    assert [(pid, edittime) for pid, _user, _date, _msg, edittime in rows] == [
        (1, 0), (2, 1700000000), (3, None),
    ]


def test_wikitext_strip_v2_handles_nesting_v1_kept_for_old_digests() -> None:
    nested = "A [[File:x.jpg|thumb|A [[Foo]] map]] B {{a|{{b|{{c|{{d|{{e|{{f}}}}}}}}}}}} C"
    assert corpus.wikitext_strip(nested) == "A B C"
    # v1 is frozen: existing wiki entries were hashed with it.
    assert "map]]" in corpus.wikitext_strip_v1(nested)
    assert corpus.WIKITEXT_STRIPPERS["wikitext-strip.v1"] is corpus.wikitext_strip_v1


def test_word_count_treats_curly_apostrophe_as_inside_a_word() -> None:
    assert corpus.word_count("don’t stop") == 2
    assert corpus.alpha_ratio("don’t stop’") == 1.0


def test_wikitext_strip_reduces_markup_to_prose() -> None:
    wikitext = (
        "{{Infobox nation|name=Testland}}\n"
        "== History ==\n"
        "The '''Republic''' was founded in [[Examplia|the old kingdom]] "
        "in 1699.<ref>Chronicle, vol. 2</ref>\n"
        "[[Category:Nations]]\n"
    )
    text = corpus.wikitext_strip(wikitext)
    assert "Infobox" not in text
    assert "Chronicle" not in text
    assert "Category:" not in text
    assert "[[" not in text and "'''" not in text
    assert "The Republic was founded in the old kingdom in 1699." in text
    assert "History" in text


# ---------------------------------------------------------------- wilson


def test_wilson_interval_known_values() -> None:
    # Published Wilson 95% interval for 5 successes in 100 trials.
    low, high = fp_measure.wilson_interval(5, 100)
    assert low == pytest.approx(0.0215, abs=0.0005)
    assert high == pytest.approx(0.1118, abs=0.0005)
    assert fp_measure.wilson_interval(0, 0) == (0.0, 1.0)
    zero_low, zero_high = fp_measure.wilson_interval(0, 764)
    assert zero_low == 0.0
    assert zero_high < 0.01  # large clean sample gives a tight upper bound


def test_slice_stats_literal() -> None:
    rows = [
        {"risk": 70, "blocked": False},
        {"risk": 10, "blocked": False},
        {"risk": 65, "blocked": True},
        {"risk": 0, "blocked": False},
    ]
    stats = fp_measure.slice_stats(rows, threshold=60)
    assert stats["n"] == 4
    assert stats["flagged"] == 2
    assert stats["fpr"] == 0.5
    assert stats["blocked"] == 1


def test_blocked_document_counts_as_flagged_at_any_score() -> None:
    rows = [{"risk": 10, "blocked": True}, {"risk": 0, "blocked": False}]
    stats = fp_measure.slice_stats(rows, threshold=60)
    assert stats["flagged"] == 1
    assert stats["fpr"] == 0.5


def test_median_risk_is_a_true_median() -> None:
    rows = [{"risk": 0, "blocked": False}, {"risk": 100, "blocked": False}]
    assert fp_measure.slice_stats(rows, threshold=60)["median_risk"] == 50


def test_results_page_handles_empty_cache_and_threshold_label() -> None:
    empty = {
        "threshold": 40, "corpus_documents": 0, "missing_cache": ["x"],
        "overall": fp_measure.slice_stats([], 40), "by_register": {}, "by_author": {},
        "threshold_sweep_fpr": {"40": {}}, "top_rules_on_human_text": [],
        "machine_documents": 0, "human_dev_documents": 0, "catch_rate": None, "rule_scorecard": [],
    }
    page = fp_measure.render_results_md(empty)
    assert "(the CLI default)" not in page
    assert "| Threshold |  |" not in page


# --------------------------------------------------------------- manifest


def test_manifest_is_structurally_sound() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema"] == "humanizer-corpus-manifest.v1"
    assert manifest["cutoff"] == "2022-11-01"
    entries = manifest["entries"]
    assert entries, "manifest must not be empty"
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids)), "entry ids must be unique"
    for entry in entries:
        assert entry["kind"] in corpus.ID_PREFIX
        # The maintainer's own writing never enters the public manifest.
        assert entry["kind"] not in corpus.PRIVATE_KINDS, entry["id"]
        assert entry["register"] in corpus.MIN_WORDS
        machine = entry["kind"] in corpus.MACHINE_KINDS
        assert entry["label"] == ("machine" if machine else "human")
        if machine:
            assert entry["author"] == "machine"
            assert entry["model"]
            assert entry["split"] == corpus.digest_split(entry["sha256"])
        else:
            assert entry["author"] in ("maintainer", "other", "public-domain", "mixed")
            assert "model" not in entry and "split" not in entry
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        prefix = corpus.ID_PREFIX[entry["kind"]]
        assert re.fullmatch(rf"{prefix}-[0-9a-f]{{12}}", entry["id"])
        assert entry["id"].split("-", 1)[1] == entry["sha256"][:12]
        assert entry["words"] >= 50
    # Only totals are public for the private pools.
    for kind, pool in manifest.get("private_pools", {}).items():
        assert kind in corpus.PRIVATE_KINDS
        assert set(pool) == {"entries", "registers"}
        assert pool["entries"] == sum(pool["registers"].values())


def test_manifest_is_anonymous() -> None:
    """Hash-only AND anonymous: no text, no usernames, no personal locators.

    Only public-domain pools (Strunk chunks, Gutenberg works, Internet
    Archive news chunks) may carry a source, and only public-domain pointers.
    The forum and wiki pools must never publish a locator of any kind.
    """
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]
    public_keys = {
        "id", "kind", "label", "register", "author", "date", "words",
        "sha256", "extraction", "source", "model", "split",
    }
    source_keys = {
        "public-domain": {"work", "chunk", "chunk_words"},
        "gutenberg-work": {"work", "gutenberg_id", "url", "chunk", "chunk_words"},
        "news-page": {"url", "ia_identifier", "chunk"},
        "hf-news": {"dataset", "id", "date", "file_name", "chunk"},
        "pep-chunk": {"repo", "commit", "path", "chunk"},
        "raid-generation": {"dataset", "file", "id"},
        "wildchat-turn": {"dataset", "conversation_hash"},
        "generated": {"prompt_id", "requested_model"},
    }
    assert set(source_keys) == set(corpus.PUBLIC_SOURCE_KINDS)
    for entry in entries:
        assert set(entry) <= public_keys
        if entry["kind"] in source_keys:
            # A public kind must publish its pointer, and only scalar values.
            assert entry["source"], f"{entry['id']} has no public source"
            assert set(entry["source"]) <= source_keys[entry["kind"]]
            assert all(isinstance(v, (str, int)) for v in entry["source"].values())
        else:
            assert "source" not in entry, f"{entry['id']} leaks a source locator"
            assert entry["author"] in ("maintainer", "other", "mixed")
            if entry["kind"] == "wiki-revision":
                # A wiki page can hold other editors' text.
                assert entry["author"] == "mixed"


# ------------------------------------------------------------ fp_measure


def test_audit_corpus_accounts_for_every_entry() -> None:
    """Audited + missing must cover the manifest exactly, cache or no cache.

    On a fresh clone the cache is empty (it is gitignored), so every entry
    lands in `missing`; after corpus.py fetch/build they land in `rows`.
    """
    # Public entries plus, on the maintainer's machine, the private ones.
    manifest = corpus.load_manifest()
    rows, missing = fp_measure.audit_corpus(threshold=60)
    assert len(rows) + len(missing) == len(manifest["entries"])


def test_audit_corpus_audits_cached_entries(tmp_path, monkeypatch) -> None:
    """With a cache present, entries are audited, not just counted missing."""
    cached = "pd-0123456789ab"
    manifest = {
        "entries": [
            {"id": cached, "register": "essay", "author": "public-domain", "words": 9, "sha256": "f" * 64},
            {"id": "pd-ba9876543210", "register": "essay", "author": "public-domain", "words": 9, "sha256": "f" * 64},
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f"{cached}.txt").write_text("[Your Name] wrote this.", encoding="utf-8")
    monkeypatch.setattr(fp_measure, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(fp_measure, "PRIVATE_MANIFEST_PATH", tmp_path / "manifest.private.json")
    monkeypatch.setattr(fp_measure, "CACHE_DIR", cache)
    rows, missing = fp_measure.audit_corpus(threshold=60)
    assert missing == ["pd-ba9876543210"]
    assert [row["id"] for row in rows] == [cached]
    assert rows[0]["blocked"] is True
    assert fp_measure.slice_stats(rows, 60)["flagged"] == 1


def test_fp_measure_cli_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fp_measure.py"), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "humanizer-fp-measure.v2"
    assert "by_register" in payload and "overall" in payload


def test_public_domain_pool_rebuilds_offline_without_gutenberg_boilerplate() -> None:
    """The Strunk pool is reproducible from the repo alone and holds only the
    book: no Project Gutenberg header or licence text."""
    chunks = corpus.gutenberg_chunks(corpus.PD_SOURCE.read_text(encoding="utf-8"))
    digests = {corpus.sha256_text(chunk) for chunk in chunks}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    published = {e["sha256"] for e in manifest["entries"] if e["kind"] == "public-domain"}
    assert digests == published
    for chunk in chunks:
        assert "Project Gutenberg" not in chunk
        assert "START OF" not in chunk and "END OF" not in chunk


def test_cache_path_rejects_malformed_ids() -> None:
    for bad in ("../x", "pd-../../etc", "PD-0123456789ab", "pd-0123"):
        with pytest.raises(ValueError):
            corpus.cache_path(bad)
    assert corpus.cache_path("pd-0123456789ab").name == "pd-0123456789ab.txt"


def test_cache_round_trip_is_byte_exact(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(corpus, "CACHE_DIR", tmp_path)
    text = "line one\rstill line one\nline two"
    corpus.write_cache("pd-0123456789ab", text)
    assert corpus.read_cache("pd-0123456789ab") == text



# ------------------------------------------------------- new pools (v4.14.0)


def test_digest_split_is_a_stable_quarter() -> None:
    assert corpus.digest_split("0" + "f" * 63) == "dev"
    assert corpus.digest_split("3" + "0" * 63) == "dev"
    assert corpus.digest_split("4" + "0" * 63) == "test"
    assert corpus.digest_split("f" * 64) == "test"


def test_save_pool_labels_machine_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(corpus, "PRIVATE_MANIFEST_PATH", tmp_path / "manifest.private.json")
    monkeypatch.setattr(corpus, "LOCAL_SOURCES_PATH", tmp_path / "sources.local.json")
    monkeypatch.setattr(corpus, "CACHE_DIR", tmp_path / "cache")
    fields = {"register": "wiki", "author": "machine", "model": "raid:gpt4", "date": "2023", "extraction": "x"}
    entries = corpus.save_pool("raid-generation", [(fields, f"text {i} " * 40, {"id": str(i)}) for i in range(8)])
    assert len(entries) == 8
    for entry in entries:
        assert entry["label"] == "machine" and entry["model"] == "raid:gpt4"
        assert entry["split"] == corpus.digest_split(entry["sha256"])
        assert entry["id"].startswith("raid-")
        assert entry["source"] == {"id": entry["source"]["id"]}
    human = corpus.save_pool("pep-chunk", [({"register": "docs", "author": "other", "date": "2001", "extraction": "x"}, "words " * 200, {"path": "p"})])
    assert human[0]["label"] == "human" and "split" not in human[0]


PEP_RST = """PEP: 9999
Title: An Example
Author: Someone <someone@example.org>
Status: Draft
Created: 01-Jan-2001

Abstract
========

This PEP proposes the ``frobnicate()`` builtin [1]_. See `the docs
<https://example.org>`_ and :pep:`8` for **details** on *style*.

.. note::

   An admonition that is not prose.

Example::

    def frobnicate():
        return 42

* A first bullet point about the design.
* A second bullet point.

+------+------+
| grid | cell |
+------+------+

References
==========

.. [1] A citation.

Copyright
=========

This document has been placed in the public domain.
"""


def test_rst_strip_keeps_paragraph_breaks_around_skipped_blocks() -> None:
    text = corpus.rst_strip(
        "Intro.\n\n.. note::\n\n   hidden\n\nAfter the directive.\n\n"
        "* bullet one\n* bullet two\n\nThe example::\n\n    code\n\ncontinues here.\n"
    )
    assert text == (
        "Intro.\n\nAfter the directive.\n\nbullet one\nbullet two\n\nThe example:\n\ncontinues here."
    )


def test_rst_strip_keeps_prose_and_drops_markup() -> None:
    text = corpus.rst_strip(PEP_RST)
    assert "PEP: 9999" not in text and "Created:" not in text
    assert "This PEP proposes the frobnicate() builtin. See the docs and 8 for details on style." in text
    assert "admonition" not in text
    assert "Example:" in text and "return 42" not in text
    assert "A first bullet point about the design." in text and "* " not in text
    assert "grid" not in text and "====" not in text
    assert "citation" not in text and "public domain" not in text


def test_pep_pairs_filters_licence_and_caps_chunks() -> None:
    long_body = "\n\n".join(f"Paragraph {i} " + "word " * 120 for i in range(12))
    pep = PEP_RST.replace("Abstract\n========\n", "Abstract\n========\n\n" + long_body + "\n")
    not_pd = pep.replace("placed in the public domain", "licensed under some terms")
    pairs, dropped = corpus.pep_pairs([("pep-9999.txt", pep), ("pep-9998.txt", not_pd)], "abc123", 50)
    assert dropped["not-public-domain"] == 1
    assert len(pairs) == corpus.PEP_CHUNKS_PER_PEP
    meta, text, source = pairs[0]
    assert meta == {"register": "docs", "author": "other", "date": "2001", "extraction": corpus.RST_STRIP_VERSION}
    assert source == {"repo": "python/peps", "commit": "abc123", "path": "pep-9999.txt", "chunk": 1}
    assert corpus.word_count(text) >= corpus.PEP_CHUNK_WORDS
    assert len(corpus.pep_pairs([("pep-9999.txt", pep)], "abc123", 1)[0]) == 1


def _raid_row(**overrides) -> dict:
    row = {
        "id": "u1", "model": "gpt4", "domain": "wiki", "decoding": "sampling",
        "repetition_penalty": "no", "attack": "none", "generation": "word " * 200,
    }
    row.update(overrides)
    return row


def test_raid_pairs_filters_and_fills_cells() -> None:
    rows = [
        _raid_row(id="a"),
        _raid_row(id="b"),  # over the per-cell quota of 1
        _raid_row(id="c", model="gpt2"),  # base model: excluded
        _raid_row(id="d", decoding="greedy"),
        _raid_row(id="e", repetition_penalty="yes"),
        _raid_row(id="f", domain="poetry"),
        _raid_row(id="g", domain="reddit", model="llama-chat", generation="word " * 60),
        _raid_row(id="h", domain="news", generation="too short"),
        _raid_row(id="i", model="human"),
    ]
    pairs, dropped = corpus.raid_pairs(rows, per_cell=1)
    assert [source["id"] for _meta, _text, source in pairs] == ["a", "g"]
    assert pairs[0][0]["register"] == "wiki" and pairs[0][0]["model"] == "raid:gpt4"
    assert pairs[1][0]["register"] == "chat"
    assert dropped["decoding-or-attack"] == 2 and dropped["under-min-words"] == 1


def test_wildchat_pairs_takes_first_prose_reply() -> None:
    def row(**overrides):
        base = {
            "conversation_hash": "h1", "model": "gpt-4", "language": "English",
            "timestamp": "2023-05-02T10:00:00Z",
            "conversation": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "reply " * 80},
                {"role": "assistant", "content": "second " * 80},
            ],
        }
        base.update(overrides)
        return base

    rows = [
        row(),
        row(conversation_hash="h2", language="Chinese"),
        row(conversation_hash="h3", conversation=[{"role": "assistant", "content": "```py\nx\n```" + " w" * 80}]),
        row(conversation_hash="h4", conversation=[{"role": "assistant", "content": "short"}]),
    ]
    pairs, dropped = corpus.wildchat_pairs(rows, target=10)
    assert len(pairs) == 1
    meta, text, source = pairs[0]
    assert text.startswith("reply") and "second" not in text
    assert meta["model"] == "wildchat:gpt-4" and meta["date"] == "2023-05" and meta["register"] == "chat"
    assert source == {"dataset": "allenai/WildChat-1M", "conversation_hash": "h1"}
    assert dropped == {"not-english": 1, "code-reply": 1, "word-band": 1}


# ------------------------------------------------------- generate_machine.py


generate = load_module("generate_machine")


class _FakeErrors:
    class APIStatusError(Exception):
        pass

    class RateLimitError(APIStatusError):
        pass

    class AuthenticationError(APIStatusError):
        pass

    class PermissionDeniedError(APIStatusError):
        pass

    class NotFoundError(APIStatusError):
        pass

    class BadRequestError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass


class _FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.messages = self

    def create(self, **request):
        from types import SimpleNamespace as NS

        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        stop_reason, text = step
        content = [NS(type="thinking", thinking=""), NS(type="text", text=text)]
        return NS(stop_reason=stop_reason, content=content, model=request["model"] + "-served")


def test_generate_pairs_labels_and_skips() -> None:
    prompts = [{"id": "wiki-01", "register": "wiki", "prompt": "Write about X."}]
    models = ["claude-opus-5-5", "claude-haiku-4-5", "m3", "m4", "m5"]
    long_text = "word " * 200
    client = _FakeClient([
        ("end_turn", long_text),
        ("end_turn", long_text),
        ("refusal", ""),
        ("max_tokens", long_text),
        _FakeErrors.RateLimitError("slow down"),
    ])
    pairs, counts = generate.generate_pairs(client, _FakeErrors, prompts, models, 16000, "low")
    assert counts == {"kept": 2, "refused": 1, "truncated": 1, "api-error": 1}
    assert [meta["model"] for meta, _t, _s in pairs] == [
        "anthropic:claude-opus-5-5-served", "anthropic:claude-haiku-4-5-served",
    ]
    assert pairs[0][1] == long_text.strip()  # text blocks only
    assert pairs[0][2] == {"prompt_id": "wiki-01", "requested_model": "claude-opus-5-5"}
    assert client.requests[0]["output_config"] == {"effort": "low"}
    assert "output_config" not in client.requests[1]  # Haiku rejects effort
    assert "fallbacks" not in client.requests[0]  # labels must stay exact


def test_generate_pairs_stops_on_configuration_errors() -> None:
    prompts = [{"id": "wiki-01", "register": "wiki", "prompt": "x"}]
    client = _FakeClient([_FakeErrors.NotFoundError("no such model")])
    with pytest.raises(_FakeErrors.NotFoundError):
        generate.generate_pairs(client, _FakeErrors, prompts, ["bad-model"], 100, None)


def test_committed_prompts_are_valid_and_cover_four_registers() -> None:
    prompts = generate.load_prompts()
    registers = {item["register"] for item in prompts}
    assert registers == {"wiki", "news", "essay", "docs"}
    assert len(prompts) >= 50
    for item in prompts:
        lowered = item["prompt"].lower()
        # Plain requests: no steering toward or away from any style.
        assert "ai" not in lowered.split() and "human" not in lowered and "tell" not in lowered


def test_generate_dry_run_calls_nothing(capsys) -> None:
    assert generate.main(["--dry-run", "--limit", "2", "--models", "a", "b"]) == 0
    assert "2 prompts x 2 models = 4 requests" in capsys.readouterr().out



# ------------------------------------------------- two-way measurement


SLOP = "Of course! Here's a polished, vibrant tapestry. I hope this helps! Let me know if you need more."
PLAIN = "The committee met on Tuesday and approved the budget for the new library wing."


def _measure_fixture(tmp_path, monkeypatch, entries):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"entries": [e for e, _t in entries]}), encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    for entry, text in entries:
        (cache / f"{entry['id']}.txt").write_text(text, encoding="utf-8")
    monkeypatch.setattr(fp_measure, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(fp_measure, "PRIVATE_MANIFEST_PATH", tmp_path / "manifest.private.json")
    monkeypatch.setattr(fp_measure, "CACHE_DIR", cache)
    return fp_measure.measure(threshold=5, include_fixture_tp=False)


def _entry(entry_id, label, register="wiki", split="test", model=None):
    # The digest's first hex digit decides the split: 0-3 dev, else test.
    digest = ("0" if split == "dev" else "f") * 64
    entry = {"id": entry_id, "label": label, "register": register, "author": "other", "words": 20, "sha256": digest}
    if label == "machine":
        entry.update({"split": split, "model": model, "author": "machine"})
    return entry


def test_measure_keeps_machine_rows_out_of_fpr(tmp_path, monkeypatch) -> None:
    result = _measure_fixture(tmp_path, monkeypatch, [
        (_entry("wiki-000000000001", "human"), PLAIN),
        (_entry("wiki-000000000002", "human"), PLAIN),
        # Human dev documents feed only the scorecard, never the published FPR.
        (_entry("wiki-000000000006", "human", split="dev"), SLOP),
        (_entry("wiki-000000000007", "human", split="dev"), PLAIN),
        (_entry("raid-000000000003", "machine", split="test", model="raid:gpt4"), SLOP),
        (_entry("raid-000000000004", "machine", split="test", model="raid:gpt4"), PLAIN),
        (_entry("raid-000000000005", "machine", split="dev", model="raid:gpt4"), SLOP),
    ])
    assert result["corpus_documents"] == 2 and result["machine_documents"] == 3
    assert result["human_dev_documents"] == 2
    assert result["overall"]["n"] == 2 and result["overall"]["flagged"] == 0
    catch = result["catch_rate"]
    assert catch["split"] == "test"
    assert catch["overall"]["n"] == 2 and catch["overall"]["caught"] == 1
    assert catch["by_model"]["raid:gpt4"]["rate"] == 0.5
    assert catch["by_register"]["wiki"]["n"] == 2
    card = {item["rule"]: item for item in result["rule_scorecard"]}
    residue = card["family9.chatbot_residue"]
    assert residue["machine_share"] == 1.0  # the one machine dev document
    assert residue["human_share"] == 0.5 and residue["ratio"] == 2.0  # 1 of 2 human dev
    page = fp_measure.render_results_md(result)
    assert "## Catch rate on machine text (test split)" in page
    assert "| model: `raid:gpt4` | 2 | 1 | 50.0% |" in page
    assert "## Rule scorecard" in page


def test_measure_without_machine_rows_says_not_measured(tmp_path, monkeypatch) -> None:
    result = _measure_fixture(tmp_path, monkeypatch, [(_entry("wiki-000000000001", "human"), PLAIN)])
    assert result["catch_rate"] is None and result["rule_scorecard"] == []
    assert "Not measured yet" in fp_measure.render_results_md(result)
    assert "Catch rate: not measured" in fp_measure.render_text(result)



def test_generate_trial_run_and_empty_run_never_touch_the_pool(monkeypatch, capsys) -> None:
    import types

    saved = []
    monkeypatch.setattr(generate.corpus, "save_pool", lambda kind, pairs: saved.append(pairs) or [])
    fake = types.SimpleNamespace(
        Anthropic=lambda **_kw: _FakeClient([("end_turn", "word " * 200)] * 10 + [("refusal", "")] * 10),
        **{name: getattr(_FakeErrors, name) for name in dir(_FakeErrors) if not name.startswith("_")},
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    assert generate.main(["--limit", "1", "--models", "m1"]) == 0
    assert saved == [] and "trial run" in capsys.readouterr().out
    fake.Anthropic = lambda **_kw: _FakeClient([("refusal", "")] * 200)
    assert generate.main(["--models", "m1"]) == 1
    assert saved == []


def test_wildchat_build_keeps_the_pool_when_nothing_arrives(monkeypatch) -> None:
    saved = []
    monkeypatch.setattr(corpus, "save_pool", lambda kind, pairs: saved.append(kind) or [])

    def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(corpus, "fetch_text_with_retry", offline)
    import argparse

    assert corpus.build_wildchat(argparse.Namespace(target=10, sleep=0)) == 1
    assert corpus.build_peps(argparse.Namespace(target=10, sleep=0)) == 1
    assert saved == []


def test_private_pools_never_reach_the_public_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(corpus, "PRIVATE_MANIFEST_PATH", tmp_path / "manifest.private.json")
    forum = {"id": "forum-0123456789ab", "kind": "forum-post", "register": "chat", "author": "maintainer",
             "sha256": "0123456789ab" + "0" * 52, "words": 60}
    pd = {"id": "pd-ba9876543210", "kind": "public-domain", "register": "essay", "author": "public-domain",
          "sha256": "ba9876543210" + "0" * 52, "words": 600}
    corpus.save_manifest({"schema": corpus.MANIFEST_SCHEMA, "cutoff": corpus.CUTOFF, "entries": [forum, pd]})
    public_text = (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "forum-0123456789ab" not in public_text and "0123456789ab" not in public_text
    public = json.loads(public_text)
    assert [e["id"] for e in public["entries"]] == ["pd-ba9876543210"]
    assert public["private_pools"] == {"forum-post": {"entries": 1, "registers": {"chat": 1}}}
    assert {e["id"] for e in corpus.load_manifest()["entries"]} == {"forum-0123456789ab", "pd-ba9876543210"}
    # A public clone (no private file) keeps the published totals when it saves.
    (tmp_path / "manifest.private.json").unlink()
    corpus.save_manifest(corpus.load_manifest())
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["private_pools"] == public["private_pools"]
