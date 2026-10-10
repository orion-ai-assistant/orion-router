"""
core/logging_utils.py
---------------------
Orion Router için güvenli, kompakt ve performansı koruyan loglama yardımcıları.
Terminale devasa prompt, mesaj içerikleri veya tool şemaları dökülmesini önler.
Hassas verileri (API anahtarları, authorization vb.) ve bilinmeyen parametreleri filtreler.
"""
import logging
from typing import Any

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
