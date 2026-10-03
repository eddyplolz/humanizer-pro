#!/usr/bin/env python3
"""Generate the current-model machine pool for catch-rate measurement.

A maintainer tool, not part of the audit: it calls the Claude API with the
committed prompts in corpus/machine_prompts.json and stores the replies the
same way as every other pool (hash-only manifest entries, text in the
gitignored cache). It needs the official SDK (`pip install anthropic`) and an
API key; the audit CLI itself stays zero-dependency.

Labels must be exact, so two things differ from a typical app:
- No refusal fallbacks. A fallback would answer with another model and the
  entry would carry the wrong label. A refused prompt is skipped and counted.
- The entry's model is the one that served the reply (`response.model`).

Generations are not reproducible byte for byte; rerunning samples afresh. The
prompts and this script are what make the measurement repeatable.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_PATH = ROOT / "corpus" / "machine_prompts.json"
PROMPTS_SCHEMA = "humanizer-machine-prompts.v1"
DEFAULT_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5")
EXTRACTION = "generated.v1"
# Non-streaming default from the API guidance: room for adaptive thinking plus
# a few hundred words of reply, under the SDK's HTTP timeout.
DEFAULT_MAX_TOKENS = 16000

_spec = importlib.util.spec_from_file_location("corpus", Path(__file__).resolve().parent / "corpus.py")
corpus = importlib.util.module_from_spec(_spec)
sys.modules["corpus"] = corpus
_spec.loader.exec_module(corpus)


def load_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != PROMPTS_SCHEMA:
        raise ValueError(f"{path}: expected schema {PROMPTS_SCHEMA}")
    prompts = payload["prompts"]
    ids = [item["id"] for item in prompts]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: prompt ids must be unique")
    for item in prompts:
        if item["register"] not in corpus.MIN_WORDS:
            raise ValueError(f"{item['id']}: unknown register {item['register']!r}")
    return prompts


def reply_text(response) -> str:
    """Concatenated text blocks; thinking and other block types are skipped."""
    return "".join(block.text for block in response.content if block.type == "text").strip()


def generate_pairs(client, errors, prompts: list[dict], models: list[str], max_tokens: int, effort: str | None):
    """Return (pairs, counts). ``errors`` is the `anthropic` module (or a
    stand-in exposing the same exception classes)."""
    pairs: list[tuple[dict, str, dict]] = []
    counts: Counter = Counter()
    month = time.strftime("%Y-%m", time.gmtime())
    for item in prompts:
        for model in models:
            request = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": item["prompt"]}],
            }
            # Haiku 4.5 rejects the effort parameter.
            if effort and not model.startswith("claude-haiku"):
                request["output_config"] = {"effort": effort}
            try:
                response = client.messages.create(**request)
            except (errors.AuthenticationError, errors.PermissionDeniedError, errors.NotFoundError, errors.BadRequestError):
                # A configuration problem (key, model id, request shape):
                # every later call would fail the same way.
                raise
            except (errors.RateLimitError, errors.APIStatusError, errors.APIConnectionError) as error:
                # The SDK already retried 429/5xx/connection errors.
                counts["api-error"] += 1
                print(f"{item['id']} on {model}: {type(error).__name__}; skipped", flush=True)
                continue
            if response.stop_reason == "refusal":
                counts["refused"] += 1
                continue
            if response.stop_reason == "max_tokens":
                counts["truncated"] += 1
                continue
            text = reply_text(response)
            if corpus.word_count(text) < corpus.MIN_WORDS[item["register"]]:
                counts["under-min-words"] += 1
                continue
            counts["kept"] += 1
            pairs.append(
                (
                    {
                        "register": item["register"],
                        "author": "machine",
                        "model": f"anthropic:{response.model}",
                        "date": month,
                        "extraction": EXTRACTION,
                    },
                    text,
                    {"prompt_id": item["id"], "requested_model": model},
                )
            )
    return pairs, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--limit", type=int, help="Use only the first N prompts (a cheap trial run).")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; call nothing.")
    args = parser.parse_args(argv)
    prompts = load_prompts()[: args.limit]
    print(f"{len(prompts)} prompts x {len(args.models)} models = {len(prompts) * len(args.models)} requests")
    if args.dry_run:
        return 0
    try:
        import anthropic
    except ImportError:
        print("FAIL: this maintainer tool needs the official SDK: pip install anthropic", file=sys.stderr)
        return 3
    client = anthropic.Anthropic(max_retries=5)
    try:
        pairs, counts = generate_pairs(client, anthropic, prompts, args.models, args.max_tokens, args.effort)
    except anthropic.APIStatusError as error:
        print(f"FAIL: {type(error).__name__}: {error.message}; nothing saved", file=sys.stderr)
        return 1
    entries = corpus.save_pool("generated", pairs)
    print(f"generated: {len(entries)} documents cached; {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
