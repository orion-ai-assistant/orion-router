"""
core/log_privacy.py
-------------------
Log labels from the Hub's request headers (read here, never forwarded to a provider). NOTHING is hidden or replaced:
the request log always keeps the full request text (messages, tools, the memory profile block) and the full answer.

* ``x-orion-memory-profile: tokens=N; facts=1,2,3``  only an extra label on the log entry ("hafıza profili: N token").
* ``x-orion-purpose``                                only an extra label ("amaç: hafıza çıkarımı").
* ``x-orion-log-content``                            no longer has any effect (content is always shown).

The labels are added to the LOGGED copy of the request as ``orion_log`` (a dict with ``etiketler`` plus the raw
``memory_profile`` / ``purpose`` values). Malformed values are ignored.
"""
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

_PROFILE_VALUE = re.compile(r"^tokens=(\d{1,9}); ?facts=(\d{1,12}(?:,\d{1,12}){0,999})?$")
_PURPOSE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_PURPOSE_LABELS = {"memory-extraction": "hafıza çıkarımı"}


@dataclass(frozen=True)
class LogPolicy:
    profile: str | None = None  # "tokens=N; facts=1,2,3" (validated)
    purpose: str | None = None


_current: ContextVar[LogPolicy | None] = ContextVar("orion_log_policy", default=None)


def policy_from_headers(headers) -> LogPolicy | None:
    """The labels of one request; None when no header carries one."""
    try:
        purpose = (headers.get("x-orion-purpose") or "").strip().lower()
        purpose = purpose if _PURPOSE.match(purpose) else None
        match = _PROFILE_VALUE.match((headers.get("x-orion-memory-profile") or "").strip())
        profile = f"tokens={match.group(1)}; facts={match.group(2) or ''}" if match else None
        if profile or purpose:
            return LogPolicy(profile=profile, purpose=purpose)
    except Exception:
        pass
    return None


def set_policy(policy: LogPolicy | None) -> None:
    _current.set(policy)


def current_policy() -> LogPolicy | None:
    return _current.get()


def scrub_request(data: Any) -> Any:
    """The request as logged: content unchanged plus the extra ``orion_log`` label (a dict, or its JSON string)."""
    policy = current_policy()
    if policy is None or data is None:
        return data
    try:
        as_text = isinstance(data, str)
        obj = json.loads(data) if as_text else data
        if not isinstance(obj, dict):
            return data
        labels: list[str] = []
        meta: dict[str, Any] = {}
        if policy.profile:
            tokens = policy.profile.split(";")[0].removeprefix("tokens=")
            labels.append(f"hafıza profili: {tokens} token")
            meta["memory_profile"] = policy.profile
        if policy.purpose:
            labels.append(f"amaç: {_PURPOSE_LABELS.get(policy.purpose, policy.purpose)}")
            meta["purpose"] = policy.purpose
        out = {**obj, "orion_log": {"etiketler": labels, **meta}}
        return json.dumps(out, ensure_ascii=False) if as_text else out
    except Exception:
        return data
