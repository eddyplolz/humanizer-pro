#!/usr/bin/env python3
"""Corpus builder for error-rate measurement, public sources only.

Ground truth by provenance, not judgment: every human document predates the
public release of ChatGPT (2022-11-30; this corpus uses a 2022-11-01 cutoff
for margin), so any audit flag on it is a false positive by construction.
Machine documents carry the model that wrote them. Design adapted from
avoid-ai-writing's corpus/fp-measure (MIT).

The corpus is hash-only. `corpus/manifest.json` carries register, author
tier, date, word count, SHA-256 digest, and a public pointer per document
(a Gutenberg id, an Internet Archive identifier, a Wikipedia revision id, a
Stack Exchange answer id, a dataset row). No text is committed: it lives in
the gitignored `corpus/cache/`, and every pool can be rebuilt from its
pointers by anyone, so every published number can be checked; every
document comes from a public source.

Subcommands:
  build-pd            chunk the in-repo public-domain Strunk text
  build-essays        chunk public-domain Gutenberg essay works
  build-news          fetch public-domain newspaper OCR (Internet Archive)
  build-hf-news       grow the news pool from OpenCulture (HF rows API)
  build-wikipedia     wiki-register pool: random English Wikipedia articles at
                      their last pre-cutoff revision (CC BY-SA)
  build-stackexchange chat-register pool: pre-cutoff Stack Exchange answers
                      from hobby and language sites (CC BY-SA)
  build-peps          docs-register pool: PEPs at the last pre-cutoff commit
  build-raid          machine pool: RAID generations (non-adversarial, MIT)
  build-wildchat      machine pool: WildChat-1M first replies (ODC-BY)
                      (scripts/generate_machine.py can add current Claude
                      models; it needs an API key and is never run by default)
  fetch               repopulate the cache from the manifest's public pointers
                      (Strunk offline; Wikipedia and Stack Exchange by id;
                      other kinds name their build-* subcommand)
  verify              check every cached file against its manifest sha256
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html as html_lib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
CACHE_DIR = CORPUS_DIR / "cache"
MANIFEST_SCHEMA = "humanizer-corpus-manifest.v1"
CUTOFF = "2022-11-01"
CUTOFF_EPOCH = 1667260800  # 2022-11-01T00:00:00Z
MIN_WORDS = {"chat": 50, "wiki": 150, "essay": 150, "news": 200, "docs": 150}
WIKITEXT_STRIP_VERSION = "wikitext-strip.v2"
CHUNK_VERSION = "chunk.v2"
USER_AGENT = "humanizer-pro-corpus/1.0"
ID_PREFIX = {
    "public-domain": "pd",
    "news-page": "news",
    "gutenberg-work": "guten",
    "hf-news": "hfnews",
    "pep-chunk": "pep",
    "wikipedia-revision": "wp",
    "stackexchange-answer": "se",
    "raid-generation": "raid",
    "wildchat-turn": "wildchat",
    "generated": "gen",
}
# Every kind publishes its pointer in the manifest; the tuple is kept as the
# contract the anonymity test checks, kind by kind.
PUBLIC_SOURCE_KINDS = (
    "public-domain",
    "news-page",
    "gutenberg-work",
    "hf-news",
    "pep-chunk",
    "wikipedia-revision",
    "stackexchange-answer",
    "raid-generation",
    "wildchat-turn",
    "generated",
)
# Machine-written kinds. Their entries carry label "machine" and the
# generating model; every other kind is human by provenance.
MACHINE_KINDS = ("raid-generation", "wildchat-turn", "generated")
# About a quarter of all documents, human and machine, form the dev split, the
# only part rule tuning may look at. Published rates use the test split.
DEV_SPLIT_HEX = "0123"


def digest_split(digest: str) -> str:
    """dev or test, from the content digest: stable, and needs no stored seed.

    Machine entries record it in the manifest; for human entries fp_measure
    derives it from the same digest, so old manifests need no rewrite."""
    return "dev" if digest[0] in DEV_SPLIT_HEX else "test"


# ---------------------------------------------------------------- utilities


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    # Straight and curly apostrophes, so "don’t" is one word.
    return len(re.findall(r"[A-Za-z0-9'’-]+", text))


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"schema": MANIFEST_SCHEMA, "cutoff": CUTOFF, "entries": []}


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def save_manifest(manifest: dict) -> None:
    entries = sorted(manifest["entries"], key=lambda entry: entry["id"])
    public = {key: value for key, value in manifest.items() if key not in ("entries", "private_pools")}
    public["entries"] = entries
    CORPUS_DIR.mkdir(exist_ok=True)
    _write_json(MANIFEST_PATH, public)


ENTRY_ID_RE = re.compile(r"[a-z]+-[0-9a-f]{12}")


def cache_path(entry_id: str) -> Path:
    """Cache file for an entry id, refusing ids that could leave CACHE_DIR."""
    if not ENTRY_ID_RE.fullmatch(entry_id):
        raise ValueError(f"malformed corpus entry id: {entry_id!r}")
    return CACHE_DIR / f"{entry_id}.txt"


def write_cache(entry_id: str, text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(entry_id).write_text(text, encoding="utf-8", newline="\n")


def read_cache(entry_id: str) -> str:
    """Cached text exactly as written. read_text() would translate a lone CR
    or CRLF to LF, so a corrupted file could still match its digest and a
    text holding a literal CR could never match it."""
    return cache_path(entry_id).read_bytes().decode("utf-8")


def save_pool(kind: str, pairs: list[tuple[dict, str, dict]]) -> list[dict]:
    """Persist one pool: manifest entries with public pointers, cache text.

    `pairs` items are (public_fields, text, source). The entry id is the kind
    prefix plus the first 12 hex chars of the content digest. Existing entries
    and cache files for the same kind are replaced (idempotent rebuild).
    """
    prefix = ID_PREFIX[kind]
    manifest = load_manifest()
    for entry_id in [e["id"] for e in manifest["entries"] if e["id"].startswith(f"{prefix}-")]:
        cache_path(entry_id).unlink(missing_ok=True)
    manifest["entries"] = [
        e for e in manifest["entries"] if not e["id"].startswith(f"{prefix}-")
    ]
    entries = []
    seen_digests: set[str] = set()
    duplicates = 0
    for public_fields, text, source in pairs:
        digest = sha256_text(text)
        if digest in seen_digests:
            # Byte-identical documents (reposts) would double-count one text
            # in the measurement and collide on the content-derived id.
            duplicates += 1
            continue
        seen_digests.add(digest)
        entry_id = f"{prefix}-{digest[:12]}"
        entry = {
            "id": entry_id,
            "kind": kind,
            "label": "machine" if kind in MACHINE_KINDS else "human",
            "words": word_count(text),
            "sha256": digest,
            **public_fields,
        }
        if kind in MACHINE_KINDS:
            entry["split"] = digest_split(digest)
        entry["source"] = source  # a public pointer anyone can rebuild from
        entries.append(entry)
        write_cache(entry_id, text)
    manifest["entries"].extend(entries)
    save_manifest(manifest)
    if duplicates:
        print(f"{kind}: dropped {duplicates} byte-identical duplicate document(s)")
    return entries


# ---------------------------------------------------------- text extraction


WIKI_DROP_RES = [
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"<ref[^>/]*/>", re.I),
    re.compile(r"<ref[^>]*>.*?</ref>", re.S | re.I),
    re.compile(r"\{\|.*?\|\}", re.S),  # tables
    re.compile(r"\[\[(?:File|Image|Category):[^\]]*\]\]", re.I),
]
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
WIKILINK_PIPED_RE = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
WIKILINK_RE = re.compile(r"\[\[([^\]]*)\]\]")
EXTLINK_RE = re.compile(r"\[https?://\S+ ([^\]]*)\]")
BARE_EXTLINK_RE = re.compile(r"\[https?://\S+\]")
HEADING_RE = re.compile(r"^=+\s*(.*?)\s*=+\s*$", re.M)
HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def wikitext_strip_v1(wikitext: str) -> str:
    """The wikitext-strip.v1 extraction, kept byte-for-byte so `fetch` can
    rebuild existing v1 entries to their published digests. New builds use
    ``wikitext_strip`` (v2)."""
    text = wikitext
    for regex in WIKI_DROP_RES:
        text = regex.sub(" ", text)
    for _ in range(4):  # nested templates, innermost first
        text, n = TEMPLATE_RE.subn(" ", text)
        if not n:
            break
    text = WIKILINK_PIPED_RE.sub(r"\1", text)
    text = WIKILINK_RE.sub(r"\1", text)
    return _wikitext_finish(text)


MEDIA_LINK_RE = re.compile(r"\[\[(?:File|Image|Category):[^\[\]]*\]\]", re.I)
INNER_PIPED_LINK_RE = re.compile(r"\[\[(?!(?:File|Image|Category):)[^\[\]|]*\|([^\[\]]*)\]\]", re.I)
INNER_LINK_RE = re.compile(r"\[\[(?!(?:File|Image|Category):)([^\[\]|]*)\]\]", re.I)
WIKI_NEST_LIMIT = 100


def wikitext_strip(wikitext: str) -> str:
    """Reduce wikitext to plain prose so markup never counts as a tell (v2).

    v1 unwrapped at most four template levels and dropped a media link at its
    first "]]", so a caption holding a link ("[[File:x|A [[Foo]] map]]") left
    " map]]" behind. v2 resolves templates and links innermost first until
    nothing changes.
    """
    text = wikitext
    for regex in WIKI_DROP_RES[:4]:
        text = regex.sub(" ", text)
    for _ in range(WIKI_NEST_LIMIT):
        text, n = TEMPLATE_RE.subn(" ", text)
        if not n:
            break
    for _ in range(WIKI_NEST_LIMIT):
        before = text
        text = INNER_PIPED_LINK_RE.sub(r"\1", text)
        text = INNER_LINK_RE.sub(r"\1", text)
        text = EXTLINK_RE.sub(r"\1", text)
        text = BARE_EXTLINK_RE.sub(" ", text)
        text = MEDIA_LINK_RE.sub(" ", text)
        if text == before:
            break
    return _wikitext_finish(text)


WIKITEXT_STRIPPERS = {"wikitext-strip.v1": wikitext_strip_v1, WIKITEXT_STRIP_VERSION: wikitext_strip}


def _wikitext_finish(text: str) -> str:
    text = EXTLINK_RE.sub(r"\1", text)
    text = BARE_EXTLINK_RE.sub(" ", text)
    text = HEADING_RE.sub(r"\1", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"^[*#:;]+\s*", "", text, flags=re.M)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------- api helpers


def api_get(api_url: str, params: dict, sleep: float) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    request = urllib.request.Request(
        f"{api_url}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
    time.sleep(sleep)
    return payload


# ------------------------------------------------------- wikipedia build


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SITE = "en.wikipedia.org"
WIKIPEDIA_RANDOM_BATCH = 20
WIKIPEDIA_MAX_WORDS = 4000  # whole articles, bounded so one page cannot dominate a run


def wikipedia_revision(title: str, sleep: float) -> dict | None:
    """The article's last revision before the cutoff, with its wikitext."""
    payload = api_get(
        WIKIPEDIA_API,
        {
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "rvlimit": 1,
            "rvstart": f"{CUTOFF}T00:00:00Z",
            "rvdir": "older",
        },
        sleep,
    )
    page = next(iter(payload.get("query", {}).get("pages", {}).values()), {})
    revisions = page.get("revisions") or []
    if not revisions or "missing" in page:
        return None
    rev = revisions[0]
    return {
        "title": page.get("title", title),
        "revid": rev["revid"],
        "timestamp": rev["timestamp"],
        "wikitext": rev.get("slots", {}).get("main", {}).get("*", ""),
    }


def wikipedia_pair(rev: dict) -> tuple[dict, str, dict] | None:
    text = wikitext_strip(rev["wikitext"])
    words = word_count(text)
    if not (MIN_WORDS["wiki"] <= words <= WIKIPEDIA_MAX_WORDS):
        return None
    return (
        {
            "register": "wiki",
            "author": "other",
            "date": rev["timestamp"][:7],
            "extraction": WIKITEXT_STRIP_VERSION,
        },
        text,
        {
            "site": WIKIPEDIA_SITE,
            "title": rev["title"],
            "revid": rev["revid"],
            "url": f"https://{WIKIPEDIA_SITE}/w/index.php?oldid={rev['revid']}",
        },
    )


def build_wikipedia(args: argparse.Namespace) -> int:
    """Wiki-register human pool: random English Wikipedia articles, each at
    its last revision before the cutoff (CC BY-SA 4.0; the pointer is the
    revision id, so the exact text can be fetched again)."""
    pairs: list[tuple[dict, str, dict]] = []
    dropped: Counter = Counter()
    seen: set[str] = set()
    stalled = 0
    while len(pairs) < args.target and stalled < 5:
        try:
            payload = api_get(
                WIKIPEDIA_API,
                {"action": "query", "list": "random", "rnnamespace": 0, "rnlimit": WIKIPEDIA_RANDOM_BATCH},
                args.sleep,
            )
        except FETCH_ERRORS as error:
            print(f"wikipedia: random listing failed ({error})", flush=True)
            stalled += 1
            continue
        titles = [item["title"] for item in payload.get("query", {}).get("random", [])]
        if not titles:
            stalled += 1
            continue
        for title in titles:
            if len(pairs) >= args.target:
                break
            if title in seen:
                continue
            seen.add(title)
            try:
                rev = wikipedia_revision(title, args.sleep)
            except FETCH_ERRORS:
                dropped["fetch-failed"] += 1
                continue
            if rev is None:
                dropped["no-pre-cutoff-revision"] += 1
                continue
            pair = wikipedia_pair(rev)
            if pair is None:
                dropped["word-band"] += 1
                continue
            pairs.append(pair)
        print(f"wikipedia: {len(pairs)}/{args.target} kept, {len(seen)} titles tried", flush=True)
    if not pairs:
        print("FAIL: no Wikipedia articles collected; the existing pool was kept", file=sys.stderr)
        return 1
    entries = save_pool("wikipedia-revision", pairs)
    print(f"wikipedia: {len(entries)} articles cached (target {args.target}); drops: {dict(dropped)}")
    return 0


# --------------------------------------------------- stack exchange build


STACKEXCHANGE_API = "https://api.stackexchange.com/2.3"
# Hobby, language, and workplace sites: conversational human prose, little code.
STACKEXCHANGE_SITES = (
    "english",
    "writing",
    "cooking",
    "gardening",
    "travel",
    "workplace",
    "academia",
    "money",
    "diy",
    "history",
)
STACKEXCHANGE_PAGE = 100
STACKEXCHANGE_MAX_WORDS = 1200
HTML_STRIP_VERSION = "html-strip.v1"
HTML_BLOCK_DROP_RE = re.compile(r"<(pre|code|blockquote)\b[^>]*>.*?</\1>", re.S | re.I)
HTML_BREAK_RE = re.compile(r"</(?:p|li|h\d|div|blockquote|tr)>|<br\s*/?>", re.I)


def html_strip(markup: str) -> str:
    """Answer HTML to prose: code, preformatted, and quoted blocks dropped
    (not the answerer's prose), block ends become paragraph breaks."""
    text = HTML_BLOCK_DROP_RE.sub(" ", markup)
    text = HTML_BREAK_RE.sub("\n\n", text)
    text = HTML_TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def stackexchange_pairs(items: list[dict], site: str) -> tuple[list, Counter]:
    """Corpus pairs from one site's answer rows. An answer edited after the
    cutoff is not pre-cutoff text, so it is dropped like a post-cutoff one."""
    pairs: list[tuple[dict, str, dict]] = []
    dropped: Counter = Counter()
    for item in items:
        created = int(item.get("creation_date") or 0)
        if created >= CUTOFF_EPOCH:
            dropped["post-cutoff"] += 1
            continue
        edited = item.get("last_edit_date")
        if edited is not None and int(edited) >= CUTOFF_EPOCH:
            dropped["edited-post-cutoff"] += 1
            continue
        text = html_strip(str(item.get("body") or ""))
        words = word_count(text)
        if not (MIN_WORDS["chat"] <= words <= STACKEXCHANGE_MAX_WORDS):
            dropped["word-band"] += 1
            continue
        answer_id = int(item["answer_id"])
        pairs.append(
            (
                {
                    "register": "chat",
                    "author": "other",
                    "date": time.strftime("%Y-%m", time.gmtime(created)),
                    "extraction": HTML_STRIP_VERSION,
                },
                text,
                {
                    "site": site,
                    "answer_id": answer_id,
                    "url": f"https://{site}.stackexchange.com/a/{answer_id}",
                },
            )
        )
    return pairs, dropped


def stackexchange_get(path: str, params: dict, sleep: float) -> dict:
    payload = api_get(f"{STACKEXCHANGE_API}/{path}", {**params, "filter": "withbody"}, sleep)
    backoff = payload.get("backoff")
    if backoff:
        time.sleep(float(backoff))
    return payload


def build_stackexchange(args: argparse.Namespace) -> int:
    """Chat-register human pool: top-voted pre-cutoff answers from hobby and
    language Stack Exchange sites (CC BY-SA; the pointer is the answer id).
    The API allows 300 requests a day without a key; a run uses about one
    per site per page."""
    pairs: list[tuple[dict, str, dict]] = []
    dropped: Counter = Counter()
    for site in STACKEXCHANGE_SITES:
        site_pairs: list = []
        for page in range(1, args.pages + 1):
            try:
                payload = stackexchange_get(
                    "answers",
                    {
                        "site": site,
                        "todate": CUTOFF_EPOCH,
                        "order": "desc",
                        "sort": "votes",
                        "pagesize": STACKEXCHANGE_PAGE,
                        "page": page,
                    },
                    args.sleep,
                )
            except FETCH_ERRORS as error:
                print(f"stackexchange: {site} page {page} failed ({error})", flush=True)
                break
            kept, drops = stackexchange_pairs(payload.get("items", []), site)
            site_pairs.extend(kept)
            dropped.update(drops)
            if len(site_pairs) >= args.per_site or not payload.get("has_more"):
                break
        pairs.extend(site_pairs[: args.per_site])
        print(f"stackexchange: {site}: {min(len(site_pairs), args.per_site)} answers kept", flush=True)
    if not pairs:
        print("FAIL: no Stack Exchange answers collected; the existing pool was kept", file=sys.stderr)
        return 1
    entries = save_pool("stackexchange-answer", pairs)
    print(f"stackexchange: {len(entries)} answers cached; drops: {dict(dropped)}")
    return 0


# ----------------------------------------------------- public-domain build


PD_SOURCE = ROOT / "reference" / "elements-of-style-1918.md"
PD_CHUNK_WORDS = 500


def build_pd(_args: argparse.Namespace) -> int:
    # The in-repo file is a full Project Gutenberg download. Chunk only the
    # book between the START/END markers: the header and the licence are
    # modern Gutenberg text, not 1918 Strunk, and counted as such they put
    # post-1918 prose into the "1918" essay slice.
    chunks = gutenberg_chunks(PD_SOURCE.read_text(encoding="utf-8"))
    pairs = [
        (
            {
                "register": "essay",
                "author": "public-domain",
                "date": "1918",
                "extraction": CHUNK_VERSION,
            },
            chunk,
            {
                "work": "reference/elements-of-style-1918.md",
                "chunk": index,
                "chunk_words": PD_CHUNK_WORDS,
            },
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    entries = save_pool("public-domain", pairs)
    print(f"public-domain: {len(entries)} chunks cached from {PD_SOURCE.name}")
    return 0


# -------------------------------------------------------------- news build


IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_QUERY = "collection:(newspapers) AND year:[1900 TO 1922] AND format:(DjVuTXT)"
NEWS_DATE1, NEWS_DATE2 = "1900", "1922"  # comfortably public domain
NEWS_CHUNK_WORDS = 600
NEWS_CHUNK_MIN, NEWS_CHUNK_MAX = 200, 1200
NEWS_CHUNKS_PER_ISSUE = 3
NEWS_MIN_ALPHA_RATIO = 0.72
NEWS_MIN_THE_RATIO = 0.02  # crude English check: "the" frequency
OCR_CLEAN_VERSION = "ocr-chunk.v3"


FETCH_ERRORS = (urllib.error.URLError, OSError, http.client.HTTPException)


def fetch_text_with_retry(url: str, sleep: float, attempts: int = 4, headers: dict | None = None) -> str:
    """fetch_text with linear backoff on rate limits and transient failures.

    Archive endpoints answer bursts with 429/503, and a read timeout raises
    TimeoutError (an OSError, not a URLError). Other HTTP errors (404 and the
    like) are permanent and raise at once.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fetch_text(url, sleep, headers)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == attempts:
                raise
            wait = 30 * attempt
        except FETCH_ERRORS:
            if attempt == attempts:
                raise
            wait = 10 * attempt
        print(f"fetch failed for {url}; retrying in {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError("unreachable")


def ocr_clean(text: str) -> str:
    # JSON-escaped CRs in HF rows survive fetch_text's newline pass.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def alpha_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    alpha = sum(1 for token in tokens if re.fullmatch(r"[A-Za-z'’-]+[.,;:!?\"'’)]*", token))
    return alpha / len(tokens)


def english_ratio(text: str) -> float:
    tokens = text.lower().split()
    if not tokens:
        return 0.0
    return tokens.count("the") / len(tokens)


def _split_oversized(paragraph: str) -> list[str]:
    """Split a paragraph past the chunk cap on line boundaries (v2 behavior).

    Some OCR sources emit a whole page as one block with only single
    newlines; without this, every page becomes one oversized chunk and the
    word-band gate drops it.
    """
    if word_count(paragraph) <= NEWS_CHUNK_MAX:
        return [paragraph]
    pieces, current, current_words = [], [], 0
    for line in paragraph.split("\n"):
        current.append(line)
        current_words += word_count(line)
        if current_words >= NEWS_CHUNK_WORDS:
            pieces.append("\n".join(current))
            current, current_words = [], 0
    if current:
        pieces.append("\n".join(current))
    return pieces


def news_chunks(raw: str) -> list[str]:
    text = ocr_clean(raw)
    paragraphs = [
        piece
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
        for piece in _split_oversized(p.strip())
    ]
    chunks, current, current_words = [], [], 0
    for paragraph in paragraphs:
        current.append(paragraph)
        current_words += word_count(paragraph)
        if current_words >= NEWS_CHUNK_WORDS:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
    if current and current_words >= NEWS_CHUNK_MIN:
        chunks.append("\n\n".join(current))
    return chunks


def build_news(args: argparse.Namespace) -> int:
    """Build the news pool from Internet Archive newspaper issues (1900-1922).

    Whole public-domain issues are downloaded as OCR text, chunked into
    ~600-word documents, and gated per chunk: word band, alphabetic-token
    ratio (OCR quality), and a crude English check. At most a few chunks are
    kept per issue so the pool spans many papers. Every drop is counted aloud;
    RESULTS.md states the OCR caveat next to the numbers.
    """
    # Do not route through api_get: it appends format=json, which IA's search
    # reads as a *metadata filter* (format:"json") and returns zero results.
    search_url = IA_SEARCH + "?" + urllib.parse.urlencode(
        {
            "q": IA_QUERY,
            "fl[]": "identifier",
            # Without an explicit sort the result order is not stable, so a
            # rebuild could select different issues.
            "sort[]": "identifier asc",
            "rows": str(args.issues),
            "page": "1",
            "output": "json",
        }
    )
    payload = json.loads(fetch_text_with_retry(search_url, args.sleep))
    identifiers = [
        doc["identifier"] for doc in payload.get("response", {}).get("docs", [])
    ]
    print(f"news: {len(identifiers)} candidate issues from Internet Archive", flush=True)
    pairs: list[tuple[dict, str, dict]] = []
    dropped = Counter()
    issues_used = 0
    for ident in identifiers:
        if len(pairs) >= args.target:
            break
        url = f"https://archive.org/download/{ident}/{ident}_djvu.txt"
        try:
            raw = fetch_text_with_retry(url, args.sleep)
        except FETCH_ERRORS:
            dropped["download-failed"] += 1
            continue
        kept_this_issue = 0
        # Skip the first chunk (masthead/OCR header noise) when others exist.
        chunks = news_chunks(raw)
        for index, chunk in enumerate(chunks[1:] or chunks, start=1):
            if len(pairs) >= args.target or kept_this_issue >= NEWS_CHUNKS_PER_ISSUE:
                break
            words = word_count(chunk)
            if not (NEWS_CHUNK_MIN <= words <= NEWS_CHUNK_MAX):
                dropped["word-band"] += 1
                continue
            if alpha_ratio(chunk) < NEWS_MIN_ALPHA_RATIO:
                dropped["ocr-quality"] += 1
                continue
            if english_ratio(chunk) < NEWS_MIN_THE_RATIO:
                dropped["not-english"] += 1
                continue
            pairs.append(
                (
                    {
                        "register": "news",
                        "author": "public-domain",
                        "date": f"{NEWS_DATE1}-{NEWS_DATE2}",
                        "extraction": OCR_CLEAN_VERSION,
                    },
                    chunk,
                    {
                        "url": f"https://archive.org/details/{ident}",
                        "ia_identifier": ident,
                        "chunk": index,
                    },
                )
            )
            kept_this_issue += 1
        issues_used += 1 if kept_this_issue else 0
    entries = save_pool("news-page", pairs)
    print(
        f"news: {len(entries)} chunks cached from {issues_used} issues "
        f"(target {args.target}); drops: {dict(dropped)}"
    )
    return 0


# -------------------------------------------------- hf news (OpenCulture)


HF_ROWS_API = "https://datasets-server.huggingface.co/rows"
HF_NEWS_DATASET = "PleIAs/US-PD-Newspapers"
# Fixed, spread offsets so the sample crosses many papers and years while
# staying deterministic (no randomness; see resume rules). datasets-server
# caps length at 100 rows per call, and probed offsets past ~2M drop the
# connection on this dataset — stay inside the window that answers.
HF_NEWS_OFFSETS = (0, 300_000, 600_000, 900_000, 1_200_000, 1_500_000, 1_800_000, 2_000_000)
HF_NEWS_MAX_YEAR = 1928  # public-domain safety margin


def build_hf_news(args: argparse.Namespace) -> int:
    """Grow the news pool from OpenCulture's US-PD-Newspapers (HF rows API).

    Page-level pre-extracted OCR text; chunked and gated exactly like the
    Internet Archive pool. English-only dataset; dates capped at 1928.
    """
    pairs: list[tuple[dict, str, dict]] = []
    dropped = Counter()
    for offset in HF_NEWS_OFFSETS:
        if len(pairs) >= args.target:
            break
        query = urllib.parse.urlencode(
            {
                "dataset": HF_NEWS_DATASET,
                "config": "default",
                "split": "train",
                "offset": offset,
                "length": "100",
            }
        )
        try:
            payload = json.loads(fetch_text(f"{HF_ROWS_API}?{query}", args.sleep))
        except FETCH_ERRORS as error:
            dropped["offset-fetch-failed"] += 1
            print(f"offset {offset}: fetch failed ({error}); skipping", flush=True)
            continue
        for item in payload.get("rows", []):
            if len(pairs) >= args.target:
                break
            row = item.get("row", {})
            date = str(row.get("date") or "")
            year = date[:4]
            if not (year.isdigit() and int(year) <= HF_NEWS_MAX_YEAR):
                dropped["outside-date-range"] += 1
                continue
            kept_this_page = 0
            chunks = news_chunks(str(row.get("text") or ""))
            for index, chunk in enumerate(chunks[1:] or chunks, start=1):
                if len(pairs) >= args.target or kept_this_page >= NEWS_CHUNKS_PER_ISSUE:
                    break
                chunk_words = word_count(chunk)
                if not (NEWS_CHUNK_MIN <= chunk_words <= NEWS_CHUNK_MAX):
                    dropped["word-band"] += 1
                    continue
                if alpha_ratio(chunk) < NEWS_MIN_ALPHA_RATIO:
                    dropped["ocr-quality"] += 1
                    continue
                if english_ratio(chunk) < NEWS_MIN_THE_RATIO:
                    dropped["not-english"] += 1
                    continue
                pairs.append(
                    (
                        {
                            "register": "news",
                            "author": "public-domain",
                            "date": year,
                            "extraction": OCR_CLEAN_VERSION,
                        },
                        chunk,
                        {
                            "dataset": HF_NEWS_DATASET,
                            "id": str(row.get("id") or ""),
                            "date": date,
                            "file_name": str(row.get("file_name") or ""),
                            "chunk": index,
                        },
                    )
                )
                kept_this_page += 1
    if not pairs:
        print("FAIL: no OpenCulture chunks collected; the existing pool was kept", file=sys.stderr)
        return 1
    entries = save_pool("hf-news", pairs)
    print(
        f"hf-news: {len(entries)} chunks cached (target {args.target}); "
        f"drops: {dict(dropped)}"
    )
    return 0


# ------------------------------------------------------ gutenberg essays


GUTENBERG_WORKS = [
    # (gutenberg id, short name) — all authors died before 1923; public domain.
    (2944, "emerson-essays-first-series"),
    (205, "thoreau-walden"),
    (3250, "twain-how-to-tell-a-story"),
]
GUTENBERG_URL = "https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt"
START_MARKER_RE = re.compile(r"\*\*\* ?START OF.*?\*\*\*", re.S)
END_MARKER_RE = re.compile(r"\*\*\* ?END OF.*", re.S)


def fetch_text(url: str, sleep: float, headers: dict | None = None) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read().decode("utf-8", errors="replace")
    time.sleep(sleep)
    # Normalize newlines so cached bytes hash identically across platforms.
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def paragraph_chunks(body: str, chunk_words: int, min_words: int) -> list[str]:
    """Group whole paragraphs into chunks of at least ``chunk_words`` words;
    a final remainder is kept only if it reaches ``min_words``."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks, current, current_words = [], [], 0
    for paragraph in paragraphs:
        current.append(paragraph)
        current_words += word_count(paragraph)
        if current_words >= chunk_words:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
    if current and current_words >= min_words:
        chunks.append("\n\n".join(current))
    return chunks


def gutenberg_chunks(raw: str) -> list[str]:
    body = START_MARKER_RE.split(raw, maxsplit=1)[-1]
    body = END_MARKER_RE.sub("", body)
    return paragraph_chunks(body, PD_CHUNK_WORDS, MIN_WORDS["essay"])


def build_essays(args: argparse.Namespace) -> int:
    """Chunk public-domain Gutenberg essay-register works (beyond Strunk)."""
    pairs: list[tuple[dict, str, dict]] = []
    for gid, name in GUTENBERG_WORKS:
        url = GUTENBERG_URL.format(gid=gid)
        raw = fetch_text(url, args.sleep)
        chunks = gutenberg_chunks(raw)
        for index, chunk in enumerate(chunks, start=1):
            pairs.append(
                (
                    {
                        "register": "essay",
                        "author": "public-domain",
                        "date": "pre-1923",
                        "extraction": CHUNK_VERSION,
                    },
                    chunk,
                    {
                        "work": name,
                        "gutenberg_id": gid,
                        "url": url,
                        "chunk": index,
                        "chunk_words": PD_CHUNK_WORDS,
                    },
                )
            )
        print(f"gutenberg: {name} -> {len(chunks)} chunks")
    entries = save_pool("gutenberg-work", pairs)
    print(f"gutenberg: {len(entries)} chunks cached from {len(GUTENBERG_WORKS)} works")
    return 0


# ------------------------------------------------------------- PEPs (docs)


GITHUB_API = "https://api.github.com"
PEPS_REPO = "python/peps"
PEP_FILE_RE = re.compile(r"(?:^|/)pep-(\d{4})\.(?:txt|rst)$")
PEP_HEADER_RE = re.compile(r"^[A-Z][A-Za-z-]*:\s")
PEP_CREATED_RE = re.compile(r"^Created:\s*.*?(\d{4})", re.M)
PEP_PUBLIC_DOMAIN_RE = re.compile(r"placed\s+in\s+the\s+public\s+domain", re.I)
RST_STOP_HEADINGS = {"copyright", "references", "footnotes"}
RST_ADORNMENT_RE = re.compile(r"""^([=\-~^"'`#*+:.])\1{2,}\s*$""")
RST_SIMPLE_TABLE_RE = re.compile(r"^=+(?:\s+=+)+\s*$")
RST_INLINE_LITERAL_RE = re.compile(r"``[^`]+``")
RST_LINK_RE = re.compile(r"`([^`<]+?)\s*<[^>]+>`__?")
RST_ROLE_RE = re.compile(r":[a-z][\w-]*:`([^`]+)`")
RST_REF_RE = re.compile(r"`([^`]+)`_{1,2}")
RST_FOOTNOTE_REF_RE = re.compile(r"\s*\[(?:#\w*|\d+|\*)\]_")
RST_EMPHASIS_RE = re.compile(r"\*\*([^*\n]+)\*\*|\*([^*\n]+)\*")
RST_BULLET_RE = re.compile(r"^[ \t]*(?:[-*+]|#\.|\d+\.)[ \t]+", re.M)
RST_STRIP_VERSION = "rst-strip.v1"
PEP_CHUNK_WORDS = 500
PEP_CHUNKS_PER_PEP = 2


def rst_strip(raw: str) -> str:
    """Reduce a PEP's reStructuredText to prose: no header block, code,
    directives, tables, or reference sections."""
    lines = raw.replace("\r\n", "\n").split("\n")
    # The RFC 822-style header block ends at the first blank line.
    if lines and PEP_HEADER_RE.match(lines[0]):
        while lines and lines[0].strip():
            lines.pop(0)
    out: list[str] = []
    skip_indent: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if skip_indent is not None:
            # Inside a literal block or directive: skip blank and indented lines.
            if not stripped or indent > skip_indent:
                continue
            skip_indent = None
            # Keep the paragraph break the skipped block stood in.
            if out and out[-1]:
                out.append("")
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if stripped.lower() in RST_STOP_HEADINGS and RST_ADORNMENT_RE.match(following):
            break
        if stripped.startswith(".. ") or stripped == "..":
            skip_indent = indent
            continue
        if RST_ADORNMENT_RE.match(stripped) or RST_SIMPLE_TABLE_RE.match(stripped):
            continue
        if stripped.startswith(("+-", "+=", "|")):
            continue
        if stripped.endswith("::"):
            skip_indent = indent
            line = line.rstrip()[:-2].rstrip()
            if line.strip():
                out.append(line.strip() + ":")
            continue
        out.append(stripped)
    text = "\n".join(out)
    # Keep the literal's text so the sentence around it stays whole.
    text = RST_INLINE_LITERAL_RE.sub(lambda m: m.group(0)[2:-2], text)
    text = RST_LINK_RE.sub(r"\1", text)
    text = RST_ROLE_RE.sub(r"\1", text)
    text = RST_REF_RE.sub(r"\1", text)
    text = RST_FOOTNOTE_REF_RE.sub("", text)
    text = RST_EMPHASIS_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = RST_BULLET_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +([.,;:])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pep_pairs(files: list[tuple[str, str]], commit: str, target: int) -> tuple[list, Counter]:
    """Chunk PEP sources into corpus pairs. ``files`` is [(path, raw)]."""
    pairs: list[tuple[dict, str, dict]] = []
    dropped: Counter = Counter()
    for path, raw in sorted(files, key=lambda item: item[0]):
        if len(pairs) >= target:
            break
        if not PEP_PUBLIC_DOMAIN_RE.search(raw):
            dropped["not-public-domain"] += 1
            continue
        created = PEP_CREATED_RE.search(raw)
        chunks = paragraph_chunks(rst_strip(raw), PEP_CHUNK_WORDS, MIN_WORDS["docs"])
        if not chunks:
            dropped["too-short"] += 1
            continue
        for index, chunk in enumerate(chunks[:PEP_CHUNKS_PER_PEP], start=1):
            if len(pairs) >= target:
                break
            pairs.append(
                (
                    {
                        "register": "docs",
                        "author": "other",
                        "date": created.group(1) if created else "pre-2022",
                        "extraction": RST_STRIP_VERSION,
                    },
                    chunk,
                    {"repo": PEPS_REPO, "commit": commit, "path": path, "chunk": index},
                )
            )
    return pairs, dropped


def github_json(url: str, sleep: float) -> object:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return json.loads(fetch_text_with_retry(url, sleep, headers=headers))


def build_peps(args: argparse.Namespace) -> int:
    """Docs-register human pool: Python Enhancement Proposals, public domain.

    The text is read at the python/peps commit that was current at the
    cutoff, so every word predates it; later edits never enter the corpus.
    """
    try:
        commits = github_json(
            f"{GITHUB_API}/repos/{PEPS_REPO}/commits?until={CUTOFF}T00:00:00Z&per_page=1",
            args.sleep,
        )
        commit = commits[0]["sha"]
        committed = commits[0]["commit"]["committer"]["date"]
        # Guard the cutoff on the response itself rather than trusting how
        # the API interprets `until`.
        if committed >= f"{CUTOFF}T00:00:00Z":
            print(f"FAIL: commit {commit[:12]} is dated {committed}, not before {CUTOFF}", file=sys.stderr)
            return 1
        tree = github_json(f"{GITHUB_API}/repos/{PEPS_REPO}/git/trees/{commit}?recursive=1", args.sleep)
    except FETCH_ERRORS as error:
        print(f"FAIL: GitHub API unreachable ({error})", file=sys.stderr)
        return 1
    if tree.get("truncated"):
        print("WARNING: GitHub truncated the tree listing; some PEPs may be missing")
    paths = sorted(
        item["path"] for item in tree.get("tree", [])
        if item.get("type") == "blob" and PEP_FILE_RE.search(item["path"])
    )
    print(f"peps: {len(paths)} PEP files at {commit[:12]} (last commit before {CUTOFF})", flush=True)
    files: list[tuple[str, str]] = []
    failed = 0
    for path in paths:
        url = f"https://raw.githubusercontent.com/{PEPS_REPO}/{commit}/{path}"
        try:
            files.append((path, fetch_text_with_retry(url, args.sleep)))
        except FETCH_ERRORS:
            failed += 1
    if failed:
        print(f"FAIL: {failed} PEP downloads failed; the existing pool was kept", file=sys.stderr)
        return 1
    pairs, dropped = pep_pairs(files, commit, args.target)
    if not pairs:
        print("FAIL: no PEP chunks produced; the existing pool was kept", file=sys.stderr)
        return 1
    entries = save_pool("pep-chunk", pairs)
    print(
        f"peps: {len(entries)} chunks cached (target {args.target}); "
        f"{failed} downloads failed; drops: {dict(dropped)}"
    )
    return 0


# ------------------------------------------------- machine pools (labelled)


RAID_URL = "https://dataset.raid-bench.xyz/train_none.csv"  # MIT; test labels are hidden
RAID_DOMAINS = {"wiki": "wiki", "news": "news", "reddit": "chat"}
# Instruction-tuned or chat generators only: GPT-2 and the base models are
# not what people paste into documents.
RAID_MODELS = ("chatgpt", "gpt4", "gpt3", "llama-chat", "mistral-chat", "mpt-chat", "cohere-chat")
RAID_EXTRACTION = "raid.v1"


def raid_pairs(rows, per_cell: int) -> tuple[list, Counter]:
    """Select RAID generations: sampling without repetition penalty, no
    adversarial attack, up to ``per_cell`` per (domain, model)."""
    pairs: list[tuple[dict, str, dict]] = []
    dropped: Counter = Counter()
    cells: Counter = Counter()
    wanted = len(RAID_DOMAINS) * len(RAID_MODELS) * per_cell
    for row in rows:
        domain, model = row.get("domain"), row.get("model")
        if domain not in RAID_DOMAINS or model not in RAID_MODELS:
            continue
        if row.get("attack", "none") != "none" or row.get("decoding") != "sampling" or row.get(
            "repetition_penalty"
        ) != "no":
            dropped["decoding-or-attack"] += 1
            continue
        if cells[(domain, model)] >= per_cell:
            continue
        register = RAID_DOMAINS[domain]
        text = (row.get("generation") or "").strip()
        if word_count(text) < MIN_WORDS[register]:
            dropped["under-min-words"] += 1
            continue
        cells[(domain, model)] += 1
        pairs.append(
            (
                {
                    "register": register,
                    "author": "machine",
                    "model": f"raid:{model}",
                    "date": "2023",
                    "extraction": RAID_EXTRACTION,
                },
                text,
                {"dataset": "liamdugan/raid", "file": "train_none.csv", "id": str(row.get("id", ""))},
            )
        )
        if len(pairs) >= wanted:
            break
    return pairs, dropped


def build_raid(args: argparse.Namespace) -> int:
    """Machine pool from RAID (Dugan et al., ACL 2024), streamed, not stored whole."""
    import csv
    import io

    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    request = urllib.request.Request(RAID_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            reader = csv.DictReader(io.TextIOWrapper(response, encoding="utf-8", newline=""))
            pairs, dropped = raid_pairs(reader, args.per_cell)
    except FETCH_ERRORS as error:
        print(f"FAIL: RAID download failed ({error}); nothing saved", file=sys.stderr)
        return 1
    if not pairs:
        print("FAIL: no RAID generations matched; the existing pool was kept", file=sys.stderr)
        return 1
    cells = Counter((meta["model"], meta["register"]) for meta, _text, _source in pairs)
    short = {f"{model}/{register}": n for (model, register), n in sorted(cells.items()) if n < args.per_cell}
    entries = save_pool("raid-generation", pairs)
    print(f"raid: {len(entries)} generations cached; drops: {dict(dropped)}")
    if short or len(cells) < len(RAID_DOMAINS) * len(RAID_MODELS):
        print(f"NOTE: cells below quota or empty: {short or 'some cells empty'}")
    return 0


WILDCHAT_DATASET = "allenai/WildChat-1M"  # ODC-BY
WILDCHAT_OFFSETS = tuple(range(0, 800_001, 100_000))
WILDCHAT_EXTRACTION = "wildchat-first-reply.v1"
WILDCHAT_MAX_WORDS = 1200


def wildchat_pairs(rows, target: int) -> tuple[list, Counter]:
    """First assistant reply of English conversations, prose only."""
    pairs: list[tuple[dict, str, dict]] = []
    dropped: Counter = Counter()
    for row in rows:
        if len(pairs) >= target:
            break
        if row.get("language") != "English":
            dropped["not-english"] += 1
            continue
        reply = next(
            (turn.get("content") or "" for turn in row.get("conversation") or [] if turn.get("role") == "assistant"),
            "",
        ).strip()
        if "```" in reply:
            dropped["code-reply"] += 1
            continue
        words = word_count(reply)
        if not (MIN_WORDS["chat"] <= words <= WILDCHAT_MAX_WORDS):
            dropped["word-band"] += 1
            continue
        timestamp = str(row.get("timestamp") or "")
        pairs.append(
            (
                {
                    "register": "chat",
                    "author": "machine",
                    "model": f"wildchat:{row.get('model') or 'unknown'}",
                    "date": timestamp[:7] if re.match(r"\d{4}-\d{2}", timestamp) else "2023",
                    "extraction": WILDCHAT_EXTRACTION,
                },
                reply,
                {"dataset": WILDCHAT_DATASET, "conversation_hash": str(row.get("conversation_hash") or "")},
            )
        )
    return pairs, dropped


def build_wildchat(args: argparse.Namespace) -> int:
    """Machine pool from WildChat-1M through the Hugging Face rows API.

    Set HF_TOKEN if the dataset asks you to accept its terms first.
    """
    token = os.environ.get("HF_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    rows: list[dict] = []
    for offset in WILDCHAT_OFFSETS:
        query = urllib.parse.urlencode(
            {"dataset": WILDCHAT_DATASET, "config": "default", "split": "train", "offset": offset, "length": "100"}
        )
        try:
            payload = json.loads(fetch_text_with_retry(f"{HF_ROWS_API}?{query}", args.sleep, headers=headers))
        except FETCH_ERRORS as error:
            print(f"offset {offset}: fetch failed ({error}); skipping", flush=True)
            continue
        rows.extend(item.get("row", {}) for item in payload.get("rows", []))
    pairs, dropped = wildchat_pairs(rows, args.target)
    if not pairs:
        print(
            "FAIL: no WildChat replies collected (gated dataset without HF_TOKEN, or offline?); "
            "the existing pool was kept",
            file=sys.stderr,
        )
        return 1
    entries = save_pool("wildchat-turn", pairs)
    print(f"wildchat: {len(entries)} replies cached (target {args.target}); drops: {dict(dropped)}")
    return 0


# ---------------------------------------------------------- fetch / verify


REBUILD_HINT = {
    "gutenberg-work": "build-essays",
    "news-page": "build-news",
    "hf-news": "build-hf-news",
    "pep-chunk": "build-peps",
    "raid-generation": "build-raid",
    "wildchat-turn": "build-wildchat",
    "generated": "scripts/generate_machine.py",
}


def fetch(args: argparse.Namespace) -> int:
    """Repopulate the cache from public pointers.

    Strunk chunks come from the repo; Wikipedia revisions and Stack Exchange
    answers are fetched by id. Other kinds are rebuilt by their own build-*
    subcommand; fetch names the missing ones and exits non-zero while any
    entry stays uncached.
    """
    manifest = load_manifest()
    missing = [entry for entry in manifest["entries"] if not cache_path(entry["id"]).exists()]
    if any(e["kind"] == "public-domain" for e in missing):
        build_pd(args)
    by_kind = Counter(e["kind"] for e in missing if e["kind"] in REBUILD_HINT)
    for kind, count in sorted(by_kind.items()):
        print(f"NOTE: {count} {kind} entries missing; rebuild them with `{REBUILD_HINT[kind]}`.")
    wiki_entries = [e for e in missing if e["kind"] == "wikipedia-revision"]
    for start in range(0, len(wiki_entries), 50):
        batch = wiki_entries[start : start + 50]
        payload = api_get(
            WIKIPEDIA_API,
            {
                "action": "query",
                "prop": "revisions",
                "revids": "|".join(str(e["source"]["revid"]) for e in batch),
                "rvprop": "ids|content",
                "rvslots": "main",
            },
            args.sleep,
        )
        by_revid = {e["source"]["revid"]: e for e in batch}
        for page in payload.get("query", {}).get("pages", {}).values():
            for rev in page.get("revisions", []):
                entry = by_revid.get(rev["revid"])
                if not entry:
                    continue
                # Rebuild with the extraction the entry was published with,
                # or its digest can never match.
                strip = WIKITEXT_STRIPPERS.get(entry.get("extraction", ""))
                if strip is None:
                    print(f"NOTE: {entry['id']}: unknown extraction {entry.get('extraction')!r}")
                    continue
                write_cache(entry["id"], strip(rev.get("slots", {}).get("main", {}).get("*", "")))
    se_entries = [e for e in missing if e["kind"] == "stackexchange-answer"]
    by_site: dict[str, list[dict]] = {}
    for entry in se_entries:
        by_site.setdefault(entry["source"]["site"], []).append(entry)
    for site, site_entries in sorted(by_site.items()):
        for start in range(0, len(site_entries), 100):
            batch = site_entries[start : start + 100]
            ids = ";".join(str(e["source"]["answer_id"]) for e in batch)
            payload = stackexchange_get(f"answers/{ids}", {"site": site}, args.sleep)
            by_id = {e["source"]["answer_id"]: e for e in batch}
            for item in payload.get("items", []):
                entry = by_id.get(int(item.get("answer_id", 0)))
                if entry is not None and entry.get("extraction") == HTML_STRIP_VERSION:
                    write_cache(entry["id"], html_strip(str(item.get("body") or "")))
    still_missing = sum(
        1 for entry in load_manifest()["entries"] if not cache_path(entry["id"]).exists()
    )
    print(
        f"fetch: attempted {len(wiki_entries)} Wikipedia and {len(se_entries)} Stack Exchange "
        f"entries; {still_missing} entries still uncached; run verify next"
    )
    return 1 if still_missing else 0


def verify(_args: argparse.Namespace) -> int:
    manifest = load_manifest()
    missing, mismatched, ok = [], [], 0
    for entry in manifest["entries"]:
        path = cache_path(entry["id"])
        if not path.exists():
            missing.append(entry["id"])
        elif sha256_text(read_cache(entry["id"])) != entry["sha256"]:
            mismatched.append(entry["id"])
        else:
            ok += 1
    print(f"verify: {ok} ok, {len(missing)} missing, {len(mismatched)} mismatched")
    for entry_id in mismatched:
        print(f"  MISMATCH {entry_id}")
    return 1 if mismatched or missing else 0


# ------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_pd = sub.add_parser("build-pd", help="chunk the in-repo Strunk text")
    p_pd.set_defaults(func=build_pd)

    p_news = sub.add_parser(
        "build-news", help="fetch public-domain newspaper text (Internet Archive)"
    )
    p_news.add_argument("--target", type=int, default=150)
    p_news.add_argument("--issues", type=int, default=120)
    p_news.add_argument("--sleep", type=float, default=1.5)
    p_news.set_defaults(func=build_news)

    p_essays = sub.add_parser(
        "build-essays", help="chunk public-domain Gutenberg essay works"
    )
    p_essays.add_argument("--sleep", type=float, default=1.0)
    p_essays.set_defaults(func=build_essays)

    p_hf = sub.add_parser(
        "build-hf-news", help="grow the news pool from OpenCulture (HF rows API)"
    )
    p_hf.add_argument("--target", type=int, default=350)
    p_hf.add_argument("--sleep", type=float, default=1.5)
    p_hf.set_defaults(func=build_hf_news)

    p_wp = sub.add_parser("build-wikipedia", help="wiki-register pool from pre-cutoff Wikipedia revisions")
    p_wp.add_argument("--target", type=int, default=500)
    p_wp.add_argument("--sleep", type=float, default=0.5)
    p_wp.set_defaults(func=build_wikipedia)

    p_se = sub.add_parser("build-stackexchange", help="chat-register pool from pre-cutoff Stack Exchange answers")
    p_se.add_argument("--per-site", type=int, default=60)
    p_se.add_argument("--pages", type=int, default=2, help="API pages of 100 answers per site, at most")
    p_se.add_argument("--sleep", type=float, default=0.5)
    p_se.set_defaults(func=build_stackexchange)

    p_peps = sub.add_parser("build-peps", help="docs-register human pool from pre-cutoff PEPs")
    p_peps.add_argument("--target", type=int, default=400)
    p_peps.add_argument("--sleep", type=float, default=0.2)
    p_peps.set_defaults(func=build_peps)

    p_raid = sub.add_parser("build-raid", help="machine pool from RAID (non-adversarial)")
    p_raid.add_argument("--per-cell", type=int, default=25, help="documents per (domain, model)")
    p_raid.set_defaults(func=build_raid)

    p_wildchat = sub.add_parser("build-wildchat", help="machine pool from WildChat-1M replies")
    p_wildchat.add_argument("--target", type=int, default=300)
    p_wildchat.add_argument("--sleep", type=float, default=1.5)
    p_wildchat.set_defaults(func=build_wildchat)

    p_fetch = sub.add_parser("fetch", help="repopulate cache from the manifest")
    p_fetch.add_argument("--sleep", type=float, default=1.0)
    p_fetch.set_defaults(func=fetch)

    p_verify = sub.add_parser("verify", help="check cache against manifest hashes")
    p_verify.set_defaults(func=verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
