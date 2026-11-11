"""
core/outgoing.py
----------------
What the Router really sends to a provider, for the request log: the JSON body of the request as it leaves (to the
local TTS or LLM server, OpenAI, OpenRouter, DeepSeek, Gemini), not the Router's own summary of it.

A runner opens a recording before it hands a request to a provider (record_outgoing); every HTTP client the
providers use (core/http_client.py, the Gemini SDK's client in providers/gemini/client.py) reports each JSON body it
sends (record_httpx_request). The last one is kept: the request that was answered (a retry without an option the
provider refused comes after the first try). Headers (API keys) are never recorded, only the body.
"""
import json
from contextvars import ContextVar
from typing import Any

_current: ContextVar["OutgoingRequest | None"] = ContextVar("orion_outgoing_request", default=None)


class OutgoingRequest:
    def __init__(self) -> None:
        self.body: Any = None

    def record(self, body: Any) -> None:
        self.body = body


def record_outgoing() -> OutgoingRequest:
    """Starts recording what this request sends. Not reset afterwards: a streamed answer is read on by another task,
    and every request starts its own recording before it sends anything."""
    recording = OutgoingRequest()
    _current.set(recording)
    return recording


def record(body: Any) -> None:
    """Records a body sent some other way than through a recorded HTTP client."""
    recording = _current.get()
    if recording is not None:
        recording.record(body)


async def record_httpx_request(request) -> None:
    """httpx event hook: the JSON body of a POST, as it is sent."""
    recording = _current.get()
    if recording is None or request.method != "POST":
        return
    if "json" not in request.headers.get("content-type", "").lower():
        return
    try:
        recording.record(json.loads(request.content))
    except Exception:
        pass
