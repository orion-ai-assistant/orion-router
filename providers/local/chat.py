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
        }

        # Sampling parametreleri toplu ve düzenli sırada
        for key in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty"):
            if kwargs.get(key) is not None:
                if key == "top_k":
                    payload[key] = int(kwargs[key])
                else:
                    payload[key] = float(kwargs[key])

        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}

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

        # Kaç karakter reasoning ve yanıt metni geldiğini takip ediyoruz
        thought_chars = 0
        content_chars = 0

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

                        if api_reasoning and raw_completion > api_reasoning:
                            usage["thoughts_tokens"] = api_reasoning
                            usage["completion_tokens"] = raw_completion - api_reasoning
                        elif api_reasoning and content_chars > 0 and raw_completion <= api_reasoning:
                            est_content = max(1, content_chars // 4)
                            usage["thoughts_tokens"] = api_reasoning
                            usage["completion_tokens"] = est_content
                            usage["total_tokens"] = usage.get("prompt_tokens", 0) + api_reasoning + est_content
                        elif thought_chars > 0:
                            total_chars = thought_chars + content_chars
                            if content_chars > 0 and total_chars > 0:
                                if raw_completion > 0:
                                    est_content = max(1, round(raw_completion * (content_chars / total_chars)))
                                    if raw_completion > 1:
                                        est_content = min(est_content, raw_completion - 1)
                                    est_think = max(1, raw_completion - est_content)
                                else:
                                    est_think = max(1, thought_chars // 4)
                                    est_content = max(1, content_chars // 4)
                                    raw_completion = est_think + est_content
                                    usage["total_tokens"] = usage.get("prompt_tokens", 0) + raw_completion
                                usage["thoughts_tokens"] = est_think
                                usage["completion_tokens"] = est_content
                            else:
                                usage["thoughts_tokens"] = raw_completion
                                usage["completion_tokens"] = 0
                        else:
                            if content_chars > 0 and raw_completion == 0:
                                raw_completion = max(1, content_chars // 4)
                                usage["total_tokens"] = usage.get("prompt_tokens", 0) + raw_completion
                            usage["thoughts_tokens"] = 0
                            usage["completion_tokens"] = raw_completion

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
                        content_chars += len(c)
                        yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(c, ensure_ascii=False)}}}}}]}}\n\n'

                    if delta.get("tool_calls"):
                        yield f'data: {{"choices":[{{"delta":{{"tool_calls":{json.dumps(delta["tool_calls"], ensure_ascii=False)}}}}}]}}\n\n'
        except httpx.ConnectError:
            raise RuntimeError(f"Could not connect to local LLM service ({LLM_HOST}:{LLM_PORT}).")
        except httpx.TimeoutException:
            raise RuntimeError(f"Local LLM service ({LLM_HOST}:{LLM_PORT}) timed out.")
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error connecting to local LLM service: {e}")
