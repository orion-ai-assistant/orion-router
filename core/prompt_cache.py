"""Provider-neutral prompt caching: request hints, usage normalization and billing.

Prompt caching lets a provider reuse the work it already did for the start of a prompt, so a
conversation that resends its history pays the cheap "cached input" rate for everything it sent
before and the normal rate only for what is new.  Providers differ in how they expose it:

* automatic, nothing to send (Gemini 2.5+, DeepSeek, OpenAI): the prefix of the prompt only has to
  stay byte-identical between requests; hits show up in the usage block;
* routing hints (OpenAI ``prompt_cache_key``, OpenRouter ``session_id``): keep a conversation on
  the machine / upstream provider that holds its cache;
* explicit markers (Anthropic ``cache_control``).

Everything provider-neutral lives here.  A provider only adapts to its own API:

* request side: override ``BaseChat.apply_cache`` (see providers/base.py) to add its parameters;
* response side: yield ``{"internal_usage": usage}`` with ``prompt_tokens`` counting *all* prompt
  tokens (cached ones included) and the cached share in one of the shapes ``extract_cache_usage``
  understands, preferably OpenAI's ``prompt_tokens_details.cached_tokens``.  ChatRunner then
  normalizes the block, so a new provider needs no billing code.

Prices are USD per one million tokens, like the rest of the catalog.  ``cache_read`` and
``cache_write`` fall back to ``input`` when unset, which bills cached tokens exactly as before
this feature existed.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping

# Fields a client may use to name a conversation.  ``prompt_cache_key`` is OpenAI's name,
# ``session_id`` OpenRouter's; the Router accepts either (or the headers) and sends each provider
# the form it understands.
CACHE_KEY_FIELDS = ("prompt_cache_key", "session_id")
CACHE_KEY_HEADERS = ("x-orion-session", "x-session-id")


@dataclass(frozen=True)
class CacheRequest:
    """What a chat request tells providers about caching."""

    key: str | None = None

    @classmethod
    def from_kwargs(cls, kwargs: Mapping[str, Any]) -> "CacheRequest":
        key = kwargs.get("cache_key")
        return cls(key if isinstance(key, str) and key else None)


def derive_cache_key(body: Mapping[str, Any], headers: Mapping[str, str], scope: str | None) -> str | None:
    """Opaque per-conversation key for a request, or None when the client named no conversation.

    The raw value is hashed together with the caller's virtual key id: provider-side keys then
    never expose chat ids, and two callers using the same chat id cannot share a cache.
    """
    raw = next(
        (str(value).strip() for value in (
            *(body.get(field) for field in CACHE_KEY_FIELDS),
            *(headers.get(name) for name in CACHE_KEY_HEADERS),
        ) if value not in (None, "") and str(value).strip()),
        None,
    )
    if raw is None:
        return None
    return hashlib.sha256(f"{scope or ''}\0{raw}".encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class CacheUsage:
    """Prompt tokens a provider served from its cache / wrote into a new cache entry."""

    read_tokens: int = 0
    write_tokens: int = 0


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value) if math.isfinite(value) and value > 0 else 0


def _details(usage: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    details = usage.get(name)
    return details if isinstance(details, Mapping) else {}


def extract_cache_usage(usage: Mapping[str, Any] | None) -> CacheUsage:
    """Read cache hits out of any usage shape a provider reports (see the module docstring)."""
    if not usage:
        return CacheUsage()
    prompt = _count(usage.get("prompt_tokens"))
    chat, responses = _details(usage, "prompt_tokens_details"), _details(usage, "input_tokens_details")
    read = max(
        _count(chat.get("cached_tokens")),
        _count(responses.get("cached_tokens")),
        _count(usage.get("cached_tokens")),
        _count(usage.get("prompt_cache_hit_tokens")),  # DeepSeek
        _count(usage.get("cached_content_token_count")),  # Gemini
    )
    write = max(
        _count(chat.get("cache_write_tokens")),
        _count(responses.get("cache_write_tokens")),
        _count(usage.get("cache_write_tokens")),
    )
    if prompt:  # never more cached tokens than prompt tokens
        read = min(read, prompt)
        write = min(write, prompt - read)
    return CacheUsage(read, write)


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return ``usage`` with its cache share in OpenAI's ``prompt_tokens_details`` form."""
    if not isinstance(usage, dict):
        return usage
    cache = extract_cache_usage(usage)
    if cache.read_tokens or cache.write_tokens:
        details = dict(_details(usage, "prompt_tokens_details"))
        details["cached_tokens"] = cache.read_tokens
        if cache.write_tokens:
            details["cache_write_tokens"] = cache.write_tokens
        usage["prompt_tokens_details"] = details
    return usage


@dataclass(frozen=True)
class PromptCost:
    cost: float  # USD; rates that are unknown count as zero (see ``known``)
    known: bool  # False when some prompt token had no price
    saved: float  # USD saved against billing every prompt token at the full input rate


def prompt_cost(prompt_tokens: int | None, cache: CacheUsage, prices: Mapping[str, float | None]) -> PromptCost:
    """Cost of a prompt: fresh tokens at ``input``, cache hits at ``cache_read``, writes at ``cache_write``."""
    prompt = _count(prompt_tokens)
    read = min(cache.read_tokens, prompt)
    write = min(cache.write_tokens, prompt - read)
    input_rate = prices.get("input")
    read_rate = prices.get("cache_read")
    write_rate = prices.get("cache_write")
    parts = (
        (prompt - read - write, input_rate),
        (read, input_rate if read_rate is None else read_rate),
        (write, input_rate if write_rate is None else write_rate),
    )
    known = all(rate is not None or not count for count, rate in parts)
    cost = sum(count * (rate or 0.0) for count, rate in parts) / 1_000_000
    saved = prompt * (input_rate or 0.0) / 1_000_000 - cost if input_rate is not None else 0.0
    return PromptCost(cost, known, saved)
