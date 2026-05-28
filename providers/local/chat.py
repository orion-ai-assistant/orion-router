"""
providers/local/chat.py
-----------------------
llama-cpp sunucusuna streaming chat yönlendirmesi.
"""
import os
import json
import httpx
from typing import AsyncGenerator, Any

from providers.base import BaseChat
from core.config import LLM_HOST, LLM_PORT


class LocalChatProvider(BaseChat):
    provider_name = "local"

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        llm_host = LLM_HOST
        llm_port = LLM_PORT
        url = f"http://{llm_host}:{llm_port}/v1/chat/completions"

        payload = {
            "model": "local-model",
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        thinking_level = kwargs.get("thinking_level")
        if thinking_level is not None:
            val = str(thinking_level).strip()
            if val.isdigit():
                payload["thinking_budget_tokens"] = int(val)
            elif val.lower() == "false":
                payload["chat_template_kwargs"] = {"enable_thinking": False}
            elif val.lower() == "true":
                payload["chat_template_kwargs"] = {"enable_thinking": True}

        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                payload["tool_choice"] = tool_choice

        # Fallback token tahmini (sunucu usage döndürmezse kullanılır)
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        est_prompt = max(1, prompt_chars // 4)
        out_chars = 0
        thought_chars = 0

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", url, json=payload, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    err = await response.aread()
                    raise RuntimeError(f"Local HTTP Error {response.status_code}: {err.decode(errors='ignore')}")

                got_usage = False
                async for data in self._iter_sse_lines(response):
                    if data.get("usage"):
                        got_usage = True
                        usage = data["usage"]
                        raw_completion = usage.get("completion_tokens", 0) or 0
                        details = usage.get("completion_tokens_details") or {}
                        r = details.get("reasoning_tokens", 0) or 0
                        if r:
                            # API reasoning_tokens döndü; output = toplam - reasoning
                            usage["thoughts_tokens"] = r
                            usage["completion_tokens"] = max(0, raw_completion - r)
                        elif thought_chars > 0:
                            # API detay vermedi ama thinking stream'i geldi;
                            # kısa output'u char'dan tahmin et, thinking'i farktan bul
                            est_output = max(1, out_chars // 4) if out_chars else 0
                            usage["completion_tokens"] = est_output
                            usage["thoughts_tokens"] = max(0, raw_completion - est_output)
                        yield {"internal_usage": usage}
                        continue

                    delta = (data.get("choices") or [{}])[0].get("delta", {})

                    if delta.get("reasoning_content"):
                        rc = delta["reasoning_content"]
                        thought_chars += len(rc)
                        yield f'data: {{"choices":[{{"delta":{{"reasoning_content":{json.dumps(rc, ensure_ascii=False)}}}}}]}}\n\n'

                    if delta.get("content"):
                        c = delta["content"]
                        out_chars += len(c)
                        yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(c, ensure_ascii=False)}}}}}]}}\n\n'

                    if delta.get("tool_calls"):
                        yield f'data: {{"choices":[{{"delta":{{"tool_calls":{json.dumps(delta["tool_calls"], ensure_ascii=False)}}}}}]}}\n\n'

                if not got_usage:
                    est_out = max(1, out_chars // 4)
                    yield {
                        "internal_usage": {
                            "prompt_tokens": est_prompt,
                            "completion_tokens": est_out,
                            "thoughts_tokens": max(0, thought_chars // 4),
                            "total_tokens": est_prompt + est_out,
                        }
                    }
