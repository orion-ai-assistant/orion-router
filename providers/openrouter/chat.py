"""
providers/openrouter/chat.py
----------------------------
OpenRouter API streaming chat provider.
reasoning (thinking), include_reasoning ve multimodal (video/görsel/ses) desteklidir.
"""
import json
import logging
import time
import httpx
from typing import AsyncGenerator, Any

from providers.base import BaseChat

from core.thinking import ThinkingConfig
from core.http_client import get_http_client

_BASE_URL = "https://openrouter.ai"
logger = logging.getLogger("service-router.openrouter")

# OpenRouter modellerinin girdi modaliteleri için önbellek
_MODEL_CATALOG_CACHE: dict[str, set[str]] = {}
_MODEL_CATALOG_LAST_FETCH: float = 0.0
_MODEL_CATALOG_TTL: float = 3600.0  # 1 saat


def transform_openrouter_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """İleti eklerini OpenRouter standart multimodal biçimine dönüştürür:
    - input_video: {data, format} -> video_url: {url: data:video/{mime};base64,{data}}
    - input_image: {data, format} -> image_url: {url: data:image/{mime};base64,{data}}
    - Mevcut video_url, image_url, input_audio ve text girdilerini sırasını bozmadan korur.
    """
    transformed = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            transformed.append(msg)
            continue

        new_content = []
        for part in content:
            if not isinstance(part, dict):
                new_content.append(part)
                continue

            ptype = part.get("type")
            if ptype == "input_video":
                v_info = part.get("input_video") or {}
                raw_data = v_info.get("data") or v_info.get("url") or ""
                if not isinstance(raw_data, str) or not raw_data.strip():
                    raise ValueError("OpenRouter input_video requires non-empty data or url.")
                raw_data = raw_data.strip()
                raw_fmt = (v_info.get("format") or "mp4").lower().strip()
                if raw_fmt == "mov":
                    mime = "video/quicktime"
                elif raw_fmt == "avi":
                    mime = "video/x-msvideo"
                elif raw_fmt.startswith("video/"):
                    mime = raw_fmt
                else:
                    mime = f"video/{raw_fmt}"

                if raw_data.startswith("http://") or raw_data.startswith("https://") or raw_data.startswith("data:"):
                    url = raw_data
                else:
                    url = f"data:{mime};base64,{raw_data}"

                new_content.append({
                    "type": "video_url",
                    "video_url": {"url": url},
                })
            elif ptype == "input_image":
                img_info = part.get("input_image") or {}
                raw_data = img_info.get("data") or ""
                raw_fmt = (img_info.get("format") or "jpeg").lower().strip()
                mime = f"image/{raw_fmt}" if not raw_fmt.startswith("image/") else raw_fmt
                if raw_data.startswith("http://") or raw_data.startswith("https://") or raw_data.startswith("data:"):
                    url = raw_data
                else:
                    url = f"data:{mime};base64,{raw_data}"

                new_content.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            else:
                new_content.append(part)

        new_msg = dict(msg)
        new_msg["content"] = new_content
        transformed.append(new_msg)
    return transformed


def extract_required_modalities(messages: list[dict[str, Any]]) -> set[str]:
    """İletilerde ihtiyaç duyulan çok modlu (multimodal) girdi türlerini belirler."""
    modalities = set()
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                pt = part.get("type", "")
                if pt in ("input_video", "video_url"):
                    modalities.add("video")
                elif pt in ("input_image", "image_url"):
                    modalities.add("image")
                elif pt in ("input_audio", "audio"):
                    modalities.add("audio")
                elif pt in ("file", "file_url"):
                    modalities.add("file")
    return modalities


async def fetch_openrouter_model_modalities() -> dict[str, set[str]]:
    """OpenRouter modellerini sorgulayıp destekledikleri girdi modalitelerini önbelleğe alır."""
    global _MODEL_CATALOG_CACHE, _MODEL_CATALOG_LAST_FETCH
    now = time.time()
    if _MODEL_CATALOG_CACHE and (now - _MODEL_CATALOG_LAST_FETCH < _MODEL_CATALOG_TTL):
        return _MODEL_CATALOG_CACHE

    try:
        client = get_http_client()
        res = await client.get(f"{_BASE_URL.rstrip('/')}/api/v1/models", timeout=10.0)
        if res.status_code == 200:
            data = res.json().get("data", [])
            new_cache = {}
            for item in data:
                mid = (item.get("id") or "").lower()
                if not mid:
                    continue
                arch = item.get("architecture") or {}
                mods = set(arch.get("input_modalities") or [])
                if not mods and arch.get("modality"):
                    left = arch["modality"].split("->")[0]
                    mods = set(left.split("+"))
                if not mods:
                    mods = {"text"}
                new_cache[mid] = mods
                if "/" in mid:
                    short = mid.split("/", 1)[1]
                    if short not in new_cache:
                        new_cache[short] = mods
            _MODEL_CATALOG_CACHE = new_cache
            _MODEL_CATALOG_LAST_FETCH = now
    except Exception as exc:
        logger.warning("OpenRouter model kataloğu güncellenemedi: %s", exc)

    return _MODEL_CATALOG_CACHE


async def validate_model_modalities(model: str, messages: list[dict[str, Any]]) -> None:
    """İletilerdeki eklerin model tarafından desteklenip desteklenmediğini denetler."""
    needed = extract_required_modalities(messages)
    if not needed:
        return

    catalog = await fetch_openrouter_model_modalities()
    if not catalog:
        return

    m_key = model.lower().strip()
    supported = catalog.get(m_key)
    if supported is None and "/" in m_key:
        supported = catalog.get(m_key.split("/", 1)[1])

    if supported is not None:
        unsupported = needed - supported
        if unsupported:
            unsupported_sorted = sorted(list(unsupported))
            supported_sorted = sorted(list(supported))
            raise ValueError(
                f"OpenRouter model '{model}' does not support {', '.join(unsupported_sorted)} input. "
                f"Supported input modalities: {supported_sorted}."
            )


class OpenRouterChatProvider(BaseChat):

    def apply_thinking(self, payload: dict[str, Any], thinking: ThinkingConfig) -> None:
        """OpenRouter API için reasoning yapılandırmasını uygular."""
        if thinking.is_unspecified:
            return

        active = not thinking.is_disabled

        payload["include_reasoning"] = active
        template_kwargs = payload.get("chat_template_kwargs") or {}
        template_kwargs["enable_thinking"] = active
        payload["chat_template_kwargs"] = template_kwargs

        if thinking.is_disabled:
            payload["reasoning"] = {"max_tokens": 0}
        elif thinking.level is not None:
            payload["reasoning_effort"] = thinking.level
            payload["reasoning"] = {"effort": thinking.level}
        elif thinking.budget is not None:
            payload["thinking_budget_tokens"] = thinking.budget
            payload["reasoning"] = {"max_tokens": thinking.budget}

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )
        if not resolved_key:
            raise ValueError("OpenRouter Error: No API key provided.")

        # 1. Model girdi modalitelerini denetle (ör. metin modeline video/görsel gönderilmişse engelle)
        await validate_model_modalities(model, messages)

        # 2. Mesaj eklerini OpenRouter standart biçimine dönüştür (input_video -> video_url vb.)
        transformed_messages = transform_openrouter_messages(messages)

        url = f"{_BASE_URL.rstrip('/')}/api/v1/chat/completions"

        from core.config import APP_REFERER, APP_TITLE, APP_CATEGORIES
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": APP_REFERER,
            "X-OpenRouter-Title": APP_TITLE,
            "X-OpenRouter-Categories": APP_CATEGORIES,
            "Authorization": f"Bearer {resolved_key}",
        }

        payload = {
            "model": model,
            "messages": transformed_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

        if kwargs.get("chat_template_kwargs") and isinstance(kwargs["chat_template_kwargs"], dict):
            payload["chat_template_kwargs"] = dict(kwargs["chat_template_kwargs"])

        thinking = self.extract_thinking_config(kwargs)
        self.apply_thinking(payload, thinking)

        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                payload["tool_choice"] = tool_choice

        client = get_http_client()
        async with client.stream("POST", url, json=payload, headers=headers, timeout=None) as response:
            if response.status_code != 200:
                err = await response.aread()
                raise RuntimeError(f"OpenRouter HTTP Error {response.status_code}: {err.decode(errors='ignore')}")

            async for data in self._iter_sse_lines(response):
                    if data.get("usage"):
                        usage = data["usage"]
                        details = usage.get("completion_tokens_details") or {}
                        r = details.get("reasoning_tokens", 0) or 0
                        if r:
                            usage["thoughts_tokens"] = r
                            # completion_tokens reasoning dahil toplamı içerir;
                            # gerçek output = completion_tokens - reasoning_tokens
                            raw_completion = usage.get("completion_tokens", 0) or 0
                            usage["completion_tokens"] = max(0, raw_completion - r)
                        yield {"internal_usage": usage}
                        continue

                    delta = (data.get("choices") or [{}])[0].get("delta", {})
                    # OpenRouter "reasoning" veya "reasoning_content" kullanır
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if reasoning:
                        yield f'data: {{"choices":[{{"delta":{{"reasoning_content":{json.dumps(reasoning, ensure_ascii=False)}}}}}]}}\n\n'
                    if delta.get("content"):
                        yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(delta["content"], ensure_ascii=False)}}}}}]}}\n\n'
                    if delta.get("tool_calls"):
                        yield f'data: {{"choices":[{{"delta":{{"tool_calls":{json.dumps(delta["tool_calls"], ensure_ascii=False)}}}}}]}}\n\n'
