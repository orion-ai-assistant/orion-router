"""Context length (tokens) of chat models, exposed by the model catalog as `context_length`.

Sources, in order: a per-model override in default_config.context_length, then
- openrouter: the `context_length` of OpenRouter's own model list (cached with the modality list),
- local: the llama server's configured n_ctx (/props), else the model's trained length (/v1/models),
- other providers: `context_length` in the bundled providers/*/models.json.
Unknown -> None. Everything is cached; callers never trigger a call per request.
"""
import time

from core.config import LLM_HOST, LLM_PORT
from core.http_client import get_http_client

_LOCAL_TTL = 60.0
_local_cache: tuple[float, int | None] = (0.0, None)


def _positive_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


async def local_context_length() -> int | None:
    global _local_cache
    now = time.time()
    if now - _local_cache[0] < _LOCAL_TTL:
        return _local_cache[1]
    found = None
    try:
        client = get_http_client()
        base = f"http://{LLM_HOST}:{LLM_PORT}"
        res = await client.get(f"{base}/props", timeout=2.0)
        if res.status_code == 200:
            settings = (res.json().get("default_generation_settings") or {})
            found = _positive_int(settings.get("n_ctx"))
        if found is None:
            res = await client.get(f"{base}/v1/models", timeout=2.0)
            if res.status_code == 200:
                for item in res.json().get("data", []):
                    found = _positive_int((item.get("meta") or {}).get("n_ctx_train"))
                    if found:
                        break
    except Exception:
        found = None
    _local_cache = (now, found)
    return found


async def resolve_context_length(item: dict, catalog_model: dict | None) -> int | None:
    """item is a router_models row (name, provider, capability, default_config)."""
    if item.get("capability") != "chat":
        return None
    override = _positive_int((item.get("default_config") or {}).get("context_length"))
    if override:
        return override
    provider = item.get("provider")
    if provider == "openrouter":
        from providers.openrouter.chat import openrouter_context_length
        return await openrouter_context_length(item.get("name"))
    if provider == "local":
        return await local_context_length()
    return _positive_int((catalog_model or {}).get("context_length"))
