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
from core.thinking import ThinkingConfig
from core.config import LLM_HOST, LLM_PORT
from core.http_client import get_http_client
from core.local_chat_defaults import LOCAL_CHAT_MODEL_NAME


def _response_error_message(body: bytes) -> str:
    raw_body = body.decode(errors="ignore").strip() or "<empty>"
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if payload.get("detail"):
            return str(payload["detail"])
    return raw_body


class LocalChatProvider(BaseChat):

    def apply_thinking(self, payload: dict[str, Any], thinking: ThinkingConfig) -> None:
        """llama.cpp / vLLM / Qwen / Jinja chat şablonları için düşünme ayarlarını uygular."""
        if thinking.is_unspecified:
            return

        active = not thinking.is_disabled

        template_kwargs = payload.get("chat_template_kwargs") or {}
        template_kwargs["enable_thinking"] = active
        payload["chat_template_kwargs"] = template_kwargs

        if thinking.is_disabled:
            payload["thinking_budget_tokens"] = 0
            payload["reasoning_effort"] = "none"
        elif thinking.level is not None:
            payload["reasoning_effort"] = thinking.level
        elif thinking.budget is not None:
            payload["thinking_budget_tokens"] = thinking.budget

    def build_payload(self, model: str, messages: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Build the exact JSON body sent to the local chat server."""
        payload = {
            "model": model or LOCAL_CHAT_MODEL_NAME,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

        for key in ("top_p", "min_p", "repeat_penalty"):
            if kwargs.get(key) is not None:
                payload[key] = float(kwargs[key])
        if kwargs.get("top_k") is not None:
            payload["top_k"] = int(kwargs["top_k"])

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

        return payload

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        url = f"http://{LLM_HOST}:{LLM_PORT}/v1/chat/completions"
        payload = self.build_payload(model, messages, **kwargs)

        # Kaç karakter reasoning (think) geldi — API breakdown vermezse tahmin için
        thought_chars = 0

        client = get_http_client()
        try:
            async with client.stream(
                "POST", url, json=payload, headers={"Content-Type": "application/json"}, timeout=None
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    message = _response_error_message(body)
                    raise RuntimeError(message)

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
        except httpx.ConnectError:
            raise RuntimeError(
                f"Yerel LLM servisine ({LLM_HOST}:{LLM_PORT}) bağlanılamadı. "
                f"Lütfen yerel model sunucusunun (llama.cpp vb.) açık olduğundan emin olun."
            )
        except httpx.TimeoutException:
            raise RuntimeError(f"Yerel LLM servisi ({LLM_HOST}:{LLM_PORT}) zaman aşımına uğradı.")
        except httpx.RequestError as e:
            raise RuntimeError(f"Yerel LLM servisine bağlanırken ağ hatası oluştu: {e}")
