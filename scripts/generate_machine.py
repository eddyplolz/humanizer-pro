#!/usr/bin/env python3
"""Generate the current-model machine pool for catch-rate measurement.

A maintainer tool, not part of the audit: it sends the committed prompts in
corpus/machine_prompts.json to a model API and stores the replies the same way
as every other pool (hash-only manifest entries, text in the gitignored
cache). The audit CLI itself stays zero-dependency and never touches the
network; this script is not shipped in the package.

Two providers:
- `--provider anthropic` (the default) calls the Claude API through the
  official SDK (`pip install anthropic`) with an Anthropic API key.
- `--provider openrouter` calls OpenRouter's chat completions endpoint with
  the standard library only and `OPENROUTER_API_KEY`. Entries are labelled
  `openrouter:<model>`. `--effort` is not supported on this route. Before any
  request, and with `--dry-run`, it prints an estimated cost and a ceiling
  from OpenRouter's public price list.

Labels must be exact, so two things differ from a typical app:
- No refusal or model fallbacks. A fallback would answer with another model
  and the entry would carry the wrong label. A refused prompt is skipped and
  counted. OpenRouter requests never carry `models`, `fallbacks`, or `route`.
- The entry's model is the one that served the reply, as the response names
  it.

Generations are not reproducible byte for byte; rerunning samples afresh. The
prompts and this script are what make the measurement repeatable.
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_PATH = ROOT / "corpus" / "machine_prompts.json"
PROMPTS_SCHEMA = "humanizer-machine-prompts.v1"
DEFAULT_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5")
EXTRACTION = "generated.v1"
# Non-streaming default from the API guidance: room for adaptive thinking plus
# a few hundred words of reply, under the SDK's HTTP timeout.
DEFAULT_MAX_TOKENS = 16000

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_DEFAULT_MODELS = (
    "anthropic/claude-opus-5.5",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-haiku-5.5",
    "anthropic/claude-fable-5.2",
)
OPENROUTER_MAX_TOKENS = 4096
OPENROUTER_RETRIES = 5
OPENROUTER_TIMEOUT = 300
# OpenAI-style finish reasons mapped onto the stop reasons generate_pairs reads.
FINISH_REASONS = {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}
# Spend estimate: about four characters per prompt token plus message overhead,
# and a typical reply of a thousand tokens. The ceiling assumes every reply
# runs to max_tokens.
CHARS_PER_TOKEN = 4
PROMPT_OVERHEAD_TOKENS = 20
TYPICAL_REPLY_TOKENS = 1000

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


def generate_pairs(
    client,
    errors,
    prompts: list[dict],
    models: list[str],
    max_tokens: int,
    effort: str | None,
    label_prefix: str = "anthropic",
    done: frozenset = frozenset(),
    record=None,
):
    """Return (pairs, counts). ``errors`` is the `anthropic` module (or a
    stand-in exposing the same exception classes, such as OpenRouterErrors).
    Each entry's model is labelled ``<label_prefix>:<served model>``.

    ``done`` holds (prompt id, model) pairs a checkpoint already settled;
    they are not sent again. ``record(prompt_id, model, outcome, pair)`` is
    called for every settled request (kept, refused, truncated, too short) so
    a caller can checkpoint it. Transient API errors are not settled: a
    re-run asks again."""
    pairs: list[tuple[dict, str, dict]] = []
    counts: Counter = Counter()
    month = time.strftime("%Y-%m", time.gmtime())
    for item in prompts:
        for model in models:
            if (item["id"], model) in done:
                continue
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
                # A configuration problem (key, credits, model id, request
                # shape): every later call would fail the same way.
                raise
            except (errors.RateLimitError, errors.APIStatusError, errors.APIConnectionError) as error:
                # The client already retried 429/5xx/connection errors.
                counts["api-error"] += 1
                print(f"{item['id']} on {model}: {type(error).__name__}; skipped", flush=True)
                continue
            if response.stop_reason == "refusal":
                outcome = "refused"
            elif response.stop_reason == "max_tokens":
                outcome = "truncated"
            else:
                text = reply_text(response)
                too_short = corpus.word_count(text) < corpus.MIN_WORDS[item["register"]]
                outcome = "under-min-words" if too_short else "kept"
            counts[outcome] += 1
            if outcome != "kept":
                if record:
                    record(item["id"], model, outcome, None)
                continue
            pair = (
                {
                    "register": item["register"],
                    "author": "machine",
                    "model": f"{label_prefix}:{response.model}",
                    "date": month,
                    "extraction": EXTRACTION,
                },
                text,
                {"prompt_id": item["id"], "requested_model": model},
            )
            pairs.append(pair)
            if record:
                record(item["id"], model, outcome, pair)
    return pairs, counts


def checkpoint_path(provider: str) -> Path:
    """Where a full run settles each paid reply as it arrives (gitignored)."""
    return corpus.CACHE_DIR / f"generate-{provider}.checkpoint.jsonl"


def load_checkpoint(path: Path) -> tuple[list, Counter, frozenset]:
    """Return (pairs, counts, done) from an earlier run's checkpoint."""
    pairs: list = []
    counts: Counter = Counter()
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done.add((row["prompt_id"], row["model"]))
            counts[row["outcome"]] += 1
            if row["pair"]:
                pairs.append(tuple(row["pair"]))
    return pairs, counts, frozenset(done)


def checkpoint_writer(path: Path):
    def record(prompt_id: str, model: str, outcome: str, pair) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"prompt_id": prompt_id, "model": model, "outcome": outcome, "pair": pair}
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    return record


# ---------------------------------------------------------------- openrouter


class OpenRouterErrors:
    """The exception names generate_pairs catches, raised by OpenRouterClient."""

    class APIStatusError(Exception):
        def __init__(self, message: str, status_code: int | None = None):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    class BadRequestError(APIStatusError):
        pass

    class AuthenticationError(APIStatusError):
        pass

    class PermissionDeniedError(APIStatusError):
        pass

    class NotFoundError(APIStatusError):
        pass

    class RateLimitError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.message = message


# 402 means the account has no credits: a configuration problem like a bad
# key, so it stops the run instead of failing every later request.
_STATUS_ERRORS = {
    400: OpenRouterErrors.BadRequestError,
    401: OpenRouterErrors.AuthenticationError,
    402: OpenRouterErrors.PermissionDeniedError,
    403: OpenRouterErrors.PermissionDeniedError,
    404: OpenRouterErrors.NotFoundError,
    429: OpenRouterErrors.RateLimitError,
}


def _status_error(status: int, detail: str) -> Exception:
    cls = _STATUS_ERRORS.get(status, OpenRouterErrors.APIStatusError)
    return cls(f"HTTP {status}: {detail}", status)


def _error_detail(raw: bytes) -> str:
    try:
        error = json.loads(raw.decode("utf-8")).get("error") or {}
        return str(error.get("message") or "no message")
    except (ValueError, AttributeError):
        return "no message"


def parse_completion(payload):
    """Turn a chat completions body into the response shape generate_pairs reads."""
    if not isinstance(payload, dict):
        raise OpenRouterErrors.APIStatusError("response is not a JSON object")
    if payload.get("error"):
        error = payload["error"]
        detail = error.get("message") if isinstance(error, dict) else error
        raise OpenRouterErrors.APIStatusError(f"error in response body: {detail}")
    served = payload.get("model")
    choices = payload.get("choices") or []
    if not served or not choices:
        # Without the served model the label would be a guess.
        raise OpenRouterErrors.APIStatusError("response names no served model or has no choices")
    choice = choices[0]
    finish = choice.get("finish_reason")
    if choice.get("native_finish_reason") == "refusal":
        stop_reason = "refusal"
    elif finish in FINISH_REASONS:
        stop_reason = FINISH_REASONS[finish]
    else:
        raise OpenRouterErrors.APIStatusError(f"unexpected finish_reason {finish!r}")
    text = ((choice.get("message") or {}).get("content") or "").strip()
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        model=served,
    )


def _retryable(error: Exception) -> bool:
    if isinstance(error, (OpenRouterErrors.RateLimitError, OpenRouterErrors.APIConnectionError)):
        return True
    status = getattr(error, "status_code", None)
    return status is not None and status >= 500


class OpenRouterClient:
    """Stand-in for `anthropic.Anthropic` that generate_pairs can drive:
    ``client.messages.create(**request)`` posts one chat completion."""

    def __init__(self, api_key: str, sleep=time.sleep, retries: int = OPENROUTER_RETRIES):
        self._api_key = api_key
        self._sleep = sleep
        self._retries = retries
        self.messages = self

    def create(self, *, model: str, max_tokens: int, messages: list[dict]):
        # Only these three keys: no `models`, `fallbacks`, or `route`, so the
        # reply always comes from the model that was asked for.
        body = {"model": model, "max_tokens": max_tokens, "messages": messages}
        attempt = 0
        while True:
            try:
                return parse_completion(self._post(body))
            except (OpenRouterErrors.APIStatusError, OpenRouterErrors.APIConnectionError) as error:
                if not _retryable(error) or attempt >= self._retries:
                    raise
            self._sleep(2**attempt)
            attempt += 1

    def _post(self, body: dict):
        request = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": corpus.USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=OPENROUTER_TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise _status_error(error.code, _error_detail(error.read() or b"")) from None
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            raise OpenRouterErrors.APIConnectionError(f"{type(error).__name__}: {error}") from None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise OpenRouterErrors.APIStatusError("response is not JSON") from None


def fetch_openrouter_prices() -> dict[str, tuple[float, float]]:
    """Model id to (prompt, completion) USD per token, from the public list."""
    request = urllib.request.Request(OPENROUTER_MODELS_URL, headers={"User-Agent": corpus.USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    prices = {}
    for model in payload["data"]:
        pricing = model.get("pricing") or {}
        try:
            prices[model["id"]] = (float(pricing["prompt"]), float(pricing["completion"]))
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def estimate_cost(prompts: list[dict], models: list[str], max_tokens: int, prices: dict) -> tuple[float, float]:
    """Return (estimate, ceiling) in USD. Raises KeyError naming a model
    with no fixed price."""
    estimate = ceiling = 0.0
    for model in models:
        prompt_price, completion_price = prices.get(model, (-1.0, -1.0))
        if prompt_price < 0 or completion_price < 0:
            raise KeyError(model)
        for item in prompts:
            prompt_cost = (len(item["prompt"]) / CHARS_PER_TOKEN + PROMPT_OVERHEAD_TOKENS) * prompt_price
            estimate += prompt_cost + min(TYPICAL_REPLY_TOKENS, max_tokens) * completion_price
            ceiling += prompt_cost + max_tokens * completion_price
    return estimate, ceiling


def print_openrouter_estimate(prompts: list[dict], models: list[str], max_tokens: int) -> int:
    """Print the spend estimate; return 0, or the exit code of a failure."""
    try:
        prices = fetch_openrouter_prices()
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError, KeyError) as error:
        print(f"FAIL: could not read OpenRouter prices: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    try:
        estimate, ceiling = estimate_cost(prompts, models, max_tokens, prices)
    except KeyError as error:
        print(f"FAIL: OpenRouter lists no fixed price for model {error.args[0]!r}", file=sys.stderr)
        return 2
    print(
        f"estimated cost: ${estimate:.2f} (about {TYPICAL_REPLY_TOKENS} reply tokens each); "
        f"ceiling: ${ceiling:.2f} (every reply at max_tokens={max_tokens})"
    )
    return 0


# ----------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=["anthropic", "openrouter"], default="anthropic")
    parser.add_argument(
        "--models",
        nargs="+",
        help=f"Default: {' '.join(DEFAULT_MODELS)} (anthropic); {' '.join(OPENROUTER_DEFAULT_MODELS)} (openrouter).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Use only the first N prompts: a trial run that reports counts and saves nothing.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help=f"Default: {DEFAULT_MAX_TOKENS} (anthropic); {OPENROUTER_MAX_TOKENS} (openrouter).",
    )
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; send no completion request.")
    args = parser.parse_args(argv)
    openrouter = args.provider == "openrouter"
    if openrouter and args.effort:
        parser.error("--effort is not supported with --provider openrouter")
    models = args.models or list(OPENROUTER_DEFAULT_MODELS if openrouter else DEFAULT_MODELS)
    max_tokens = args.max_tokens or (OPENROUTER_MAX_TOKENS if openrouter else DEFAULT_MAX_TOKENS)
    prompts = load_prompts()[: args.limit]
    print(f"{len(prompts)} prompts x {len(models)} models = {len(prompts) * len(models)} requests")
    if openrouter:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not args.dry_run and not api_key:
            print("FAIL: set the OPENROUTER_API_KEY environment variable", file=sys.stderr)
            return 3
        status = print_openrouter_estimate(prompts, models, max_tokens)
        if status or args.dry_run:
            return status
        errors = OpenRouterErrors
        client = OpenRouterClient(api_key)
    else:
        if args.dry_run:
            return 0
        try:
            import anthropic
        except ImportError:
            print("FAIL: this maintainer tool needs the official SDK: pip install anthropic", file=sys.stderr)
            return 3
        errors = anthropic
        client = anthropic.Anthropic(max_retries=5)
    if args.limit is not None:
        # Saving replaces the whole pool, which costs money to rebuild.
        try:
            _pairs, counts = generate_pairs(client, errors, prompts, models, max_tokens, args.effort, args.provider)
        except errors.APIStatusError as error:
            print(f"FAIL: {type(error).__name__}: {getattr(error, 'message', error)}", file=sys.stderr)
            return 1
        print(f"trial run: {dict(counts)}; the generated pool was not changed")
        return 0
    # A full run settles each paid reply in a checkpoint as it arrives, so a
    # budget cap or crash mid-run loses nothing: the same command resumes.
    checkpoint = checkpoint_path(args.provider)
    pairs, counts, done = load_checkpoint(checkpoint)
    if done:
        print(f"resuming: {len(done)} requests already settled in {checkpoint.name}")
    try:
        new_pairs, new_counts = generate_pairs(
            client, errors, prompts, models, max_tokens, args.effort, args.provider,
            done=done, record=checkpoint_writer(checkpoint),
        )
    except errors.APIStatusError as error:
        _p, _c, settled = load_checkpoint(checkpoint)
        print(
            f"FAIL: {type(error).__name__}: {getattr(error, 'message', error)}; {len(settled)} results kept in "
            f"{checkpoint}; fix the cause and re-run the same command to resume",
            file=sys.stderr,
        )
        return 1
    pairs += new_pairs
    counts.update(new_counts)
    if not pairs:
        print(f"FAIL: no documents generated ({dict(counts)}); the existing pool was kept", file=sys.stderr)
        return 1
    entries = corpus.save_pool("generated", pairs)
    checkpoint.unlink(missing_ok=True)
    print(f"generated: {len(entries)} documents cached; {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
