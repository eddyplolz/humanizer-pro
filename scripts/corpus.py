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
MIN_WORDS = {"chat": 50, "wiki": 150, "essay": 150}
BBCODE_STRIP_VERSION = "bbcode-strip.v1"
WIKITEXT_STRIP_VERSION = "wikitext-strip.v1"
USER_AGENT = "humanizer-pro-corpus/1.0"
ID_PREFIX = {"forum-post": "forum", "wiki-revision": "wiki", "public-domain": "pd"}


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
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_local_sources() -> dict:
    if LOCAL_SOURCES_PATH.exists():
        return json.loads(LOCAL_SOURCES_PATH.read_text(encoding="utf-8"))
    return {"schema": SOURCES_SCHEMA, "sources": {}}


def save_local_sources(sources: dict) -> None:
    CORPUS_DIR.mkdir(exist_ok=True)
    LOCAL_SOURCES_PATH.write_text(
        json.dumps(sources, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_cache(entry_id: str, text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{entry_id}.txt").write_text(text, encoding="utf-8")


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
        if kind == "public-domain":
            entry["source"] = source  # in-repo pointer; reveals nothing
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

    p_fetch = sub.add_parser("fetch", help="repopulate cache from the manifest")
    p_fetch.add_argument("--sleep", type=float, default=1.0)
    p_fetch.set_defaults(func=fetch)

    p_verify = sub.add_parser("verify", help="check cache against manifest hashes")
    p_verify.set_defaults(func=verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
