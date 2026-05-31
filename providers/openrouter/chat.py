"""
providers/openrouter/chat.py
----------------------------
OpenRouter API streaming chat provider.
reasoning (thinking) ve include_reasoning desteklidir.
"""
import json
import httpx
from typing import AsyncGenerator, Any

from providers.base import BaseChat

_BASE_URL = "https://openrouter.ai"


class OpenRouterChatProvider(BaseChat):
    provider_name = "openrouter"

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        url = f"{_BASE_URL.rstrip('/')}/api/v1/chat/completions"

        if not api_key:
            raise ValueError("OpenRouter Error: No API key provided.")

        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/krstalacam/orion-ai-assistant",
            "X-Title": "Orion AI Assistant",
            "Authorization": f"Bearer {api_key}",
        }

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

        thinking_level = kwargs.get("thinking_level")
        if thinking_level is not None:
            payload["reasoning_effort"] = thinking_level
            payload["include_reasoning"] = True  # only request reasoning when thinking is active

        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
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
