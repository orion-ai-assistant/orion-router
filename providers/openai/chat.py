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

from core.thinking import ThinkingConfig
from core.http_client import get_http_client

_BASE_URL = "https://api.openai.com"


class OpenAIChatProvider(BaseChat):

    def apply_thinking(self, payload: dict[str, Any], thinking: ThinkingConfig) -> None:
        """OpenAI API için reasoning_effort parametresini uygular."""
        if thinking.is_unspecified or thinking.is_disabled:
            # Devre dışı veya belirtilmemiş ise reasoning_effort eklenmez
            return

        if thinking.level is not None:
            payload["reasoning_effort"] = thinking.level

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        url = f"{_BASE_URL}/v1/chat/completions"

        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )

        if not resolved_key:
            raise ValueError("OpenAI Error: No API key provided.")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {resolved_key}",
        }

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

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
