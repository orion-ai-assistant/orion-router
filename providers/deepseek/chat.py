"""
providers/deepseek/chat.py
--------------------------
DeepSeek API streaming chat provider.
Desteklenen modeller:
  - deepseek-flash (DeepSeek-V4.1-Flash): Metin, JSON, Tool Calls, Vision ve Thinking Mode
  - deepseek-v4-pro (DeepSeek-V4-Pro-0813): Metin, JSON, Tool Calls, Thinking Mode (Görsel desteklenmez)
"""
import json
import logging
import os
from typing import Any, AsyncGenerator

from core.http_client import get_http_client
from core.thinking import ThinkingConfig
from providers.base import BaseChat

_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
logger = logging.getLogger("service-router.deepseek")

# Eski veya alternatif model isimlerini güncel resmi modellere yönlendirir
MODEL_ALIASES: dict[str, str] = {
    "deepseek-chat": "deepseek-flash",
    "deepseek-reasoner": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
}

# DeepSeek reasoning_effort eşleştirmeleri
_EFFORT_MAP: dict[str, str] = {
    "minimal": "low",
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
    "max": "max",
    "ultra": "max",
}


def validate_deepseek_modalities(model: str, messages: list[dict[str, Any]]) -> None:
    """DeepSeek modellerinin desteklemediği modaliteleri doğrular."""
    has_image = False
    has_audio = False
    has_video = False

    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type", "")
                if ptype in ("image_url", "image", "input_image"):
                    has_image = True
                elif ptype in ("input_audio", "audio"):
                    has_audio = True
                elif ptype in ("input_video", "video_url", "video"):
                    has_video = True

    if has_audio:
        raise ValueError(f"DeepSeek model '{model}' does not support audio input.")
    if has_video:
        raise ValueError(f"DeepSeek model '{model}' does not support video input.")
    if has_image and model == "deepseek-v4-pro":
        raise ValueError(
            f"DeepSeek model '{model}' does not support vision/image input. "
            "Please use 'deepseek-flash' for multimodal requests."
        )


def transform_deepseek_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gelen mesajları DeepSeek OpenAI-uyumlu formatına normalize eder.
    
    Not: DeepSeek Tool Calls ve Thinking Mode dokümantasyonuna göre;
    asistan mesajlarındaki `reasoning_content` parametresi tool çağrıları
    içeren çoklu turlarda API'ye eksiksiz geri iletilmelidir.
    """
    transformed = []
    for msg in messages:
        m = dict(msg)
        content = m.get("content")
        if isinstance(content, list):
            new_content = []
            for part in content:
                if isinstance(part, dict):
                    # Orion / Hub standart input_image formatını image_url'e çevir
                    if part.get("type") == "input_image":
                        img = part.get("image") or part.get("input_image") or {}
                        url = img.get("url")
                        if not url and img.get("data"):
                            fmt = img.get("format", "jpeg")
                            url = f"data:image/{fmt};base64,{img['data']}"
                        if url:
                            new_content.append({"type": "image_url", "image_url": {"url": url}})
                            continue
                new_content.append(part)
            m["content"] = new_content
        transformed.append(m)
    return transformed


class DeepSeekChatProvider(BaseChat):
    provider_name: str = "deepseek"

    def apply_thinking(self, payload: dict[str, Any], thinking: ThinkingConfig) -> None:
        """DeepSeek Thinking Mode ve reasoning_effort parametrelerini uygular."""
        if thinking.is_disabled:
            payload["thinking"] = {"type": "disabled"}
            return

        if thinking.is_active:
            payload["thinking"] = {"type": "enabled"}
            if thinking.level is not None:
                effort = _EFFORT_MAP.get(thinking.level.lower(), thinking.level)
                payload["reasoning_effort"] = effort
            elif thinking.budget is not None:
                payload["reasoning_effort"] = "low" if thinking.budget <= 2048 else "high"

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
            raise ValueError("DeepSeek Error: No API key provided.")

        actual_model = MODEL_ALIASES.get(model, model)

        # 1. Desteklenmeyen modaliteleri denetle
        validate_deepseek_modalities(actual_model, messages)

        # 2. Mesaj eklerini ve reasoning_content'i normalize et
        transformed_messages = transform_deepseek_messages(messages)

        url = f"{_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {resolved_key}",
        }

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": transformed_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])
        if kwargs.get("top_p") is not None:
            payload["top_p"] = float(kwargs["top_p"])
        if kwargs.get("max_tokens") is not None:
            payload["max_tokens"] = int(kwargs["max_tokens"])
        elif kwargs.get("max_completion_tokens") is not None:
            payload["max_tokens"] = int(kwargs["max_completion_tokens"])

        if kwargs.get("response_format") is not None:
            payload["response_format"] = kwargs["response_format"]

        thinking = self.extract_thinking_config(kwargs)
        # deepseek-reasoner model alias'ı istenmiş ve thinking belirtilmemişse varsayılan aktif olsun
        if model == "deepseek-reasoner" and thinking.is_unspecified:
            thinking = ThinkingConfig.from_value("high")
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
                raise RuntimeError(
                    f"DeepSeek HTTP Error {response.status_code}: {err.decode(errors='ignore')}"
                )

            async for data in self._iter_sse_lines(response):
                if data.get("error"):
                    err = data["error"]
                    err_msg = err.get("message", json.dumps(err)) if isinstance(err, dict) else str(err)
                    raise RuntimeError(f"DeepSeek Stream Error: {err_msg}")

                if data.get("usage"):
                    usage = data["usage"]
                    details = usage.get("completion_tokens_details") or {}
                    r = details.get("reasoning_tokens", 0) or 0
                    if r:
                        usage["thoughts_tokens"] = r
                        raw_completion = usage.get("completion_tokens", 0) or 0
                        usage["completion_tokens"] = max(0, raw_completion - r)
                    yield {"internal_usage": usage}
                    continue

                choices = data.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    yield f'data: {{"choices":[{{"delta":{{"reasoning_content":{json.dumps(reasoning, ensure_ascii=False)}}}}}]}}\n\n'

                if delta.get("content"):
                    yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(delta["content"], ensure_ascii=False)}}}}}]}}\n\n'

                if delta.get("tool_calls"):
                    yield f'data: {{"choices":[{{"delta":{{"tool_calls":{json.dumps(delta["tool_calls"], ensure_ascii=False)}}}}}]}}\n\n'
