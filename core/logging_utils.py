"""
core/logging_utils.py
---------------------
Orion Router için güvenli, kompakt ve performansı koruyan loglama yardımcıları.
Terminale devasa prompt, mesaj içerikleri veya tool şemaları dökülmesini önler.
Hassas verileri (API anahtarları, authorization vb.) ve bilinmeyen parametreleri filtreler.
"""
import logging
import re
import json
import httpx
from starlette.exceptions import HTTPException
from typing import Any


def diagnostic_text(value: Any, limit: int = 800) -> str:
    """Keep diagnostics redacted, bounded and on one terminal line."""
    from core.secret_guard import redact

    text = re.sub(r"[\x00-\x20\x7f-\x9f]+", " ", redact(str(value))).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def is_expected_provider_error(error):
    if isinstance(error, (ValueError, HTTPException, httpx.HTTPError, TimeoutError, ConnectionError)):
        return True
    if isinstance(error, RuntimeError):
        return any(marker in str(error).lower() for marker in (
            "http error", "api error", "stream error:",
        )) or isinstance(error.__cause__ or error.__context__, (httpx.HTTPError, OSError))
    return False


def provider_error_summary(error):
    """Prefer upstream message/code over dumping the entire HTTP error body."""
    text = str(error)
    prefix, separator, body = text.partition("{")
    if separator:
        try:
            payload = json.loads(separator + body)
        except (ValueError, TypeError):
            pass
        else:
            detail = payload.get("error", payload) if isinstance(payload, dict) else None
            if isinstance(detail, dict) and detail.get("message"):
                code = detail.get("code") or detail.get("type")
                text = prefix + str(detail["message"]) + (f" (code={code})" if code else "")
    return diagnostic_text(text) or "No error message supplied"


def log_provider_failure(logger, capability, provider, model, error, log_id=None, *, unexpected=None):
    """Expected upstream rejections need a reason; bugs also need a traceback."""
    if unexpected is None:
        unexpected = isinstance(error, BaseException) and not is_expected_provider_error(error)
    level = logging.ERROR if unexpected else logging.WARNING
    logger.log(
        level,
        "%s failed | provider=%s model=%s log_id=%s | %s: %s",
        capability,
        diagnostic_text(provider), diagnostic_text(model), log_id if log_id is not None else "-",
        type(error).__name__ if isinstance(error, BaseException) else "UpstreamError",
        provider_error_summary(error),
        exc_info=(type(error), error, error.__traceback__) if unexpected else None,
    )


def log_chat_failure(logger, provider, model, error, log_id=None, *, unexpected=None):
    log_provider_failure(logger, "Chat", provider, model, error, log_id, unexpected=unexpected)


async def log_http_exception(request, exc):
    """Log HTTP rejection reasons while preserving Starlette's response contract."""
    from fastapi.exception_handlers import http_exception_handler

    cause = exc.__cause__
    from core.availability import ServiceUnavailable
    # An optional local service that is not running is a state, already logged once when it began.
    level = (logging.DEBUG if isinstance(exc, ServiceUnavailable)
             else logging.ERROR if exc.status_code >= 500 else logging.WARNING)
    logging.getLogger("service-router.http").log(
        level,
        "HTTP %s | %s %s | %s%s",
        exc.status_code, diagnostic_text(request.method), diagnostic_text(request.url.path),
        diagnostic_text(exc.detail),
        f" | cause={type(cause).__name__}: {diagnostic_text(cause) or 'No error message supplied'}" if cause else "",
    )
    return await http_exception_handler(request, exc)

# Chat isteklerinde loglanmasına izin verilen güvenli parametreler (whitelist)
SAFE_CHAT_PARAM_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "max_tokens",
    "max_completion_tokens",
    "thinking",
    "thinking_level",
    "reasoning_effort",
    "thinking_budget",
    "presence_penalty",
    "frequency_penalty",
    "repeat_penalty",
    "seed",
)

# TTS isteklerinde loglanmasına izin verilen güvenli parametreler (whitelist)
SAFE_TTS_PARAM_KEYS = (
    "speed",
    "pitch",
    "language",
    "response_format",
    "temperature",
    "tts_instruct",
    "gender",
    "age",
    "style",
    "accent",
    "dialect",
    "guidance_scale",
    "steps",
    "seed",
)


def format_chat_stream_info(
    provider: str,
    model: str,
    messages: list[dict[str, Any]] | None,
    kwargs: dict[str, Any],
) -> str:
    """INFO seviyesi için kompakt, özet log metni oluşturur.
    Mesaj içerikleri, promptlar ve tool şemaları ASLA yazdırılmaz.
    Yalnızca provider, model, mesaj sayısı, tool sayısı ve izin verilen parametreler gösterilir.
    """
    parts = [f"provider={provider}", f"model={model}"]

    if isinstance(messages, list):
        parts.append(f"messages={len(messages)}")

    tools = kwargs.get("tools")
    if isinstance(tools, list) and tools:
        tool_choice = kwargs.get("tool_choice")
        choice_str = ""
        if isinstance(tool_choice, str):
            choice_str = f" ({tool_choice})"
        elif isinstance(tool_choice, dict) and "function" in tool_choice:
            fn = tool_choice.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                choice_str = f" ({fn['name']})"
        parts.append(f"tools={len(tools)}{choice_str}")
    elif tools is not None:
        parts.append("tools=0")

    # Yalnızca güvenli allowlist parametrelerini ekle
    params: dict[str, Any] = {}
    for key in SAFE_CHAT_PARAM_KEYS:
        val = kwargs.get(key)
        if val is not None and val != "":
            params[key] = val

    if params:
        parts.append(f"params={params}")

    return "Starting chat stream: " + ", ".join(parts)


def format_chat_stream_debug(
    messages: list[dict[str, Any]] | None,
    kwargs: dict[str, Any],
) -> str:
    """DEBUG seviyesi için teknik ayrıntıları özetler.
    100.000 tokenlık promptların veya devasa tool JSON'larının terminale dökülmesini engeller.
    Rol dağılımı, karakter uzunlukları, tool isimleri ve güvenli parametre anahtarlarını gösterir.
    """
    details: list[str] = []

    if isinstance(messages, list):
        role_counts: dict[str, int] = {}
        total_chars = 0
        for m in messages:
            if isinstance(m, dict):
                r = m.get("role", "unknown")
                role_counts[r] = role_counts.get(r, 0) + 1
                c = m.get("content")
                if isinstance(c, str):
                    total_chars += len(c)
                elif isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and "text" in part:
                            total_chars += len(part.get("text", ""))
        roles_str = ", ".join(f"{k}:{v}" for k, v in role_counts.items())
        details.append(f"roles=[{roles_str}]")
        details.append(f"approx_chars={total_chars}")

    tools = kwargs.get("tools")
    if isinstance(tools, list) and tools:
        names: list[str] = []
        for t in tools:
            if isinstance(t, dict):
                fn = t.get("function")
                if isinstance(fn, dict) and fn.get("name"):
                    names.append(fn["name"])
                elif t.get("name"):
                    names.append(t["name"])
        if len(names) > 10:
            names_repr = ", ".join(names[:10]) + f", ... (+{len(names)-10} more)"
        else:
            names_repr = ", ".join(names)
        details.append(f"tool_names=[{names_repr}]")

    # Bilinen ve izin verilen kwargs anahtarlarını özetle (hassas anahtarlar hariç)
    safe_keys = [k for k in sorted(kwargs.keys()) if k in SAFE_CHAT_PARAM_KEYS or k in ("tools", "tool_choice", "stream")]
    if safe_keys:
        details.append(f"keys={safe_keys}")

    return "Chat stream debug: " + ", ".join(details)


def log_chat_stream_start(
    logger: logging.Logger,
    provider: str,
    model: str,
    messages: list[dict[str, Any]] | None,
    kwargs: dict[str, Any],
) -> None:
    """Chat akışı başlatılırken güvenli ve özet log kaydı üretir."""
    logger.info("%s", format_chat_stream_info(provider, model, messages, kwargs))
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("%s", format_chat_stream_debug(messages, kwargs))


def format_tts_kwargs_summary(kwargs: dict[str, Any]) -> dict[str, Any]:
    """TTS isteklerinde terminale basılan kwargs'ı güvenli parametrelerle sınırlandırır."""
    return {
        k: kwargs[k]
        for k in SAFE_TTS_PARAM_KEYS
        if k in kwargs and kwargs[k] is not None and kwargs[k] != ""
    }
