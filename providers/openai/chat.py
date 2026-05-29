"""
providers/openai/chat.py
------------------------
OpenAI API streaming chat provider.
reasoning_effort (thinking_level) desteklidir.
"""
import json
import httpx
from typing import AsyncGenerator, Any

from providers.base import BaseChat

_BASE_URL = "https://api.openai.com"


class OpenAIChatProvider(BaseChat):
    provider_name = "openai"

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        url = f"{_BASE_URL}/v1/chat/completions"

        if not api_key:
            raise ValueError("OpenAI Error: No API key provided.")

        headers = {
            "Content-Type": "application/json",
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
                    raise RuntimeError(f"OpenAI HTTP Error {response.status_code}: {err.decode(errors='ignore')}")

                async for data in self._iter_sse_lines(response):
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

                    delta = (data.get("choices") or [{}])[0].get("delta", {})
                    if delta.get("reasoning_content"):
                        yield f'data: {{"choices":[{{"delta":{{"reasoning_content":{json.dumps(delta["reasoning_content"], ensure_ascii=False)}}}}}]}}\n\n'
                    if delta.get("content"):
                        yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(delta["content"], ensure_ascii=False)}}}}}]}}\n\n'
                    if delta.get("tool_calls"):
                        yield f'data: {{"choices":[{{"delta":{{"tool_calls":{json.dumps(delta["tool_calls"], ensure_ascii=False)}}}}}]}}\n\n'
