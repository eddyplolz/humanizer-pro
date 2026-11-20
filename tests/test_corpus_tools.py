from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
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
        "register_curves": {}, "policy_caps": {"cap": 0.01, "by_register": {}},
        "top_rules_on_human_text": [],
        "machine_documents": 0, "human_dev_documents": 0, "catch_rate": None, "rule_scorecard": [],
    }
    page = fp_measure.render_results_md(empty)
    assert "(the CLI default)" not in page
    assert "| Threshold |  |" not in page
    assert "## Separation by register" not in page


# ------------------------------------------------------- threshold sweep


def risk_rows(risks: list[int], blocked: bool = False, **fields) -> list[dict]:
    return [{"risk": risk, "blocked": blocked, **fields} for risk in risks]


def test_auroc_counts_ties_as_half() -> None:
    # Machine 20 beats human 10, ties 20, loses to 30 (1.5 of 3); machine 40
    # beats all three (3 of 3). 4.5 of 6 pairs = 0.75.
    human = risk_rows([10, 20, 30])
    machine = risk_rows([20, 40])
    assert fp_measure.auroc(human, machine) == 0.75


def test_auroc_ranks_a_block_above_every_score() -> None:
    # A blocked document is flagged at every threshold, so it outranks a
    # human document with a high score but no block.
    human = risk_rows([90])
    machine = risk_rows([5], blocked=True)
    assert fp_measure.auroc(human, machine) == 1.0
    assert fp_measure.auroc([], machine) is None
    assert fp_measure.auroc(human, []) is None
    # A blocked human document outranks a machine document at 90.
    assert fp_measure.auroc(risk_rows([10], blocked=True), risk_rows([90])) == 0.0


def test_policy_cap_rejects_a_share_that_rounds_down_to_the_cap() -> None:
    # 10 of 996 is 1.004%: above a 1% cap, though it rounds to 1.00%.
    dev = risk_rows([0] * 986 + [60] * 10, register="chat")
    caps = fp_measure.policy_caps(dev, [], [], cap=0.01, thresholds=(50, 65))
    assert caps["by_register"]["chat"]["threshold"] == 65


def test_policy_cap_says_when_no_threshold_holds_it() -> None:
    dev = risk_rows([100] * 60, register="chat")
    entry = fp_measure.policy_caps(dev, [], [], cap=0.01)["by_register"]["chat"]
    assert entry["threshold"] is None
    assert entry["reason"] == "no threshold up to 100 holds the 1.0% cap"


def test_register_curves_cover_a_register_with_only_machine_text() -> None:
    curves = fp_measure.register_curves([], risk_rows([70], register="wiki"))
    assert curves["wiki"]["human_n"] == 0
    assert curves["wiki"]["auroc"] is None and curves["wiki"]["mean_risk_gap"] is None
    assert curves["wiki"]["points"][0] == {"threshold": 0, "fpr": None, "catch": 1.0}


def test_cli_rejects_an_fpr_cap_outside_zero_to_one() -> None:
    with pytest.raises(SystemExit):
        fp_measure.main(["--fpr-cap", "1.5"])


def test_register_curves_literal() -> None:
    human = risk_rows([0, 50, 70], register="chat")
    machine = risk_rows([50, 80], register="chat")
    curves = fp_measure.register_curves(human, machine)
    chat = curves["chat"]
    assert chat["human_n"] == 3 and chat["machine_n"] == 2
    assert chat["auroc"] == 0.75
    # Mean machine risk 65 minus mean human risk 40.
    assert chat["mean_risk_gap"] == 25.0
    points = {p["threshold"]: p for p in chat["points"]}
    assert set(points) == set(range(0, 101, 5))
    assert points[50] == {"threshold": 50, "fpr": 0.6667, "catch": 1.0}
    assert points[75] == {"threshold": 75, "fpr": 0.0, "catch": 0.5}
    assert points[0] == {"threshold": 0, "fpr": 1.0, "catch": 1.0}


def test_register_curves_without_machine_text_reports_no_catch() -> None:
    curves = fp_measure.register_curves(risk_rows([10], register="wiki"), [])
    wiki = curves["wiki"]
    assert wiki["machine_n"] == 0
    assert wiki["auroc"] is None and wiki["mean_risk_gap"] is None
    assert all(p["catch"] is None for p in wiki["points"])


def test_policy_cap_picks_on_dev_and_reports_on_test() -> None:
    # Dev: 100 human documents, one at 50 and one at 70. Threshold 50 flags
    # two (2%), threshold 55 flags one (1%), so 55 is the lowest step that
    # holds a 1% cap.
    dev = risk_rows([10] * 98 + [50, 70], register="chat")
    test_human = risk_rows([10, 60], register="chat")
    test_machine = risk_rows([56, 40], register="chat")
    caps = fp_measure.policy_caps(dev, test_human, test_machine, cap=0.01)
    assert caps["cap"] == 0.01
    chat = caps["by_register"]["chat"]
    assert chat["threshold"] == 55
    assert chat["dev_n"] == 100
    assert chat["test_fpr"] == 0.5
    assert chat["catch"] == 0.5
    assert chat["machine_n"] == 2
    assert chat["reason"] is None


def test_policy_cap_refuses_a_slice_too_small_to_hold_it() -> None:
    dev = risk_rows([10] * 10, register="wiki")
    caps = fp_measure.policy_caps(dev, risk_rows([10], register="wiki"), [], cap=0.01)
    wiki = caps["by_register"]["wiki"]
    assert wiki["threshold"] is None
    assert wiki["reason"] == "dev split has 10 human documents; the cap needs at least 50"


def test_policy_cap_reports_when_blocks_alone_break_it() -> None:
    # Two blocks in 100 documents are flagged at every threshold: 2% > 1%.
    dev = risk_rows([0] * 98, register="docs") + risk_rows([0, 0], blocked=True, register="docs")
    caps = fp_measure.policy_caps(dev, risk_rows([0], register="docs"), [], cap=0.01)
    docs = caps["by_register"]["docs"]
    assert docs["threshold"] is None
    assert docs["reason"] == "blocks alone flag 2.0% of the dev split, above the 1.0% cap"


def test_length_bands_split_by_words_and_split() -> None:
    human = (
        risk_rows([10, 30], words=120, split="dev")
        + risk_rows([20], words=150, split="dev")
        + risk_rows([5], words=600, split="test")
    )
    machine = (
        risk_rows([30, 40], words=99, split="dev")
        + risk_rows([90], words=149, split="dev")
        + risk_rows([70], words=249, split="dev")
    )
    bands = {b["band"]: b for b in fp_measure.length_bands(human, machine)}
    assert list(bands) == ["0-49", "50-99", "100-149", "150-249", "250-499", "500+"]
    # 100-149: human 10, 30 against machine 90 -> AUROC 1.0.
    assert bands["100-149"]["dev"] == {"human_n": 2, "machine_n": 1, "auroc": 1.0}
    # 150 words opens the next band: human 20 against machine 70.
    assert bands["150-249"]["dev"] == {"human_n": 1, "machine_n": 1, "auroc": 1.0}
    # 99 words stays in 50-99, which has no human text.
    assert bands["50-99"]["dev"] == {"human_n": 0, "machine_n": 2, "auroc": None}
    assert bands["500+"]["test"] == {"human_n": 1, "machine_n": 0, "auroc": None}
    assert bands["500+"]["dev"]["human_n"] == 0


def test_readability_by_register_reports_medians_and_auroc() -> None:
    human = [
        {"register": "news", "fk_grade": g} for g in (8.0, 10.0, 12.0)
    ] + [{"register": "news", "fk_grade": None}]
    machine = [{"register": "news", "fk_grade": g} for g in (12.0, 14.0)] + [{"register": "chat", "fk_grade": 6.0}]
    table = fp_measure.readability_by_register(human, machine)
    # Machine 12 beats 8 and 10, ties 12 (2.5 of 3); 14 beats all three. 5.5 of 6.
    assert table["news"] == {
        "human_n": 3, "machine_n": 2, "human_median": 10.0, "machine_median": 13.0, "auroc": round(5.5 / 6, 4),
    }
    # A document without a grade is left out, and an empty side has no AUROC.
    assert table["chat"] == {"human_n": 0, "machine_n": 1, "human_median": None, "machine_median": 6.0, "auroc": None}


def test_value_auroc_below_half_means_machine_reads_lower() -> None:
    assert fp_measure.value_auroc([10.0, 12.0], [6.0, 8.0]) == 0.0
    assert fp_measure.value_auroc([], [1.0]) is None


def test_attack_catch_rates_compare_each_attack_with_its_originals() -> None:
    machine = [
        {"risk": 70, "blocked": False, "split": "test", "raid_ref": "s1"},
        {"risk": 10, "blocked": False, "split": "test", "raid_ref": "s2"},
        {"risk": 10, "blocked": False, "split": "test", "raid_ref": None},
    ]
    attacked = [
        {"risk": 10, "blocked": False, "split": "test", "attack": "paraphrase", "raid_ref": "s1"},
        {"risk": 10, "blocked": False, "split": "test", "attack": "paraphrase", "raid_ref": "s2"},
        {"risk": 0, "blocked": True, "split": "test", "attack": "homoglyph", "raid_ref": "s2"},
        {"risk": 90, "blocked": False, "split": "dev", "attack": "homoglyph", "raid_ref": "s1"},  # dev: left out
    ]
    result = fp_measure.attack_catch_rates(attacked, machine, 60)
    para = result["by_attack"]["paraphrase"]
    assert (para["n"], para["caught"]) == (2, 0)
    assert (para["unattacked"]["n"], para["unattacked"]["caught"]) == (2, 1)
    homo = result["by_attack"]["homoglyph"]
    assert (homo["n"], homo["caught"], homo["unattacked"]["caught"]) == (1, 1, 0)
    assert (result["overall"]["n"], result["overall"]["caught"]) == (3, 1)
    assert (result["overall"]["unattacked"]["n"], result["overall"]["unattacked"]["caught"]) == (2, 1)
    assert fp_measure.attack_catch_rates([], machine, 60) is None


def test_results_page_renders_length_bands() -> None:
    cell = {"human_n": 38, "machine_n": 23, "auroc": 0.537}
    empty = {"human_n": 0, "machine_n": 4, "auroc": None}
    assert fp_measure.band_cell(cell) == "38 / 23 / 0.54"
    assert fp_measure.band_cell(empty) == "0 / 4 / -"


def test_results_page_renders_sweep_separation_and_caps() -> None:
    human = risk_rows([0, 50, 70], register="chat")
    machine = risk_rows([50, 80], register="chat")
    dev = risk_rows([10] * 98 + [50, 70], register="chat")
    result = {
        "threshold": 60, "corpus_documents": 3, "missing_cache": [],
        "overall": fp_measure.slice_stats(human, 60),
        "by_register": {"chat": fp_measure.slice_stats(human, 60)}, "by_author": {},
        "register_curves": fp_measure.register_curves(human, machine),
        "policy_caps": fp_measure.policy_caps(dev, human, machine, cap=0.01),
        "top_rules_on_human_text": [], "machine_documents": 2, "human_dev_documents": 100,
        "catch_rate": None, "rule_scorecard": [],
    }
    page = fp_measure.render_results_md(result)
    assert "| 50 | 66.7% / 100.0% |" in page
    assert "| chat | 3 | 2 | 0.75 | +25.0 |" in page
    assert "## Reading grade by register" not in page
    result["readability"] = {"chat": {"human_n": 3, "machine_n": 2, "human_median": 9.5, "machine_median": 12.0, "auroc": 0.8}}
    assert "| chat | 3 | 2 | 9.5 | 12.0 | 0.80 |" in fp_measure.render_results_md(result)
    assert "chat         9.5 / 12.0  AUROC 0.80" in fp_measure.render_text(result)
    assert "## Catch rate on attacked machine text" not in fp_measure.render_results_md(result)
    result["attack_catch_rate"] = fp_measure.attack_catch_rates(
        [{"risk": 0, "blocked": True, "split": "test", "attack": "homoglyph", "raid_ref": "s1"}],
        [{"risk": 10, "blocked": False, "split": "test", "raid_ref": "s1"}],
        60,
    )
    page = fp_measure.render_results_md(result)
    row = next(line for line in page.splitlines() if line.startswith("| homoglyph |"))
    assert row.startswith("| homoglyph | 1 | 1 | 100.0% |") and row.endswith("| 0 of 1 (0.0%) |")
    assert "all attacks" not in page
    assert "homoglyph" in fp_measure.render_text(result)
    assert "| chat | 100 | 55 | 33.3% | 50.0% |" in page
    assert "## Flag rate on grammar-edited human text" not in page
    result["polish_flag_rate"] = fp_measure.polish_flag_rates(
        [{"risk": 70, "blocked": False, "split": "test", "model": "openrouter:m1", "original_ref": "h1", "edit_share": 0.05}],
        [{"id": "h1", "risk": 10, "blocked": False, "split": "test"}],
        60,
    )
    page = fp_measure.render_results_md(result)
    assert corpus.POLISH_PROMPT in page
    row = next(line for line in page.splitlines() if line.startswith("| openrouter:m1 |"))
    assert row.startswith("| openrouter:m1 | 1 | 1 | 100.0% |") and row.endswith("| 0 of 1 (0.0%) | 5.0% | - | +60 | 100.0% | 0.0% |")
    assert "openrouter:m1" in fp_measure.render_text(result)


def test_signed_score_change() -> None:
    assert (fp_measure.signed(None), fp_measure.signed(0), fp_measure.signed(-2.5), fp_measure.signed(3)) == (
        "-", "0", "-2.5", "+3"
    )


def test_edit_shares_count_changed_and_added_words() -> None:
    assert fp_measure.edit_shares("the cat sat", "the cat sat") == (0.0, 0.0)
    assert fp_measure.edit_shares("teh cat sat down", "the cat sat down") == (0.25, 0.25)
    assert fp_measure.edit_shares("one two", "") == (1.0, 0.0)
    assert fp_measure.edit_shares("", "anything") == (0.0, 0.0)
    # An added lead-in changes nothing the person wrote but adds words.
    assert fp_measure.edit_shares("a b c d", "Here it is: a b c d") == (0.0, 0.75)


def test_polish_flag_rates_compare_each_model_with_the_originals() -> None:
    human = [
        {"id": "h1", "risk": 70, "blocked": False, "split": "test"},
        {"id": "h2", "risk": 10, "blocked": False, "split": "test"},
    ]
    polished = [
        {"risk": 70, "blocked": False, "split": "test", "model": "a", "original_ref": "h1", "edit_share": 0.1},
        {"risk": 0, "blocked": True, "split": "test", "model": "a", "original_ref": "h2", "edit_share": 0.3},
        {"risk": 10, "blocked": False, "split": "test", "model": "b", "original_ref": "h2", "edit_share": None},
        {"risk": 90, "blocked": False, "split": "dev", "model": "b", "original_ref": "h1", "edit_share": 0.0},  # dev
    ]
    result = fp_measure.polish_flag_rates(polished, human, 60)
    a = result["by_model"]["a"]
    assert (a["n"], a["caught"], a["before"]["n"], a["before"]["caught"]) == (2, 2, 2, 1)
    assert a["median_edit_share"] == 0.2 and a["median_added_share"] is None
    # h1 70 -> 70 is no change; h2 10 -> blocked ranks as 101, a rise of 91.
    assert (a["median_risk_change"], a["share_risk_rose"], a["share_risk_fell"]) == (45.5, 0.5, 0.0)
    b = result["by_model"]["b"]
    assert (b["n"], b["caught"], b["before"]["caught"], b["median_edit_share"]) == (1, 0, 0, None)
    assert (b["median_risk_change"], b["share_risk_rose"], b["share_risk_fell"]) == (0, 0.0, 0.0)
    assert fp_measure.polish_flag_rates([], human, 60) is None


def test_scorecard_marks_rules_that_add_no_points() -> None:
    result = {
        "threshold": 60, "corpus_documents": 1, "missing_cache": [],
        "overall": fp_measure.slice_stats(risk_rows([0], register="chat"), 60),
        "by_register": {}, "by_author": {}, "register_curves": {}, "policy_caps": {"cap": 0.01, "by_register": {}},
        "top_rules_on_human_text": [], "machine_documents": 1, "human_dev_documents": 1,
        "catch_rate": None,
        "rule_scorecard": [
            {"rule": "source_risk.bare_url", "human_share": 0.1, "machine_share": 0.05, "ratio": 0.5},
            {"rule": "clarity.wordiness", "human_share": 0.2, "machine_share": 0.2, "ratio": 1.0},
            {"rule": "family9.humanizer_spacing", "human_share": 0.0, "machine_share": 0.1, "ratio": None},
        ],
    }
    page = fp_measure.render_results_md(result)
    assert "| `source_risk.bare_url` (no points) | 10.0% | 5.0% | 0.50 |" in page
    assert "| `clarity.wordiness` (no points) |" in page
    assert "| `family9.humanizer_spacing` | 0.0% | 10.0% | only on machine |" in page


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
        assert entry["register"] in corpus.MIN_WORDS
        machine = entry["kind"] in corpus.MACHINE_KINDS
        attacked = entry["kind"] in corpus.ATTACKED_KINDS
        polished = entry["kind"] in corpus.POLISHED_KINDS
        assert entry["label"] == corpus.entry_label(entry["kind"])
        if machine:
            assert entry["author"] == "machine"
            assert entry["model"]
            assert entry["split"] == corpus.digest_split(entry["sha256"])
        elif attacked:
            # An attacked document keeps the split of the generation it came from.
            assert entry["author"] == "machine"
            assert entry["model"] and entry["attack"] != "none"
            assert entry["split"] in ("dev", "test")
        elif polished:
            # Human text a model edited: the model is named, the split is the
            # original's, and the pointer names the original.
            assert entry["author"] == "polished"
            assert entry["model"] and entry["split"] == "test"
        else:
            # Every document comes from a public source.
            assert entry["author"] in ("other", "public-domain")
            assert "model" not in entry and "split" not in entry
        if not attacked:
            assert "attack" not in entry
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        prefix = corpus.ID_PREFIX[entry["kind"]]
        assert re.fullmatch(rf"{prefix}-[0-9a-f]{{12}}", entry["id"])
        if not polished:
            # A polished id also hashes its original and model; see save_pool.
            assert entry["id"].split("-", 1)[1] == entry["sha256"][:12]
        assert entry["words"] >= 50
    assert "private_pools" not in manifest
    # Every attacked document points at a RAID generation still in the
    # manifest, with the same split; a rebuilt RAID pool must not orphan them.
    raid = {str(e["source"]["id"]): e for e in entries if e["kind"] == "raid-generation"}
    for entry in entries:
        if entry["kind"] in corpus.ATTACKED_KINDS:
            original = raid.get(entry["source"]["adv_source_id"])
            assert original is not None, entry["id"]
            assert original["split"] == entry["split"], entry["id"]
    by_id = {e["id"]: e for e in entries}
    for entry in entries:
        if entry["kind"] in corpus.POLISHED_KINDS:
            original = by_id.get(entry["source"]["original_id"])
            assert original is not None and original["label"] == "human", entry["id"]


def test_manifest_is_anonymous() -> None:
    """Hash-only: no text, no usernames, and every pointer is to a public
    source anyone can fetch (a Gutenberg id, an archive identifier, a
    Wikipedia revision id, a Stack Exchange answer id, a dataset row)."""
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]
    public_keys = {
        "id", "kind", "label", "register", "author", "date", "words",
        "sha256", "extraction", "source", "model", "split", "attack",
    }
    source_keys = {
        "public-domain": {"work", "chunk", "chunk_words"},
        "gutenberg-work": {"work", "gutenberg_id", "url", "chunk", "chunk_words"},
        "persuade-essay": {"dataset", "id"},
        "news-page": {"url", "ia_identifier", "chunk"},
        "hf-news": {"dataset", "id", "date", "file_name", "chunk"},
        "cc-news": {"dataset", "row", "url", "domain"},
        "pep-chunk": {"repo", "commit", "path", "chunk"},
        "wikipedia-revision": {"site", "title", "revid", "url"},
        "stackexchange-answer": {"site", "answer_id", "url"},
        "raid-generation": {"dataset", "file", "id"},
        "raid-attack": {"dataset", "file", "id", "adv_source_id"},
        "wildchat-turn": {"dataset", "conversation_hash"},
        "generated": {"prompt_id", "requested_model"},
        "polished": {"original_id", "requested_model"},
    }
    assert set(source_keys) == set(corpus.PUBLIC_SOURCE_KINDS)
    for entry in entries:
        assert set(entry) <= public_keys
        assert entry["kind"] in source_keys, entry["id"]
        # Every kind publishes its pointer, and only scalar values.
        assert entry["source"], f"{entry['id']} has no public source"
        assert set(entry["source"]) <= source_keys[entry["kind"]]
        assert all(isinstance(v, (str, int)) for v in entry["source"].values())


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
    assert payload["schema"] == "humanizer-fp-measure.v3"
    assert "by_register" in payload and "overall" in payload
    assert "register_curves" in payload and "policy_caps" in payload
    assert "threshold_sweep_fpr" not in payload


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


def test_save_pool_keeps_each_models_polished_reply(tmp_path, monkeypatch) -> None:
    """Two models may return the same edit; each still counts for its model."""
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(corpus, "CACHE_DIR", tmp_path / "cache")
    text = "the same corrected words " * 30
    fields = {"register": "essay", "author": "polished", "date": "2026-11", "extraction": "x", "split": "test"}
    pairs = [
        ({**fields, "model": "openrouter:a"}, text, {"original_id": "essay-1", "requested_model": "a"}),
        ({**fields, "model": "openrouter:b"}, text, {"original_id": "essay-1", "requested_model": "b"}),
        ({**fields, "model": "openrouter:b"}, text, {"original_id": "essay-1", "requested_model": "b"}),  # repeat
    ]
    entries = corpus.save_pool("polished", pairs)
    assert [e["model"] for e in entries] == ["openrouter:a", "openrouter:b"]
    assert len({e["id"] for e in entries}) == 2 and all(e["sha256"] == corpus.sha256_text(text) for e in entries)
    assert all(e["label"] == "polished" and e["split"] == "test" for e in entries)


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


def test_raid_attack_pairs_keep_one_attacked_row_per_source_and_attack() -> None:
    sources = {
        "s1": {"register": "news", "model": "raid:gpt4", "split": "test", "date": "2023"},
        "s2": {"register": "chat", "model": "raid:chatgpt", "split": "dev", "date": "2023"},
    }
    long_text = "word " * 250
    rows = [
        {"id": "a", "adv_source_id": "s1", "attack": "paraphrase", "generation": long_text},
        {"id": "b", "adv_source_id": "s1", "attack": "paraphrase", "generation": long_text},  # repeat
        {"id": "c", "adv_source_id": "s1", "attack": "homoglyph", "generation": long_text},
        {"id": "d", "adv_source_id": "s1", "attack": "none", "generation": long_text},  # not attacked
        {"id": "e", "adv_source_id": "other", "attack": "synonym", "generation": long_text},  # not ours
        {"id": "f", "adv_source_id": "s2", "attack": "synonym", "generation": "too short"},
        {"id": "g", "adv_source_id": "s2", "attack": "zero_width_space", "generation": "word " * 60},
    ]
    pairs, dropped = corpus.raid_attack_pairs(rows, sources)
    assert [source["id"] for _meta, _text, source in pairs] == ["a", "c", "g"]
    meta, _text, source = pairs[0]
    assert meta["attack"] == "paraphrase" and meta["split"] == "test" and meta["model"] == "raid:gpt4"
    assert source == {"dataset": "liamdugan/raid", "file": "train.csv", "id": "a", "adv_source_id": "s1"}
    assert pairs[2][0]["register"] == "chat" and pairs[2][0]["split"] == "dev"
    assert dropped == {"duplicate-attack": 1, "under-min-words": 1}


def test_attack_sample_draws_test_generations_across_the_id_range() -> None:
    digests = [corpus.sha256_text(str(index)) for index in range(200)]
    entries = [
        {"id": f"raid-{digest[:12]}", "kind": "raid-generation", "split": corpus.digest_split(digest)}
        for digest in digests
    ]
    entries.append({"id": "wildchat-000000000000", "kind": "wildchat-turn", "split": "test"})
    sample = corpus.attack_sample(entries, 10)
    assert len(sample) == 10
    assert all(entry["kind"] == "raid-generation" and entry["split"] == "test" for entry in sample)
    # Not just the lowest ids: the id's first character also sets the split.
    assert sample != sorted(sample, key=lambda entry: entry["id"])
    assert corpus.attack_sample(entries, 10) == sample
    assert len(corpus.attack_sample(entries, 0)) == sum(
        1 for entry in entries if entry["kind"] == "raid-generation" and entry["split"] == "test"
    )


def test_persuade_pairs_dedupes_spans_and_fills_prompts() -> None:
    long_text = "word " * 200
    rows = [
        # The CSV repeats an essay once per annotated span; demographic
        # columns are present in the file but never copied.
        {"essay_id": "E1", "prompt_name": "Venus", "full_text": long_text, "gender": "x"},
        {"essay_id": "E1", "prompt_name": "Venus", "full_text": long_text, "gender": "x"},
        {"essay_id": "E2", "prompt_name": "Venus", "full_text": "too short"},
        {"essay_id": "E3", "prompt_name": "Venus", "full_text": "line\r\n" + long_text},
        {"essay_id": "E4", "prompt_name": "Mars", "full_text": long_text + "x"},
    ]
    pairs, dropped = corpus.persuade_pairs(rows, per_prompt=3)
    ids = [source["id"] for _meta, _text, source in pairs]
    # Prompts in name order, essays in digest order. E2 is below the essay
    # minimum, so both prompts fall short of a quota of three.
    assert ids == ["E4", "E3", "E1"]
    assert dropped == {"out-of-length-band": 1, "prompt-below-quota": 2}
    meta, text, source = pairs[1]
    assert meta == {"register": "essay", "author": "other", "date": "2010-2020", "extraction": "persuade.v1"}
    assert source == {"dataset": "scrosseye/persuade_corpus_2.0", "id": "E3"}
    assert "\r" not in text and text.startswith("line\nword")


def test_persuade_pairs_order_is_by_id_digest() -> None:
    text = "word " * 200
    rows = [{"essay_id": f"E{n}", "prompt_name": "P", "full_text": text + str(n)} for n in range(6)]
    first, _ = corpus.persuade_pairs(rows, per_prompt=3)
    again, _ = corpus.persuade_pairs(list(reversed(rows)), per_prompt=3)
    expected = sorted((f"E{n}" for n in range(6)), key=corpus.sha256_text)[:3]
    assert [s["id"] for _m, _t, s in first] == expected
    assert [s["id"] for _m, _t, s in again] == expected


def test_cc_news_pairs_gates_dates_length_boilerplate_and_repeats() -> None:
    body = "The council met on Tuesday and the vote passed. " * 30

    def row(**overrides):
        base = {"date": "2018-03-04 00:00:00", "url": "https://example.com/a", "domain": "example.com", "text": body}
        return {**base, **overrides}

    rows = list(
        enumerate(
            [
                row(),
                row(url="https://example.com/a"),  # same URL again
                row(url="https://example.com/b", date="2022-11-01"),  # on the cutoff
                row(url="https://example.com/c", date=""),
                row(url="https://example.com/c2", date="1970-01-01"),  # before the crawl
                row(url="https://example.com/c3", date="2017-13-45"),
                row(url="ftp://example.com/d"),
                row(url="https://example.com/e", text="too short"),
                row(url="https://example.com/f", text=body + "Sign up for our newsletter."),
                row(url="https://example.com/f2", text=body + "Write to [email\xa0protected] today."),
                row(url="https://example.com/f3", text=body + "\n\nAdvertisement\n\nMore text."),
                row(url="https://example.com/g", text="le la les des une " * 60),
                row(url="https://example.com/h", text="She baked cookies for the newsletter team.\r\n\r\n\r\n" + body),
                row(url="https://wire.example.org/a", domain="wire.example.org"),  # same text, other URL
                row(url="https://other.example.org/j", domain="other.example.org", date="2022-10-31", text=body + "j"),
            ]
        )
    )
    rows.append(("7", row(url="https://example.com/k")))  # no integer row index
    pairs, dropped = corpus.cc_news_pairs(rows)
    assert [source["url"][-1] for _meta, _text, source in pairs] == ["a", "h", "j"]
    assert dropped == {
        "duplicate-url": 1,
        "undated-or-out-of-range": 4,
        "no-pointer": 1,
        "word-band": 1,
        "boilerplate": 3,
        "not-english": 1,
        "duplicate-text": 1,
        "no-row-index": 1,
    }
    meta, text, source = pairs[1]
    assert meta == {"register": "news", "author": "other", "date": "2018-03-04", "extraction": "ccnews.v1"}
    assert source == {"dataset": "vblagoje/cc_news", "row": 12, "url": "https://example.com/h", "domain": "example.com"}
    assert "\r" not in text and "\n\n\n" not in text
    assert pairs[2][0]["date"] == "2022-10-31"


def test_cc_news_boilerplate_spares_articles_about_the_words() -> None:
    match = corpus.CC_NEWS_BOILERPLATE_RE.search
    for clean in ("Cookies and newsletters were on the agenda.", "Readers said they would subscribe later.",
                  "The advertisement ran for a week.", "She asked us to read more slowly."):
        assert not match(clean), clean
    for dirty in ("Copyright \u00a9 2018", "Click here to see more.", "[email protected]", "[email&#160;protected]",
                  "Body.\nRead more:\nNext", "Body.\nRelated\nNext", "Share on Facebook", "Continue reading the story"):
        assert match(dirty), dirty


def test_cc_news_select_is_independent_of_arrival_order_and_missing_windows() -> None:
    def pair(n, domain):
        return ({"date": "2018-01-01"}, f"text {n}", {"row": n, "url": f"https://{domain}/{n}", "domain": domain})

    pairs = [pair(n, f"site{n % 4}.example") for n in range(40)]
    chosen, dropped = corpus.cc_news_select(pairs, target=6, per_domain=3)
    again, _ = corpus.cc_news_select(list(reversed(pairs)), target=6, per_domain=3)
    assert chosen == again and len(chosen) == 6
    assert dropped == {"outlet-quota": 28, "over-target": 6}
    assert [p[2]["row"] for p in chosen] == sorted(p[2]["row"] for p in chosen)
    assert max(Counter(p[2]["domain"] for p in chosen).values()) <= 3
    # Losing one outlet's window only frees its own slots.
    lost = {p[2]["url"] for p in chosen if p[2]["domain"] == "site0.example"}
    survivors, _ = corpus.cc_news_select([p for p in pairs if p[2]["domain"] != "site0.example"], target=6, per_domain=3)
    assert {p[2]["url"] for p in chosen} - lost <= {p[2]["url"] for p in survivors}
    small, small_drops = corpus.cc_news_select(pairs[:2], target=6, per_domain=3)
    assert len(small) == 2 and small_drops == {}


def test_cc_news_date_bounds() -> None:
    assert corpus.cc_news_date("2017-12-01 00:00:00") == "2017-12-01"
    assert corpus.cc_news_date("2017-12-01T00:00:00Z") == "2017-12-01"
    for bad in (None, "", "12/01/2017", "0000-00-00", "2015-12-31", "2022-11-01", "2017-02-30"):
        assert corpus.cc_news_date(bad) is None, bad


def test_cc_news_build_keeps_the_pool_when_nothing_arrives(monkeypatch) -> None:
    saved = []
    monkeypatch.setattr(corpus, "save_pool", lambda kind, pairs: saved.append(kind) or [])

    def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(corpus, "fetch_text_with_retry", offline)
    import argparse

    assert corpus.build_cc_news(argparse.Namespace(target=10, per_domain=3, sleep=0)) == 1
    assert saved == []


def test_cc_news_build_reads_every_window_then_selects(monkeypatch, capsys) -> None:
    body = "The council met on Tuesday and the vote passed. " * 30
    rows = [
        (n, {"date": "2018-01-01", "url": f"https://site{n}.example/a", "domain": f"site{n}.example", "text": body + str(n)})
        for n in range(10)
    ]

    def fake_rows(offsets, sleep, dropped):
        dropped["offset-fetch-failed"] += 1
        return iter(rows)

    monkeypatch.setattr(corpus, "cc_news_rows", fake_rows)
    saved = []
    monkeypatch.setattr(corpus, "save_pool", lambda kind, pairs: saved.extend(pairs) or pairs)
    import argparse

    assert corpus.build_cc_news(argparse.Namespace(target=4, per_domain=3, sleep=0)) == 0
    expected, _ = corpus.cc_news_select(corpus.cc_news_pairs(rows)[0], 4, 3)
    assert saved == expected and len(saved) == 4
    out = capsys.readouterr().out
    assert "1 windows failed to download" in out and "'over-target': 6" in out


def test_cc_news_rows_reads_row_index_and_skips_failed_windows(monkeypatch) -> None:
    urls = []

    def fake_fetch(url, sleep, *args, **kwargs):
        urls.append(url)
        if "offset=10" in url:
            raise OSError("502")
        return json.dumps({"rows": [{"row_idx": 3, "row": {"url": "u"}}, {"row": None}]})

    monkeypatch.setattr(corpus, "fetch_text_with_retry", fake_fetch)
    dropped = Counter()
    assert list(corpus.cc_news_rows((0, 10), 0, dropped)) == [(3, {"url": "u"}), (None, {})]
    assert dropped == {"offset-fetch-failed": 1}
    assert "config=plain_text" in urls[0] and "length=10" in urls[0] and "offset=0" in urls[0]


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


def test_polish_sample_takes_human_test_documents_per_kind() -> None:
    entries = []
    for index in range(40):
        digest = corpus.sha256_text(f"doc{index}")
        kind = "persuade-essay" if index % 2 else "stackexchange-answer"
        entries.append({"id": f"x-{digest[:12]}", "kind": kind, "label": "human", "sha256": digest})
    entries.append({"id": "gen-000000000000", "kind": "generated", "label": "machine", "sha256": "f" * 64, "split": "test"})
    # A non-human entry of a sampled kind is never picked.
    entries.append({"id": "pol-000000000000", "kind": "persuade-essay", "label": "polished", "sha256": "e" * 64, "split": "test"})
    sample = generate.polish_sample(entries, {"persuade-essay": 3, "stackexchange-answer": 2})
    assert [e["kind"] for e in sample] == ["persuade-essay"] * 3 + ["stackexchange-answer"] * 2
    assert all(corpus.digest_split(e["sha256"]) == "test" for e in sample)
    assert generate.polish_sample(entries, {"persuade-essay": 3, "stackexchange-answer": 2}) == sample


def test_polished_pairs_point_at_the_original() -> None:
    sample = [{"id": "essay-abc", "kind": "persuade-essay", "sha256": "f" * 64}]
    pairs = [(
        {"register": "essay", "author": "machine", "model": "openrouter:m", "date": "2026-11", "extraction": "generated.v1"},
        "Fixed text.",
        {"prompt_id": "essay-abc", "requested_model": "m"},
    )]
    (public, _text, source), = generate.polished_pairs(pairs, sample)
    assert public["author"] == "polished" and public["split"] == "test"
    assert public["extraction"] == generate.POLISH_EXTRACTION and public["model"] == "openrouter:m"
    assert source == {"original_id": "essay-abc", "requested_model": "m"}
    assert corpus.entry_label("polished") == "polished"


def test_wrapped_polish_replies_are_caught() -> None:
    original = "I think school should start later.\nStudents are tired."
    assert not generate.wrapped_reply(original, "I think school should start later.\nStudents are tired.")
    assert generate.wrapped_reply(original, "Here is the corrected text:\n\nI think school should start later.")
    assert generate.wrapped_reply(original, "```\nI think school should start later.\n```")
    # A colon line the person wrote is theirs, not a wrapper.
    listing = "My reasons are these:\nfirst, sleep."
    assert not generate.wrapped_reply(listing, "My reasons are these:\nFirst, sleep.")
    assert not generate.wrapped_reply("```\ncode\n```", "```\ncode\n```")
    # A first line the edit corrected is still the person's.
    tip = "you can do it like this:\nrun the script twice."
    assert not generate.wrapped_reply(tip, "You can do it like this:\nRun the script twice.")
    reasons = "Their are three reason's:\nsleep, food, and time."
    assert not generate.wrapped_reply(reasons, "There are three reasons:\nSleep, food, and time.")
    # A lead-in without a colon, and a closing note, are wrappers.
    assert generate.wrapped_reply(original, "Sure! Here is the corrected text.\nI think school should start later.\nStudents are tired.")
    assert generate.wrapped_reply(original, "I think school should start later.\nStudents are tired.\nChanges made: none needed.")
    # A one-line document has nothing to compare a wrapper with.
    assert not generate.wrapped_reply("Short.", "Short.")


def test_polish_task_needs_openrouter() -> None:
    with pytest.raises(SystemExit):
        generate.main(["--task", "polish", "--dry-run"])


def test_estimate_uses_each_prompt_reply_length() -> None:
    prices = {"m": (0.0, 1.0)}
    prompts = [{"prompt": "", "reply_tokens": 100}, {"prompt": ""}]
    estimate, ceiling = generate.estimate_cost(prompts, ["m"], 500, prices)
    assert estimate == 100 + 500  # 100 for the first, min(1000, 500) for the second
    assert ceiling == 1000


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


class _FakeHTTP:
    """Stands in for urllib.request.urlopen: replays scripted replies."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def __call__(self, request, timeout=None):
        import io
        import urllib.error

        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, int):
            body = json.dumps({"error": {"message": f"status {step}"}}).encode()
            raise urllib.error.HTTPError(
                request.full_url, step, "err", None, io.BytesIO(body)
            )
        reply = io.BytesIO(json.dumps(step).encode())
        return reply


def _completion(
    finish, text="word " * 200, served="anthropic/claude-opus-5.5-20261101", native=None
):
    return {
        "model": served,
        "choices": [
            {
                "finish_reason": finish,
                "native_finish_reason": native,
                "message": {"content": text},
            }
        ],
    }


def test_openrouter_request_shape_and_labels(monkeypatch) -> None:
    http = _FakeHTTP(
        [
            _completion("stop"),
            _completion("length"),
            _completion("content_filter"),
            _completion("stop", native="refusal"),
        ]
    )
    monkeypatch.setattr(generate.urllib.request, "urlopen", http)
    client = generate.OpenRouterClient("sk-test", sleep=lambda _s: None)
    prompts = [{"id": "wiki-01", "register": "wiki", "prompt": "Write about X."}]
    models = ["anthropic/claude-opus-5.5", "m2", "m3", "m4"]
    pairs, counts = generate.generate_pairs(
        client, generate.OpenRouterErrors, prompts, models, 4096, None, "openrouter"
    )
    assert counts == {"kept": 1, "truncated": 1, "refused": 2}
    assert [meta["model"] for meta, _t, _s in pairs] == [
        "openrouter:anthropic/claude-opus-5.5-20261101"
    ]
    assert pairs[0][1] == ("word " * 200).strip()
    assert pairs[0][2] == {
        "prompt_id": "wiki-01",
        "requested_model": "anthropic/claude-opus-5.5",
    }
    request = http.requests[0]
    assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer sk-test"
    body = json.loads(request.data)
    assert body == {
        "model": "anthropic/claude-opus-5.5",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": "Write about X."}],
    }  # no models, fallbacks, or route: labels must stay exact


def test_openrouter_errors_stop_or_retry(monkeypatch) -> None:
    prompts = [{"id": "wiki-01", "register": "wiki", "prompt": "x"}]
    for status, error in ((401, "AuthenticationError"), (402, "PermissionDeniedError")):
        http = _FakeHTTP([status])
        monkeypatch.setattr(generate.urllib.request, "urlopen", http)
        client = generate.OpenRouterClient("sk-test", sleep=lambda _s: None)
        with pytest.raises(getattr(generate.OpenRouterErrors, error)):
            generate.generate_pairs(
                client,
                generate.OpenRouterErrors,
                prompts,
                ["m1"],
                100,
                None,
                "openrouter",
            )
        assert len(http.requests) == 1  # configuration errors are not retried
    sleeps = []
    http = _FakeHTTP([429] * 6 + [{"error": {"message": "provider down"}}])
    monkeypatch.setattr(generate.urllib.request, "urlopen", http)
    client = generate.OpenRouterClient("sk-test", sleep=sleeps.append)
    pairs, counts = generate.generate_pairs(
        client,
        generate.OpenRouterErrors,
        prompts,
        ["m1", "m2"],
        100,
        None,
        "openrouter",
    )
    assert pairs == [] and counts == {"api-error": 2}
    assert sleeps == [1, 2, 4, 8, 16]  # five retries, then the 429 is counted
    assert len(http.requests) == 7  # an error object in a 200 body is not retried


def _openrouter_dry_run_fixture(monkeypatch, prices):
    prompts = [
        {"id": f"wiki-0{n}", "register": "wiki", "prompt": "p" * 80} for n in (1, 2)
    ]
    monkeypatch.setattr(generate, "load_prompts", lambda: prompts)
    monkeypatch.setattr(generate, "fetch_openrouter_prices", lambda: prices)

    def no_network(*_args, **_kwargs):
        raise AssertionError("dry run touched the network")

    monkeypatch.setattr(generate.urllib.request, "urlopen", no_network)


def test_openrouter_dry_run_prints_estimate_and_calls_nothing(
    monkeypatch, capsys
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _openrouter_dry_run_fixture(monkeypatch, {"m1": (0.001, 0.002)})
    assert (
        generate.main(["--provider", "openrouter", "--dry-run", "--models", "m1"]) == 0
    )
    out = capsys.readouterr().out
    # Per request: (80/4 + 20) * 0.001 + 1000 * 0.002 = 2.04; ceiling 0.04 + 4096 * 0.002 = 8.232.
    assert "2 prompts x 1 models = 2 requests" in out
    assert "estimated cost: $4.08" in out
    assert "ceiling: $16.46 (every reply at max_tokens=4096)" in out


def test_openrouter_unpriced_model_fails_loud(monkeypatch, capsys) -> None:
    _openrouter_dry_run_fixture(monkeypatch, {"m1": (0.001, 0.002)})
    assert (
        generate.main(
            ["--provider", "openrouter", "--dry-run", "--models", "m1", "nope/x"]
        )
        == 2
    )
    assert "'nope/x'" in capsys.readouterr().err


def test_openrouter_needs_a_key_and_rejects_effort(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _openrouter_dry_run_fixture(monkeypatch, {})
    assert generate.main(["--provider", "openrouter", "--limit", "1"]) == 3
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exit_info:
        generate.main(["--provider", "openrouter", "--effort", "low", "--dry-run"])
    assert exit_info.value.code == 2
    assert (
        "--effort is not supported with --provider openrouter"
        in capsys.readouterr().err
    )



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



def test_generate_trial_run_and_empty_run_never_touch_the_pool(
    tmp_path, monkeypatch, capsys
) -> None:
    import types

    monkeypatch.setattr(generate.corpus, "CACHE_DIR", tmp_path)
    saved = []
    monkeypatch.setattr(
        generate.corpus, "save_pool", lambda kind, pairs: saved.append(pairs) or []
    )
    fake = types.SimpleNamespace(
        Anthropic=lambda **_kw: _FakeClient(
            [("end_turn", "word " * 200)] * 10 + [("refusal", "")] * 10
        ),
        **{
            name: getattr(_FakeErrors, name)
            for name in dir(_FakeErrors)
            if not name.startswith("_")
        },
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    assert generate.main(["--limit", "1", "--models", "m1"]) == 0
    assert saved == [] and "trial run" in capsys.readouterr().out
    fake.Anthropic = lambda **_kw: _FakeClient([("refusal", "")] * 200)
    assert generate.main(["--models", "m1"]) == 1
    assert saved == []


def test_generate_keeps_paid_results_across_a_fatal_error(
    tmp_path, monkeypatch, capsys
) -> None:
    import types

    # A budget cap (403) mid-run must not throw away the replies already paid for.
    monkeypatch.setattr(generate.corpus, "CACHE_DIR", tmp_path)
    prompts = [
        {"id": f"wiki-0{n}", "register": "wiki", "prompt": "x"} for n in (1, 2, 3)
    ]
    monkeypatch.setattr(generate, "load_prompts", lambda: prompts)
    saved = []
    monkeypatch.setattr(
        generate.corpus, "save_pool", lambda kind, pairs: saved.append(pairs) or pairs
    )
    long_text = "word " * 200
    first = _FakeClient(
        [
            ("end_turn", long_text + "one"),
            ("refusal", ""),
            _FakeErrors.RateLimitError("slow down"),
            _FakeErrors.PermissionDeniedError("budget limit exceeded"),
        ]
    )
    fake = types.SimpleNamespace(
        Anthropic=lambda **_kw: first,
        **{
            name: getattr(_FakeErrors, name)
            for name in dir(_FakeErrors)
            if not name.startswith("_")
        },
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    assert generate.main(["--models", "m1", "m2"]) == 1
    err = capsys.readouterr().err
    assert saved == [] and "2 results kept" in err and "re-run" in err
    # The re-run asks only for what is still missing: the api-error and the
    # two never-sent requests, not the kept reply or the refusal.
    second = _FakeClient([("end_turn", long_text + "two")] * 4)
    fake.Anthropic = lambda **_kw: second
    assert generate.main(["--models", "m1", "m2"]) == 0
    asked = [(r["messages"][0]["content"], r["model"]) for r in second.requests]
    assert len(asked) == 4 and ("x", "m1") in asked
    assert len(saved) == 1 and len(saved[0]) == 5  # 1 from the first run + 4 new
    assert saved[0][0][2] == {"prompt_id": "wiki-01", "requested_model": "m1"}
    assert list(tmp_path.glob("*.checkpoint.jsonl")) == []  # cleared after the save


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




# ------------------------------------------------ wikipedia / stack exchange


def test_html_strip_keeps_prose_and_drops_code_and_quotes() -> None:
    markup = (
        "<p>Use <em>fresh</em> yeast &amp; warm water.</p>"
        "<pre><code>knead(dough)</code></pre>"
        "<blockquote><p>Someone else wrote this.</p></blockquote>"
        "<ul><li>Rest it.</li><li>Bake it.</li></ul>"
    )
    text = corpus.html_strip(markup)
    assert text == "Use fresh yeast & warm water.\n\nRest it.\n\nBake it."
    assert "knead" not in text and "Someone else" not in text


def test_stackexchange_pairs_keeps_only_pre_cutoff_untouched_prose() -> None:
    prose = "word " * 80
    items = [
        {"answer_id": 1, "creation_date": corpus.CUTOFF_EPOCH - 10, "body": f"<p>{prose}</p>"},
        {"answer_id": 2, "creation_date": corpus.CUTOFF_EPOCH + 10, "body": f"<p>{prose}</p>"},
        {"answer_id": 3, "creation_date": 1500000000, "last_edit_date": corpus.CUTOFF_EPOCH + 5, "body": f"<p>{prose}</p>"},
        {"answer_id": 4, "creation_date": 1500000000, "last_edit_date": 1600000000, "body": f"<p>{prose}</p>"},
        {"answer_id": 5, "creation_date": 1500000000, "body": "<p>too short</p>"},
    ]
    pairs, dropped = corpus.stackexchange_pairs(items, "cooking")
    assert [source["answer_id"] for _f, _t, source in pairs] == [1, 4]
    assert dropped == {"post-cutoff": 1, "edited-post-cutoff": 1, "word-band": 1}
    fields, text, source = pairs[1]
    assert fields == {"register": "chat", "author": "other", "date": "2017-07", "extraction": corpus.HTML_STRIP_VERSION}
    assert source == {"site": "cooking", "answer_id": 4, "url": "https://cooking.stackexchange.com/a/4"}
    assert text == prose.strip()


def test_wikipedia_pair_strips_wikitext_and_bounds_length() -> None:
    bold = "'" * 3
    body = bold + "Marvale" + bold + " is a [[town]] in [[Calder Bay|the bay]].<ref>cite</ref> " + "It has a harbor. " * 60
    rev = {"title": "Marvale", "revid": 123, "timestamp": "2021-06-01T00:00:00Z", "wikitext": body}
    fields, text, source = corpus.wikipedia_pair(rev)
    assert text.startswith("Marvale is a town in the bay.")
    assert "<ref>" not in text and "[[" not in text
    assert fields == {"register": "wiki", "author": "other", "date": "2021-06", "extraction": corpus.WIKITEXT_STRIP_VERSION}
    assert source == {"site": "en.wikipedia.org", "title": "Marvale", "revid": 123, "url": "https://en.wikipedia.org/w/index.php?oldid=123"}
    assert corpus.wikipedia_pair({**rev, "wikitext": "Too short."}) is None
    assert corpus.wikipedia_pair({**rev, "wikitext": "word " * (corpus.WIKIPEDIA_MAX_WORDS + 1)}) is None


def test_save_manifest_drops_the_old_private_totals(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "MANIFEST_PATH", tmp_path / "manifest.json")
    pd = {"id": "pd-ba9876543210", "kind": "public-domain", "register": "essay", "author": "public-domain",
          "sha256": "ba9876543210" + "0" * 52, "words": 600}
    corpus.save_manifest({"schema": corpus.MANIFEST_SCHEMA, "cutoff": corpus.CUTOFF, "entries": [pd],
                          "private_pools": {"forum-post": {"entries": 5, "registers": {"chat": 5}}}})
    public = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "private_pools" not in public
    assert [e["id"] for e in public["entries"]] == ["pd-ba9876543210"]


def test_fetch_rebuilds_wikipedia_and_stackexchange_entries_by_id(tmp_path, monkeypatch) -> None:
    import argparse

    wikitext = "Prose from the revision. " * 20
    html = "<p>" + "Prose from the answer. " * 20 + "</p>"
    wp_text = corpus.wikitext_strip(wikitext)
    se_text = corpus.html_strip(html)
    entries = [
        {"id": f"wp-{corpus.sha256_text(wp_text)[:12]}", "kind": "wikipedia-revision", "register": "wiki",
         "author": "other", "words": 100, "sha256": corpus.sha256_text(wp_text),
         "extraction": corpus.WIKITEXT_STRIP_VERSION,
         "source": {"site": "en.wikipedia.org", "title": "X", "revid": 77, "url": "u"}},
        {"id": f"se-{corpus.sha256_text(se_text)[:12]}", "kind": "stackexchange-answer", "register": "chat",
         "author": "other", "words": 100, "sha256": corpus.sha256_text(se_text),
         "extraction": corpus.HTML_STRIP_VERSION,
         "source": {"site": "cooking", "answer_id": 9, "url": "u"}},
    ]
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(corpus, "CACHE_DIR", tmp_path / "cache")
    corpus._write_json(tmp_path / "manifest.json", {"schema": corpus.MANIFEST_SCHEMA, "cutoff": corpus.CUTOFF, "entries": entries})
    calls = []

    def fake_api_get(url, params, sleep):
        calls.append((url, params))
        assert params["revids"] == "77"
        return {"query": {"pages": {"1": {"revisions": [{"revid": 77, "slots": {"main": {"*": wikitext}}}]}}}}

    def fake_se_get(path, params, sleep):
        calls.append((path, params))
        assert path == "answers/9" and params["site"] == "cooking"
        return {"items": [{"answer_id": 9, "body": html}]}

    monkeypatch.setattr(corpus, "api_get", fake_api_get)
    monkeypatch.setattr(corpus, "stackexchange_get", fake_se_get)
    assert corpus.fetch(argparse.Namespace(sleep=0)) == 0
    assert len(calls) == 2
    assert corpus.verify(argparse.Namespace()) == 0


def test_fetch_rebuilds_cc_news_entries_by_row(tmp_path, monkeypatch) -> None:
    import argparse

    raw = "First paragraph of the story.  \r\n\r\n\r\n" + "Second paragraph. " * 40
    text = corpus.cc_news_clean(raw)

    def entry(row, url):
        return {"id": f"ccnews-{corpus.sha256_text(text + url)[:12]}", "kind": "cc-news", "register": "news",
                "author": "other", "words": 100, "sha256": corpus.sha256_text(text), "date": "2018-01-02",
                "extraction": corpus.CC_NEWS_EXTRACTION,
                "source": {"dataset": corpus.CC_NEWS_DATASET, "row": row, "url": url, "domain": "example.com"}}

    kept, moved = entry(41, "https://example.com/a"), entry(42, "https://example.com/b")
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(corpus, "CACHE_DIR", tmp_path / "cache")
    corpus._write_json(tmp_path / "manifest.json", {"schema": corpus.MANIFEST_SCHEMA, "cutoff": corpus.CUTOFF, "entries": [kept, moved]})
    urls = []

    def fake_fetch(url, sleep, *args, **kwargs):
        urls.append(url)
        # Row 42 now holds another article, so its entry must stay uncached.
        row_url = "https://example.com/a" if "offset=41" in url else "https://example.com/other"
        return json.dumps({"rows": [{"row_idx": 0, "row": {"url": row_url, "text": raw}}]})

    monkeypatch.setattr(corpus, "fetch_text_with_retry", fake_fetch)
    assert corpus.fetch(argparse.Namespace(sleep=0)) == 1
    assert all("config=plain_text" in url and "length=1" in url for url in urls) and len(urls) == 2
    assert corpus.cache_path(kept["id"]).exists() and not corpus.cache_path(moved["id"]).exists()
    assert corpus.read_cache(kept["id"]) == text


def test_period_bands_from_manifest_dates() -> None:
    assert fp_measure.period_of("pre-1923") == "pre-1930"
    assert fp_measure.period_of("1900-1922") == "pre-1930"
    assert fp_measure.period_of("1899") == "pre-1930"
    assert fp_measure.period_of("2001") == "1930-2017"
    assert fp_measure.period_of("2021-06") == "2018-2022"
    assert fp_measure.period_of("") == "undated"


def test_measure_reports_false_positives_by_period(tmp_path, monkeypatch) -> None:
    old = {**_entry("pd-000000000001", "human", register="essay"), "date": "1918"}
    new = {**_entry("wp-000000000002", "human", register="wiki"), "date": "2021-03"}
    newer = {**_entry("wp-000000000003", "human", register="wiki"), "date": "2022-10"}
    result = _measure_fixture(tmp_path, monkeypatch, [(old, PLAIN), (new, SLOP), (newer, PLAIN)])
    periods = result["by_period"]
    assert list(periods) == ["pre-1930", "2018-2022"]
    assert periods["pre-1930"]["n"] == 1 and periods["pre-1930"]["flagged"] == 0
    assert periods["2018-2022"]["n"] == 2 and periods["2018-2022"]["flagged"] == 1
    page = fp_measure.render_results_md(result)
    assert "| period: 2018-2022 | 2 | 1 | 50.0% |" in page
    assert "period:pre-1930" in fp_measure.render_text(result)


def test_register_defaults_check_each_register_at_its_own_threshold() -> None:
    human = risk_rows([10, 25], register="chat", period="2018-2022") + risk_rows(
        [25, 25], register="essay", period="pre-1930"
    )
    machine = (
        risk_rows([25, 70], register="chat", model="m1")
        + risk_rows([25], register="essay", model="m1")
        + risk_rows([5], register="docs", model="m2")
    )
    polished = risk_rows([22], register="chat")
    defaults = fp_measure.register_default_rates(human, machine, polished, 60)
    chat, essay, docs = (defaults["by_register"][reg] for reg in ("chat", "essay", "docs"))
    assert chat["threshold"] == 20 and essay["threshold"] == 60 and docs["threshold"] == 20
    assert chat["human"]["flagged"] == 1 and chat["human"]["flagged_at_fixed"] == 0
    assert chat["machine"]["flagged"] == 2 and chat["machine"]["flagged_at_fixed"] == 1
    assert chat["polished"]["flagged"] == 1 and chat["polished"]["flagged_at_fixed"] == 0
    assert essay["human"]["flagged"] == 0 and essay["machine"]["flagged"] == 0
    assert docs["human"]["n"] == 0 and docs["machine"]["flagged"] == 0
    assert defaults["overall"]["human"]["flagged"] == 1 and defaults["overall"]["machine"]["flagged"] == 2
    assert defaults["by_period"]["2018-2022"]["flagged"] == 1 and defaults["by_period"]["pre-1930"]["flagged"] == 0
    assert defaults["by_model"]["m1"]["flagged"] == 2 and defaults["by_model"]["m2"]["flagged"] == 0
    blocked = risk_rows([0], blocked=True, register="essay", period="pre-1930")
    assert fp_measure.register_default_rates(blocked, [], [], 60)["overall"]["human"]["flagged"] == 1


def test_register_defaults_render_on_the_results_page(tmp_path, monkeypatch) -> None:
    result = _measure_fixture(tmp_path, monkeypatch, [
        (_entry("se-000000000001", "human", register="chat"), PLAIN),
        (_entry("raid-000000000002", "machine", register="chat", model="raid:gpt4"), SLOP),
    ])
    page = fp_measure.render_results_md(result)
    assert "## Rates at the register defaults" in page
    assert "| chat | 20 | 0 of 1 (0.0%) |" in page
    assert "| `raid:gpt4` | 1 of 1 (100.0%) |" in page
    assert "At the --register defaults" in fp_measure.render_text(result)
