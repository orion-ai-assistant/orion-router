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

from core.thinking import ThinkingConfig

_BASE_URL = "https://openrouter.ai"


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

        url = f"{_BASE_URL.rstrip('/')}/api/v1/chat/completions"

        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )

        if not resolved_key:
            raise ValueError("OpenRouter Error: No API key provided.")

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
            "messages": messages,
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
