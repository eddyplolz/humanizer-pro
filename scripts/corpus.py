#!/usr/bin/env python3
"""Human-control corpus builder for FP measurement.

Ground truth by provenance, not judgment: every corpus document predates the
public release of ChatGPT (2022-11-30; this corpus uses a 2022-11-01 cutoff
for margin), so any audit flag on it is a false positive by construction.
Design adapted from avoid-ai-writing's corpus/fp-measure (MIT).

The corpus is hash-only and anonymous. `corpus/manifest.json` carries only
register, author tier, date, word count, and SHA-256 digest per document —
no text, no usernames, no source locators. Entry ids are derived from the
digest, so they identify content without describing it. The text lives in
`corpus/cache/` and the source locators in `corpus/sources.local.json`;
both are gitignored and stay on the maintainer's machine. The public-domain
pool is the one exception: its entries point at the public-domain text this
repository already ships, so that slice is independently rebuildable.

Subcommands:
  build-forum   read MyBB dump SQL files, extract pre-cutoff posts
  build-wiki    fetch a wiki user's pre-cutoff revisions via the MediaWiki API
  build-pd      chunk the in-repo public-domain Strunk text
  build-essays  chunk public-domain Gutenberg essay works
  build-news    fetch public-domain newspaper OCR (Internet Archive)
  build-hf-news grow the news pool from OpenCulture (HF rows API)
  build-peps    docs-register pool: PEPs at the last pre-cutoff commit
  build-raid    machine pool: RAID generations (non-adversarial, MIT)
  build-wildchat machine pool: WildChat-1M first replies (ODC-BY)
                (scripts/generate_machine.py adds current Claude models)
  fetch         repopulate the cache (public-domain always; wiki needs the
                maintainer's sources.local.json; other kinds name their
                build-* subcommand)
  verify        check every cached file against its manifest sha256

Maintainer-local settings (dump paths, identity mapping, wiki endpoint) come
from CLI flags or a gitignored `corpus/build.local.json`; they are
deliberately not stored in the manifest or this script.
"""

from __future__ import annotations

import argparse
import hashlib
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
LOCAL_CONFIG_PATH = CORPUS_DIR / "build.local.json"
LOCAL_SOURCES_PATH = CORPUS_DIR / "sources.local.json"

MANIFEST_SCHEMA = "humanizer-corpus-manifest.v1"
SOURCES_SCHEMA = "humanizer-corpus-sources.v1"
CUTOFF = "2022-11-01"
CUTOFF_EPOCH = 1667260800  # 2022-11-01T00:00:00Z
MIN_WORDS = {"chat": 50, "wiki": 150, "essay": 150, "news": 200, "docs": 150}
BBCODE_STRIP_VERSION = "bbcode-strip.v2"
WIKITEXT_STRIP_VERSION = "wikitext-strip.v2"
CHUNK_VERSION = "chunk.v2"
USER_AGENT = "humanizer-pro-corpus/1.0"
ID_PREFIX = {
    "forum-post": "forum",
    "wiki-revision": "wiki",
    "public-domain": "pd",
    "news-page": "news",
    "gutenberg-work": "guten",
    "hf-news": "hfnews",
    "pep-chunk": "pep",
    "raid-generation": "raid",
    "wildchat-turn": "wildchat",
    "generated": "gen",
}
# Kinds whose sources are public-domain pointers and may publish in the manifest.
PUBLIC_SOURCE_KINDS = (
    "public-domain",
    "news-page",
    "gutenberg-work",
    "hf-news",
    "pep-chunk",
    "raid-generation",
    "wildchat-turn",
    "generated",
)
# Machine-written kinds. Their entries carry label "machine", the generating
# model, and a dev/test split; every other kind is human by provenance.
MACHINE_KINDS = ("raid-generation", "wildchat-turn", "generated")
# About a quarter of machine documents form the dev split, the only part rule
# tuning may look at. The published catch rate uses the test split.
DEV_SPLIT_HEX = "0123"


def machine_split(digest: str) -> str:
    """dev or test, from the content digest: stable, and needs no stored seed."""
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


def save_manifest(manifest: dict) -> None:
    manifest["entries"].sort(key=lambda entry: entry["id"])
    CORPUS_DIR.mkdir(exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_local_sources() -> dict:
    if LOCAL_SOURCES_PATH.exists():
        return json.loads(LOCAL_SOURCES_PATH.read_text(encoding="utf-8"))
    return {"schema": SOURCES_SCHEMA, "sources": {}}


def save_local_sources(sources: dict) -> None:
    CORPUS_DIR.mkdir(exist_ok=True)
    LOCAL_SOURCES_PATH.write_text(
        json.dumps(sources, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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


def load_local_config() -> dict:
    if LOCAL_CONFIG_PATH.exists():
        return json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_pool(kind: str, pairs: list[tuple[dict, str, dict]]) -> list[dict]:
    """Persist one pool: anonymous public entries, local sources, cache text.

    `pairs` items are (public_fields, text, source). The entry id is the kind
    prefix plus the first 12 hex chars of the content digest, so a public id
    names content without describing where it came from. Existing entries and
    cache files for the same kind are replaced (idempotent rebuild).
    """
    prefix = ID_PREFIX[kind]
    manifest = load_manifest()
    local = load_local_sources()
    for entry_id in [e["id"] for e in manifest["entries"] if e["id"].startswith(f"{prefix}-")]:
        cache_path(entry_id).unlink(missing_ok=True)
        local["sources"].pop(entry_id, None)
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
            entry["split"] = machine_split(digest)
        if kind in PUBLIC_SOURCE_KINDS:
            entry["source"] = source  # public-domain pointer; reveals nothing personal
        else:
            local["sources"][entry_id] = source
        entries.append(entry)
        write_cache(entry_id, text)
    manifest["entries"].extend(entries)
    save_manifest(manifest)
    save_local_sources(local)
    if duplicates:
        print(f"{kind}: dropped {duplicates} byte-identical duplicate document(s)")
    return entries


# ---------------------------------------------------------- text extraction


# Innermost block only: its body holds no opening tag of the same name, so
# nested quotes are removed from the inside out rather than the outer opener
# pairing with the inner closer and leaking the quoted author's words.
BBCODE_BLOCK_RE = re.compile(
    r"\[(quote|code|php|html)(?:=[^\]]*)?\](?:(?!\[\1(?:=[^\]]*)?\]).)*?\[/\1\]", re.S | re.I
)
SQL_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a"}
BBCODE_TAG_RE = re.compile(r"\[/?[a-zA-Z*][^\]]*\]")


def bbcode_strip(message: str) -> str:
    """SQL-unescape a MyBB message and strip BBCode.

    Quote and code blocks are removed outright: quoted text is another
    author's writing and code is not prose. Remaining tags are unwrapped.
    """
    # One pass over escape pairs. Chained replace() calls read the "\\n" in
    # an escaped backslash followed by "n" (C:\\new) as a newline.
    text = re.sub(r"\\(.)", lambda m: SQL_ESCAPES.get(m.group(1), m.group(1)), message, flags=re.S)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    while True:
        text, count = BBCODE_BLOCK_RE.subn(" ", text)
        if not count:
            break
    text = BBCODE_TAG_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


# ------------------------------------------------------------- forum build


# mybb_posts columns: pid,tid,replyto,fid,subject,icon,uid,username,dateline,message,...
POSTS_INSERT_RE = re.compile(r"INSERT INTO `mybb_posts`[^;]*?VALUES\s*(.*?);\r?\n", re.S)
POST_ROW_RE = re.compile(
    r"\((\d+),\s*\d+,\s*\d+,\s*\d+,\s*'(?:[^'\\]|\\.)*',\s*-?\d+,\s*(\d+),\s*"
    r"'((?:[^'\\]|\\.)*)',\s*(\d+),\s*'((?:[^'\\]|\\.)*)'"
    # Optional tail: ipaddress (quoted, hex, _binary, or NULL), includesig,
    # smilieoff, edituid, then edittime. MyBB stores the edited text in place,
    # so a post edited after the cutoff is not pre-cutoff text. A dump whose
    # rows lack these columns yields None and is counted, not guessed.
    r"(?:,\s*(?:'(?:[^'\\]|\\.)*'|_binary\s*'(?:[^'\\]|\\.)*'|0x[0-9A-Fa-f]*|NULL)"
    r",\s*-?\d+,\s*-?\d+,\s*-?\d+,\s*(\d+))?"
)


def iter_mybb_posts(sql_path: Path):
    text = sql_path.read_text(encoding="utf-8", errors="replace")
    for insert in POSTS_INSERT_RE.finditer(text):
        for row in POST_ROW_RE.finditer(insert.group(1)):
            pid, _uid, username, dateline, message, edittime = row.groups()
            yield (
                int(pid),
                username,
                int(dateline),
                message,
                int(edittime) if edittime is not None else None,
            )


def build_forum(args: argparse.Namespace) -> int:
    config = load_local_config()
    dump_dir = Path(args.dump_dir or config.get("mybb_dump_dir", ""))
    maintainer_users = set(args.maintainer_user or config.get("maintainer_users", []))
    if not dump_dir.is_dir():
        print(f"FAIL: MyBB dump directory not found: {dump_dir!r}", file=sys.stderr)
        return 3
    dumps = sorted(dump_dir.glob("*_sanitized.sql"))
    if not dumps:
        print(f"FAIL: no *_sanitized.sql files in {dump_dir}", file=sys.stderr)
        return 3
    pairs: list[tuple[dict, str, dict]] = []
    dropped = Counter()
    for sql_path in dumps:
        forum = sql_path.stem.replace("_sanitized", "")
        for pid, username, dateline, message, edittime in iter_mybb_posts(sql_path):
            if dateline >= CUTOFF_EPOCH:
                dropped["post-cutoff"] += 1
                continue
            if edittime is not None and edittime >= CUTOFF_EPOCH:
                dropped["edited-post-cutoff"] += 1
                continue
            if edittime is None:
                dropped["edittime-unknown"] += 1
            text = bbcode_strip(message)
            if word_count(text) < MIN_WORDS["chat"]:
                dropped["under-min-words"] += 1
                continue
            pairs.append(
                (
                    {
                        "register": "chat",
                        "author": "maintainer" if username in maintainer_users else "other",
                        "date": time.strftime("%Y-%m", time.gmtime(dateline)),
                        "extraction": BBCODE_STRIP_VERSION,
                    },
                    text,
                    {"dump": forum, "pid": pid},
                )
            )
    entries = save_pool("forum-post", pairs)
    by_author = Counter(entry["author"] for entry in entries)
    print(
        f"forum: {len(entries)} entries cached "
        f"({by_author['maintainer']} maintainer, {by_author['other']} other); "
        f"dropped {dropped['post-cutoff']} post-cutoff, "
        f"{dropped['edited-post-cutoff']} edited after the cutoff, "
        f"{dropped['under-min-words']} under {MIN_WORDS['chat']} words; "
        f"{dropped['edittime-unknown']} kept with no parseable edittime"
    )
    return 0


# -------------------------------------------------------------- wiki build


def api_get(api_url: str, params: dict, sleep: float) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    request = urllib.request.Request(
        f"{api_url}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    time.sleep(sleep)
    return payload


def build_wiki(args: argparse.Namespace) -> int:
    config = load_local_config()
    api_url = args.api_url or config.get("wiki_api_url")
    user = args.user or config.get("wiki_user")
    if not api_url or not user:
        print("FAIL: --api-url and --user (or build.local.json) required", file=sys.stderr)
        return 3
    # 1) Enumerate the user's pre-cutoff mainspace contributions, newest first,
    #    keeping the latest pre-cutoff revision per page.
    latest_rev_by_page: dict[str, int] = {}
    params = {
        "action": "query",
        "list": "usercontribs",
        "ucuser": user,
        "ucnamespace": "0",
        "ucstart": f"{CUTOFF}T00:00:00Z",
        "ucdir": "older",
        "uclimit": "500",
        "ucprop": "ids|title|timestamp",
    }
    while True:
        payload = api_get(api_url, params, args.sleep)
        for contrib in payload.get("query", {}).get("usercontribs", []):
            latest_rev_by_page.setdefault(contrib["title"], contrib["revid"])
        cont = payload.get("continue")
        if not cont:
            break
        params.update(cont)
    print(f"wiki: {len(latest_rev_by_page)} pages with pre-cutoff revisions by {user}")
    # 2) Batch-fetch revision content.
    revids = sorted(latest_rev_by_page.values())
    pairs: list[tuple[dict, str, dict]] = []
    dropped = Counter()
    for start in range(0, len(revids), 50):
        batch = revids[start : start + 50]
        payload = api_get(
            api_url,
            {
                "action": "query",
                "prop": "revisions",
                "revids": "|".join(str(revid) for revid in batch),
                "rvprop": "ids|timestamp|content",
                "rvslots": "main",
            },
            args.sleep,
        )
        for page in payload.get("query", {}).get("pages", {}).values():
            for rev in page.get("revisions", []):
                wikitext = rev.get("slots", {}).get("main", {}).get("*", "")
                text = wikitext_strip(wikitext)
                if word_count(text) < MIN_WORDS["wiki"]:
                    dropped["under-min-words"] += 1
                    continue
                pairs.append(
                    (
                        {
                            "register": "wiki",
                            # A page at the maintainer's last pre-cutoff
                            # revision can hold other editors' text.
                            "author": "mixed",
                            "date": rev["timestamp"][:7],
                            "extraction": WIKITEXT_STRIP_VERSION,
                        },
                        text,
                        {
                            "api": api_url,
                            "revid": rev["revid"],
                            "title": page.get("title", ""),
                        },
                    )
                )
    entries = save_pool("wiki-revision", pairs)
    print(
        f"wiki: {len(entries)} entries cached; "
        f"dropped {dropped['under-min-words']} under {MIN_WORDS['wiki']} words"
    )
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
RST_BULLET_RE = re.compile(r"^\s*(?:[-*+]|#\.|\d+\.)\s+", re.M)
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
    pairs, dropped = pep_pairs(files, commit, args.target)
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
    entries = save_pool("raid-generation", pairs)
    print(f"raid: {len(entries)} generations cached; drops: {dict(dropped)}")
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
    entries = save_pool("wildchat-turn", pairs)
    print(f"wildchat: {len(entries)} replies cached (target {args.target}); drops: {dict(dropped)}")
    return 0


# ---------------------------------------------------------- fetch / verify


REBUILD_HINT = {
    "gutenberg-work": "build-essays",
    "news-page": "build-news",
    "hf-news": "build-hf-news",
    "forum-post": "build-forum",
    "pep-chunk": "build-peps",
    "raid-generation": "build-raid",
    "wildchat-turn": "build-wildchat",
    "generated": "scripts/generate_machine.py",
}


def fetch(args: argparse.Namespace) -> int:
    """Repopulate cache: public-domain from the repo, wiki via local sources.

    Other kinds are rebuilt by their own build-* subcommand; fetch says which
    ones are missing and exits non-zero while any entry stays uncached.
    """
    manifest = load_manifest()
    local = load_local_sources()["sources"]
    missing = [entry for entry in manifest["entries"] if not cache_path(entry["id"]).exists()]
    if any(e["kind"] == "public-domain" for e in missing):
        build_pd(args)
    wiki_entries = [
        e for e in missing if e["kind"] == "wiki-revision" and e["id"] in local
    ]
    unsourced_wiki = sum(
        1 for e in missing if e["kind"] == "wiki-revision" and e["id"] not in local
    )
    if unsourced_wiki:
        print(
            f"NOTE: {unsourced_wiki} wiki entries have no locator in "
            f"{LOCAL_SOURCES_PATH.name} on this machine (the corpus is anonymous "
            "by design)."
        )
    by_kind = Counter(e["kind"] for e in missing if e["kind"] in REBUILD_HINT)
    for kind, count in sorted(by_kind.items()):
        print(f"NOTE: {count} {kind} entries missing; rebuild them with `{REBUILD_HINT[kind]}`.")
    # Batch per API endpoint: a batch must not borrow the first entry's wiki.
    by_api: dict[str, list[dict]] = {}
    for entry in wiki_entries:
        by_api.setdefault(local[entry["id"]]["api"], []).append(entry)
    for api_url, api_entries in sorted(by_api.items()):
        for start in range(0, len(api_entries), 50):
            batch = api_entries[start : start + 50]
            payload = api_get(
                api_url,
                {
                    "action": "query",
                    "prop": "revisions",
                    "revids": "|".join(str(local[e["id"]]["revid"]) for e in batch),
                    "rvprop": "ids|content",
                    "rvslots": "main",
                },
                args.sleep,
            )
            by_revid = {local[e["id"]]["revid"]: e for e in batch}
            for page in payload.get("query", {}).get("pages", {}).values():
                for rev in page.get("revisions", []):
                    entry = by_revid.get(rev["revid"])
                    if not entry:
                        continue
                    # Rebuild with the extraction the entry was published
                    # with, or its digest can never match.
                    strip = WIKITEXT_STRIPPERS.get(entry.get("extraction", ""))
                    if strip is None:
                        print(f"NOTE: {entry['id']}: unknown extraction {entry.get('extraction')!r}")
                        continue
                    write_cache(entry["id"], strip(rev.get("slots", {}).get("main", {}).get("*", "")))
    still_missing = sum(
        1 for entry in load_manifest()["entries"] if not cache_path(entry["id"]).exists()
    )
    print(
        f"fetch: attempted {len(wiki_entries)} wiki entries; "
        f"{still_missing} entries still uncached; run verify next"
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

    p_forum = sub.add_parser("build-forum", help="extract pre-cutoff MyBB posts")
    p_forum.add_argument("--dump-dir", help="directory of *_sanitized.sql dumps")
    p_forum.add_argument(
        "--maintainer-user",
        action="append",
        help="forum username belonging to the maintainer (repeatable)",
    )
    p_forum.set_defaults(func=build_forum)

    p_wiki = sub.add_parser("build-wiki", help="fetch a user's pre-cutoff revisions")
    p_wiki.add_argument("--api-url", help="MediaWiki api.php URL")
    p_wiki.add_argument("--user", help="wiki username")
    p_wiki.add_argument("--sleep", type=float, default=1.0)
    p_wiki.set_defaults(func=build_wiki)

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
