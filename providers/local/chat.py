"""
providers/local/chat.py
-----------------------
llama-cpp sunucusuna streaming chat yönlendirmesi.
Thinking desteklidir. API reasoning_tokens vermezse karakter bazlı tahminle ayırır.
"""
import json
import httpx
from typing import AsyncGenerator, Any

from providers.base import BaseChat
from core.config import LLM_HOST, LLM_PORT


class LocalChatProvider(BaseChat):


    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        url = f"http://{LLM_HOST}:{LLM_PORT}/v1/chat/completions"

        payload = {
            "model": "local-model",
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

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

        # Kaç karakter reasoning (think) geldi — API breakdown vermezse tahmin için
        thought_chars = 0

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", url, json=payload, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    err = await response.aread()
                    raise RuntimeError(f"Local HTTP Error {response.status_code}: {err.decode(errors='ignore')}")

                async for data in self._iter_sse_lines(response):
                    # ── Usage chunk ────────────────────────────────────────────────────
                    if data.get("usage"):
                        usage = data["usage"]
                        raw_completion = usage.get("completion_tokens", 0) or 0

                        # API reasoning_tokens breakdown veriyorsa kullan
                        details = usage.get("completion_tokens_details") or {}
                        api_reasoning = details.get("reasoning_tokens", 0) or 0

                        if api_reasoning:
                            # API net breakdown verdi
                            usage["thoughts_tokens"] = api_reasoning
                            usage["completion_tokens"] = max(0, raw_completion - api_reasoning)
                        elif thought_chars > 0:
                            # API vermedi ama think stream'i geldi → char oranıyla böl
                            # raw_completion = toplam output (think + text)
                            # think oranı = thought_chars / (thought_chars + out_chars)
                            # Burada out_chars'ı bilmiyoruz, ama orantıyı kullanabiliriz:
                            # think_tokens ≈ raw_completion * (thought_chars / total_chars)
                            # total_chars hesabı yapamıyoruz burada, basit yaklaşım:
                            # think_tokens ≈ thought_chars // 4 (char/token oranı)
                            est_think = thought_chars // 4
                            est_think = min(est_think, raw_completion)  # toplam aşmasın
                            usage["thoughts_tokens"] = est_think
                            usage["completion_tokens"] = max(0, raw_completion - est_think)
                        # else: API breakdown yok, think yok → tüm completion_tokens out'ta kalır

                        yield {"internal_usage": usage}
                        continue

                    # ── Content chunks ─────────────────────────────────────────────────
                    delta = (data.get("choices") or [{}])[0].get("delta", {})

                    if delta.get("reasoning_content"):
                        rc = delta["reasoning_content"]
                        thought_chars += len(rc)
                        yield f'data: {{"choices":[{{"delta":{{"reasoning_content":{json.dumps(rc, ensure_ascii=False)}}}}}]}}\n\n'

                    if delta.get("content"):
                        c = delta["content"]
                        yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(c, ensure_ascii=False)}}}}}]}}\n\n'

                    if delta.get("tool_calls"):
                        yield f'data: {{"choices":[{{"delta":{{"tool_calls":{json.dumps(delta["tool_calls"], ensure_ascii=False)}}}}}]}}\n\n'
