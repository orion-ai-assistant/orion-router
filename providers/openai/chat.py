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

    @staticmethod
    def _responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                items.append({
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": message.get("content", ""),
                })
            elif role == "assistant" and message.get("tool_calls"):
                if message.get("content"):
                    items.append({"role": "assistant", "content": message["content"]})
                for call in message["tool_calls"]:
                    fn = call.get("function") or {}
                    items.append({
                        "type": "function_call",
                        "call_id": call["id"],
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", "{}"),
                    })
            else:
                content = message.get("content", "")
                if isinstance(content, list):
                    new_content = []
                    for part in content:
                        if part.get("type") == "text":
                            new_content.append({"type": "input_text", "text": part.get("text", "")})
                        elif part.get("type") in ("image_url", "input_image"):
                            img_val = part.get("image_url")
                            url = ""
                            if isinstance(img_val, dict):
                                url = img_val.get("url", "")
                            elif isinstance(img_val, str):
                                url = img_val
                            
                            if url.startswith("data:audio/"):
                                try:
                                    header, b64 = url.split(",", 1)
                                    fmt = header.split(";")[0].split("/")[-1]
                                    new_content.append({"type": "input_audio", "input_audio": {"data": b64, "format": fmt}})
                                except Exception:
                                    pass
                            elif url:
                                new_content.append({"type": "input_image", "image_url": url})
                        else:
                            new_content.append(part)
                    items.append({"role": role, "content": new_content})
                else:
                    items.append({"role": role, "content": content})
        return items

    def _responses_payload(self, model: str, messages: list[dict[str, Any]], kwargs: dict) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "input": self._responses_input(messages),
            "stream": True,
            "store": False,
        }
        thinking = self.extract_thinking_config(kwargs)
        if thinking.level is not None:
            payload["reasoning"] = {"effort": thinking.level}
        elif thinking.is_disabled:
            payload["reasoning"] = {"effort": "none"}
        if thinking.level is None and kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = [
                {"type": "function", **tool.get("function", {})}
                if tool.get("type") == "function" else tool
                for tool in tools
            ]
            choice = kwargs.get("tool_choice")
            if isinstance(choice, dict) and choice.get("type") == "function":
                payload["tool_choice"] = {"type": "function", "name": choice.get("function", {}).get("name", "")}
            elif choice:
                payload["tool_choice"] = choice
        return payload

    async def _stream_responses(self, client, headers: dict, payload: dict) -> AsyncGenerator[Any, None]:
        url = f"{_BASE_URL}/v1/responses"
        tool_indexes: dict[int, int] = {}
        async with client.stream("POST", url, json=payload, headers=headers, timeout=None) as response:
            if response.status_code != 200:
                err = await response.aread()
                message = err.decode(errors="ignore")
                if response.status_code == 400 and "reasoning" in payload and "reasoning" in message.lower():
                    fallback = {key: value for key, value in payload.items() if key not in ("reasoning", "temperature")}
                    async for chunk in self._stream_responses(client, headers, fallback):
                        yield chunk
                    return
                raise RuntimeError(f"OpenAI Responses HTTP Error {response.status_code}: {message}")

            async for event in self._iter_sse_lines(response):
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    yield f'data: {json.dumps({"choices": [{"delta": {"content": event.get("delta", "")}}]}, ensure_ascii=False)}\n\n'
                elif kind == "response.output_item.added" and event.get("item", {}).get("type") == "function_call":
                    item = event["item"]
                    output_index = event.get("output_index", 0)
                    tool_indexes[output_index] = len(tool_indexes)
                    call = {"index": tool_indexes[output_index], "id": item.get("call_id"), "type": "function", "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "")}}
                    yield f'data: {json.dumps({"choices": [{"delta": {"tool_calls": [call]}}]}, ensure_ascii=False)}\n\n'
                elif kind == "response.function_call_arguments.delta":
                    output_index = event.get("output_index", 0)
                    if output_index in tool_indexes:
                        call = {"index": tool_indexes[output_index], "function": {"arguments": event.get("delta", "")}}
                        yield f'data: {json.dumps({"choices": [{"delta": {"tool_calls": [call]}}]}, ensure_ascii=False)}\n\n'
                elif kind == "response.completed":
                    usage = event.get("response", {}).get("usage") or {}
                    if usage:
                        reasoning = (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0) or 0
                        yield {"internal_usage": {
                            "prompt_tokens": usage.get("input_tokens", 0),
                            "completion_tokens": max(0, (usage.get("output_tokens", 0) or 0) - reasoning),
                            "thoughts_tokens": reasoning,
                        }}
                elif kind in ("error", "response.failed"):
                    error = event.get("error") or event.get("response", {}).get("error") or event
                    raise RuntimeError(f"OpenAI Responses stream error: {error}")

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        # Audio belongs to Chat Completions; never silently reroute it to Responses.
        content_parts = [part for msg in messages if isinstance(msg.get("content"), list)
                         for part in msg["content"]]
        if any(part.get("type") in ("input_video", "video_url") for part in content_parts):
            raise ValueError("OpenAI chat does not accept raw video here. Use a video-capable provider.")
        has_audio = any(part.get("type") == "input_audio" for part in content_parts)
        for part in content_parts:
            if part.get("type") == "input_audio":
                audio = part["input_audio"]
                if audio.get("format") not in ("wav", "mp3") or not audio.get("data"):
                    raise ValueError("OpenAI input_audio requires base64 data in wav or mp3 format.")

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
        thinking = self.extract_thinking_config(kwargs)
        self.apply_thinking(payload, thinking)
        if "reasoning_effort" not in payload and kwargs.get("temperature") is not None:
            payload["temperature"] = float(kwargs["temperature"])

        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                payload["tool_choice"] = tool_choice

        client = get_http_client()
        if tools and thinking.is_active and not has_audio:
            async for chunk in self._stream_responses(client, headers, self._responses_payload(model, messages, kwargs)):
                yield chunk
            return

        async with client.stream("POST", url, json=payload, headers=headers, timeout=None) as response:
            if response.status_code != 200:
                err = await response.aread()
                message = err.decode(errors="ignore")
                if response.status_code == 400 and tools and not has_audio and any(
                    marker in message.lower() for marker in ("tool", "function call", "responses api", "reasoning_effort")
                ):
                    async for chunk in self._stream_responses(client, headers, self._responses_payload(model, messages, kwargs)):
                        yield chunk
                    return
                if response.status_code == 400 and "reasoning_effort" in payload and any(
                    marker in message.lower() for marker in ("reasoning_effort", "reasoning effort")
                ):
                    fallback = {key: value for key, value in payload.items() if key != "reasoning_effort"}
                    if kwargs.get("temperature") is not None:
                        fallback["temperature"] = float(kwargs["temperature"])
                    async with client.stream("POST", url, json=fallback, headers=headers, timeout=None) as retry:
                        if retry.status_code != 200:
                            retry_error = await retry.aread()
                            raise RuntimeError(f"OpenAI HTTP Error {retry.status_code}: {retry_error.decode(errors='ignore')}")
                        async for data in self._iter_sse_lines(retry):
                            async for chunk in self._chat_chunks(data):
                                yield chunk
                    return
                if response.status_code == 400 and "temperature" in payload and "temperature" in message.lower():
                    fallback = {key: value for key, value in payload.items() if key != "temperature"}
                    async with client.stream("POST", url, json=fallback, headers=headers, timeout=None) as retry:
                        if retry.status_code != 200:
                            retry_error = await retry.aread()
                            raise RuntimeError(f"OpenAI HTTP Error {retry.status_code}: {retry_error.decode(errors='ignore')}")
                        async for data in self._iter_sse_lines(retry):
                            async for chunk in self._chat_chunks(data):
                                yield chunk
                    return
                raise RuntimeError(f"OpenAI HTTP Error {response.status_code}: {message}")

            async for data in self._iter_sse_lines(response):
                async for chunk in self._chat_chunks(data):
                    yield chunk

    async def _chat_chunks(self, data: dict) -> AsyncGenerator[Any, None]:
        if data.get("usage"):
            usage = data["usage"]
            details = usage.get("completion_tokens_details") or {}
            reasoning = details.get("reasoning_tokens", 0) or 0
            if reasoning:
                usage["thoughts_tokens"] = reasoning
                usage["completion_tokens"] = max(0, (usage.get("completion_tokens", 0) or 0) - reasoning)
            yield {"internal_usage": usage}
            return

        delta = (data.get("choices") or [{}])[0].get("delta", {})
        for key in ("reasoning_content", "content", "tool_calls"):
            if delta.get(key):
                yield f'data: {json.dumps({"choices": [{"delta": {key: delta[key]}}]}, ensure_ascii=False)}\n\n'
