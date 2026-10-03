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


def test_wikitext_strip_reduces_markup_to_prose() -> None:
    wikitext = (
        "{{Infobox nation|name=Testland}}\n"
        "== History ==\n"
        "The '''Republic''' was founded in [[Alduria|the old kingdom]] "
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
        assert entry["kind"] in (
            "forum-post", "wiki-revision", "public-domain", "news-page",
            "gutenberg-work", "hf-news",
        )
        assert entry["register"] in ("chat", "wiki", "essay", "news")
        assert entry["label"] == "human"
        assert entry["author"] in ("maintainer", "other", "public-domain")
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert re.fullmatch(r"(forum|wiki|pd|news|guten|hfnews)-[0-9a-f]{12}", entry["id"])
        assert entry["id"].split("-", 1)[1] == entry["sha256"][:12]
        assert entry["words"] >= 50


def test_manifest_is_anonymous() -> None:
    """Hash-only AND anonymous: no text, no usernames, no personal locators.

    Only public-domain pools (Strunk chunks, Gutenberg works, Internet
    Archive news chunks) may carry a source, and only public-domain pointers.
    The forum and wiki pools must never publish a locator of any kind.
    """
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]
    public_keys = {
        "id", "kind", "label", "register", "author", "date", "words",
        "sha256", "extraction", "source",
    }
    source_keys = {
        "public-domain": {"work", "chunk", "chunk_words"},
        "gutenberg-work": {"work", "gutenberg_id", "url", "chunk", "chunk_words"},
        "news-page": {"url", "ia_identifier", "chunk"},
        "hf-news": {"dataset", "id", "date", "file_name", "chunk"},
    }
    for entry in entries:
        assert set(entry) <= public_keys
        if entry["kind"] in source_keys:
            assert set(entry.get("source", {})) <= source_keys[entry["kind"]]
        else:
            assert "source" not in entry, f"{entry['id']} leaks a source locator"


# ------------------------------------------------------------ fp_measure


def test_audit_corpus_accounts_for_every_entry() -> None:
    """Audited + missing must cover the manifest exactly, cache or no cache.

    On a fresh clone the cache is empty (it is gitignored), so every entry
    lands in `missing`; after corpus.py fetch/build they land in `rows`.
    """
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows, missing = fp_measure.audit_corpus(threshold=60)
    assert len(rows) + len(missing) == len(manifest["entries"])


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
    assert payload["schema"] == "humanizer-fp-measure.v1"
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
