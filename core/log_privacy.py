"""
core/log_privacy.py
-------------------
Per-request log privacy, set by the Hub's request headers (they are read here and never forwarded to a provider):

* ``x-orion-log-content: hidden``   the request log keeps metadata only (time, model, status, tokens, purpose);
                                    messages, tools and the answer are replaced by a marker.
* ``x-orion-log-content: show``     the explicit opt-in: everything is logged in full, also the memory profile.
* ``x-orion-memory-profile: tokens=N; facts=1,2,3``
                                    the profile block inside the system message is replaced in the LOGGED copy by
                                    "[hafıza profili: tokens=N; facts=1,2,3]"; the provider still gets the full text.
* ``x-orion-purpose``               a short label (e.g. memory-extraction) kept in the hidden log entry.

Malformed values are ignored. Unknown ``x-orion-log-content`` values behave as absent.
"""
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

HIDDEN_MARKER = "[içerik gizli]"
PROFILE_START = "What you know about the user (a profile built from their memory"
# The block is its header line followed by "- ..." lines (the Hub appends it last in the system message).
_PROFILE_BLOCK = re.compile(r"(\n\n)?" + re.escape(PROFILE_START) + r"[^\n]*(?:\n- [^\n]*)*")
_PROFILE_VALUE = re.compile(r"^tokens=(\d{1,9}); ?facts=(\d{1,12}(?:,\d{1,12}){0,999})?$")
_PURPOSE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_KEPT_PARAMS = ("model", "stream", "temperature", "top_p", "max_tokens", "thinking")


@dataclass(frozen=True)
class LogPolicy:
    hidden: bool = False
    profile: str | None = None  # "tokens=N; facts=1,2,3" (validated)
    purpose: str | None = None


_current: ContextVar[LogPolicy | None] = ContextVar("orion_log_policy", default=None)


def policy_from_headers(headers) -> LogPolicy | None:
    """The policy of one request; None when no header asks for anything."""
    try:
        mode = (headers.get("x-orion-log-content") or "").strip().lower()
        purpose = (headers.get("x-orion-purpose") or "").strip().lower()
        purpose = purpose if _PURPOSE.match(purpose) else None
        if mode == "hidden":
            return LogPolicy(hidden=True, purpose=purpose)
        match = _PROFILE_VALUE.match((headers.get("x-orion-memory-profile") or "").strip())
        if match and mode != "show":
            return LogPolicy(profile=f"tokens={match.group(1)}; facts={match.group(2) or ''}", purpose=purpose)
    except Exception:
        pass
    return None


def set_policy(policy: LogPolicy | None) -> None:
    _current.set(policy)


def current_policy() -> LogPolicy | None:
    return _current.get()


def _cut_profile(value: Any, marker: str) -> Any:
    if isinstance(value, str):
        if PROFILE_START not in value:
            return value
        return _PROFILE_BLOCK.sub(lambda m: (m.group(1) or "") + marker, value)
    if isinstance(value, list):
        return [_cut_profile(v, marker) for v in value]
    if isinstance(value, dict):
        return {k: _cut_profile(v, marker) for k, v in value.items()}
    return value


def scrub_request(data: Any) -> Any:
    """The request as it may be logged (a dict, or its JSON string)."""
    policy = current_policy()
    if policy is None or data is None:
        return data
    try:
        as_text = isinstance(data, str)
        obj = json.loads(data) if as_text else data
        if not isinstance(obj, dict):
            return data
        if policy.hidden:
            out = {k: obj[k] for k in _KEPT_PARAMS if isinstance(obj.get(k), (str, int, float, bool))}
            out["messages"] = HIDDEN_MARKER
            out["content_hidden"] = True
            if policy.purpose:
                out["purpose"] = policy.purpose
        else:
            out = _cut_profile(obj, f"[hafıza profili: {policy.profile}]")
        return json.dumps(out, ensure_ascii=False) if as_text else out
    except Exception:
        return HIDDEN_MARKER if policy.hidden else data


def scrub_response(data: Any) -> Any:
    """The response as it may be logged: only metadata when the content is hidden."""
    policy = current_policy()
    if policy is None or not policy.hidden or data is None:
        return data
    try:
        as_text = isinstance(data, str)
        obj = json.loads(data) if as_text else data
        if not isinstance(obj, dict):
            return data
        out: dict[str, Any] = {k: obj[k] for k in ("usage", "metrics", "status") if k in obj}
        if "error" in obj:
            out["error"] = str(obj["error"])[:200]
        if "choices" in obj:
            out["choices"] = [{"message": {"role": "assistant", "content": HIDDEN_MARKER}}]
        out["content_hidden"] = True
        return json.dumps(out, ensure_ascii=False) if as_text else out
    except Exception:
        return HIDDEN_MARKER
