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
  fetch         repopulate the cache (public-domain always; others need
                the maintainer's sources.local.json)
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
import re
import sys
import time
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
MIN_WORDS = {"chat": 50, "wiki": 150, "essay": 150, "news": 200}
BBCODE_STRIP_VERSION = "bbcode-strip.v1"
WIKITEXT_STRIP_VERSION = "wikitext-strip.v1"
USER_AGENT = "humanizer-pro-corpus/1.0"
ID_PREFIX = {
    "forum-post": "forum",
    "wiki-revision": "wiki",
    "public-domain": "pd",
    "news-page": "news",
    "gutenberg-work": "guten",
    "hf-news": "hfnews",
}
# Kinds whose sources are public-domain pointers and may publish in the manifest.
PUBLIC_SOURCE_KINDS = ("public-domain", "news-page", "gutenberg-work", "hf-news")


# ---------------------------------------------------------------- utilities


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9''-]+", text))


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


def write_cache(entry_id: str, text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{entry_id}.txt").write_text(text, encoding="utf-8", newline="\n")


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
        (CACHE_DIR / f"{entry_id}.txt").unlink(missing_ok=True)
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
            "label": "human",
            "words": word_count(text),
            "sha256": digest,
            **public_fields,
        }
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


BBCODE_BLOCK_RE = re.compile(
    r"\[(quote|code|php|html)(?:=[^\]]*)?\].*?\[/\1\]", re.S | re.I
)
BBCODE_TAG_RE = re.compile(r"\[/?[a-zA-Z*][^\]]*\]")


def bbcode_strip(message: str) -> str:
    """SQL-unescape a MyBB message and strip BBCode.

    Quote and code blocks are removed outright: quoted text is another
    author's writing and code is not prose. Remaining tags are unwrapped.
    """
    text = message.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    text = text.replace("\\\"", '"').replace("\\'", "'").replace("\\\\", "\\")
    text = BBCODE_BLOCK_RE.sub(" ", text)
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


def wikitext_strip(wikitext: str) -> str:
    """Reduce wikitext to plain prose so markup never counts as a tell."""
    text = wikitext
    for regex in WIKI_DROP_RES:
        text = regex.sub(" ", text)
    for _ in range(4):  # nested templates, innermost first
        text, n = TEMPLATE_RE.subn(" ", text)
        if not n:
            break
    text = WIKILINK_PIPED_RE.sub(r"\1", text)
    text = WIKILINK_RE.sub(r"\1", text)
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
)


def iter_mybb_posts(sql_path: Path):
    text = sql_path.read_text(encoding="utf-8", errors="replace")
    for insert in POSTS_INSERT_RE.finditer(text):
        for row in POST_ROW_RE.finditer(insert.group(1)):
            pid, _uid, username, dateline, message = row.groups()
            yield int(pid), username, int(dateline), message


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
        for pid, username, dateline, message in iter_mybb_posts(sql_path):
            if dateline >= CUTOFF_EPOCH:
                dropped["post-cutoff"] += 1
                continue
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
        f"{dropped['under-min-words']} under {MIN_WORDS['chat']} words"
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
                            "author": "maintainer",
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
    text = PD_SOURCE.read_text(encoding="utf-8")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        current.append(paragraph)
        current_words += word_count(paragraph)
        if current_words >= PD_CHUNK_WORDS:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
    if current and current_words >= MIN_WORDS["essay"]:
        chunks.append("\n\n".join(current))
    pairs = [
        (
            {
                "register": "essay",
                "author": "public-domain",
                "date": "1918",
                "extraction": "chunk.v1",
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
OCR_CLEAN_VERSION = "ocr-chunk.v2"


def api_get_with_retry(url: str, params: dict, sleep: float, attempts: int = 5) -> dict:
    """loc.gov JSON with backoff: the API 503s hard on bursts, for minutes."""
    for attempt in range(1, attempts + 1):
        try:
            return api_get(url, params, sleep)
        except urllib.error.HTTPError as error:
            if error.code in (429, 503) and attempt < attempts:
                wait = 90 * attempt
                print(f"rate-limited ({error.code}); backing off {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def ocr_clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def alpha_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    alpha = sum(1 for token in tokens if re.fullmatch(r"[A-Za-z''-]+[.,;:!?\"')]*", token))
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
            "rows": str(args.issues),
            "page": "1",
            "output": "json",
        }
    )
    payload = json.loads(fetch_text(search_url, args.sleep))
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
            raw = fetch_text(url, args.sleep)
        except (urllib.error.HTTPError, urllib.error.URLError):
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
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
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


def fetch_text(url: str, sleep: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read().decode("utf-8", errors="replace")
    time.sleep(sleep)
    # Normalize newlines so cached bytes hash identically across platforms.
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def gutenberg_chunks(raw: str) -> list[str]:
    body = START_MARKER_RE.split(raw, maxsplit=1)[-1]
    body = END_MARKER_RE.sub("", body)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks, current, current_words = [], [], 0
    for paragraph in paragraphs:
        current.append(paragraph)
        current_words += word_count(paragraph)
        if current_words >= PD_CHUNK_WORDS:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
    if current and current_words >= MIN_WORDS["essay"]:
        chunks.append("\n\n".join(current))
    return chunks


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
                        "extraction": "chunk.v1",
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


# ---------------------------------------------------------- fetch / verify


def fetch(args: argparse.Namespace) -> int:
    """Repopulate cache: public-domain from the repo, others via local sources."""
    manifest = load_manifest()
    local = load_local_sources()["sources"]
    missing = [
        entry
        for entry in manifest["entries"]
        if not (CACHE_DIR / f"{entry['id']}.txt").exists()
    ]
    if any(e["kind"] == "public-domain" for e in missing):
        build_pd(args)
    wiki_entries = [
        e for e in missing if e["kind"] == "wiki-revision" and e["id"] in local
    ]
    unsourced = [
        e
        for e in missing
        if e["kind"] != "public-domain" and e["id"] not in local
    ]
    if unsourced:
        print(
            f"NOTE: {len(unsourced)} entries have no locator in "
            f"{LOCAL_SOURCES_PATH.name} on this machine (the corpus is anonymous "
            "by design); rebuild them with the build-* subcommands where the "
            "sources are available."
        )
    for start in range(0, len(wiki_entries), 50):
        batch = wiki_entries[start : start + 50]
        payload = api_get(
            local[batch[0]["id"]]["api"],
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
                if entry:
                    write_cache(
                        entry["id"],
                        wikitext_strip(rev.get("slots", {}).get("main", {}).get("*", "")),
                    )
    print(f"fetch: attempted {len(wiki_entries)} wiki entries; run verify next")
    return 0


def verify(_args: argparse.Namespace) -> int:
    manifest = load_manifest()
    missing, mismatched, ok = [], [], 0
    for entry in manifest["entries"]:
        path = CACHE_DIR / f"{entry['id']}.txt"
        if not path.exists():
            missing.append(entry["id"])
        elif sha256_text(path.read_text(encoding="utf-8")) != entry["sha256"]:
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

    p_fetch = sub.add_parser("fetch", help="repopulate cache from the manifest")
    p_fetch.add_argument("--sleep", type=float, default=1.0)
    p_fetch.set_defaults(func=fetch)

    p_verify = sub.add_parser("verify", help="check cache against manifest hashes")
    p_verify.set_defaults(func=verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
