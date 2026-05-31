"""
providers/gemini/chat.py
------------------------
Google Gemini streaming chat provider.
OpenAI-style mesaj formatını Gemini içerik formatına çevirir.
Thinking (reasoning) desteklidir.

Token sayım kuralı:
  candidates_token_count = out + think (toplam output)
  thoughts_token_count   = sadece think
  → completion_tokens (out) = candidates - thoughts
"""
import json
import logging
from typing import AsyncGenerator, Any

from google import genai
from google.genai import types

from providers.base import BaseChat

logger = logging.getLogger("service-router.gemini")


class GeminiChatProvider(BaseChat):
    provider_name = "gemini"

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:

        if not api_key:
            err_msg = "Gemini Error: No API key provided."
            yield f'data: {json.dumps({"error": {"message": err_msg, "type": "api_error"}}, ensure_ascii=False)}\n\n'
            return

        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            err_msg = f"Gemini client init failed: {e}"
            yield f'data: {json.dumps({"error": {"message": err_msg, "type": "api_error"}}, ensure_ascii=False)}\n\n'
            return

        # OpenAI mesaj formatını Gemini formatına çevir
        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = (
                    (system_instruction + "\n" + content) if system_instruction else content
                )
                continue

            if role == "tool":
                name = msg.get("name", "unknown")
                try:
                    resp_dict = json.loads(content)
                except Exception:
                    resp_dict = {"result": content}
                
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(name=name, response=resp_dict)]
                    )
                )
                continue
                
            if role == "assistant" and msg.get("tool_calls"):
                parts = []
                if content:
                    parts.append(types.Part.from_text(text=content))
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    
                    part_fc = types.Part.from_function_call(name=name, args=args)
                    tc_id = tc.get("id", "")
                    if "__ts__" in tc_id:
                        try:
                            import base64
                            ts_b64 = tc_id.split("__ts__", 1)[1]
                            part_fc.thought_signature = base64.b64decode(ts_b64)
                        except Exception:
                            pass

                    parts.append(part_fc)
                
                contents.append(
                    types.Content(
                        role="model",
                        parts=parts
                    )
                )
                continue

            # content bir liste ise (multimodal: metin + dosya referansı)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append(types.Part.from_text(text=part["text"]))
                    elif part.get("type") == "file_uri":
                        parts.append(
                            types.Part.from_uri(
                                file_uri=part["file_uri"],
                                mime_type=part.get("mime_type", "application/octet-stream"),
                            )
                        )
                contents.append(
                    types.Content(
                        role="user" if role == "user" else "model",
                        parts=parts,
                    )
                )
            else:
                contents.append(
                    types.Content(
                        role="user" if role == "user" else "model",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        config_kwargs: dict = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if kwargs.get("temperature") is not None:
            config_kwargs["temperature"] = float(kwargs["temperature"])

        thinking_level = kwargs.get("thinking_level")
        if thinking_level is not None:
            val = str(thinking_level).strip()
            if val.isdigit():
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=True, thinking_budget=int(val)
                )
            else:
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=True, thinking_level=val
                )

        tools = kwargs.get("tools")
        if tools:
            gemini_tools = []
            for t in tools:
                if t.get("type") == "function":
                    fn = t.get("function", {})
                    gemini_tools.append(
                        types.Tool(
                            function_declarations=[
                                types.FunctionDeclaration(
                                    name=fn.get("name", ""),
                                    description=fn.get("description", ""),
                                    parameters=fn.get("parameters", {}),
                                )
                            ]
                        )
                    )
            if gemini_tools:
                config_kwargs["tools"] = gemini_tools

        try:
            config = types.GenerateContentConfig(**config_kwargs)
        except Exception as e:
            err_msg = f"Gemini config error: {e}"
            yield f'data: {json.dumps({"error": {"message": err_msg, "type": "api_error"}}, ensure_ascii=False)}\n\n'
            return

        try:
            stream = await client.aio.models.generate_content_stream(
                model=model, contents=contents, config=config
            )
            final_usage = None

            async for chunk in stream:
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    final_usage = chunk.usage_metadata
                if not getattr(chunk, "candidates", None):
                    continue
                candidate = chunk.candidates[0]
                if not getattr(candidate, "content", None):
                    continue
                for part in candidate.content.parts or []:
                    if getattr(part, "function_call", None):
                        fc = part.function_call
                        name = fc.name
                        
                        if hasattr(fc.args, "items"):
                            args_dict = {k: v for k, v in fc.args.items()}
                        elif isinstance(fc.args, dict):
                            args_dict = fc.args
                        else:
                            try:
                                args_dict = dict(fc.args)
                            except Exception:
                                args_dict = {}

                        args_json = json.dumps(args_dict, ensure_ascii=False)
                        ts_str = ""
                        if getattr(part, "thought_signature", None):
                            import base64
                            ts_b64 = base64.b64encode(part.thought_signature).decode("utf-8")
                            ts_str = f"__ts__{ts_b64}"

                        tc = {
                            "index": 0,
                            "id": f"call_{name}{ts_str}",
                            "type": "function",
                            "function": {"name": name, "arguments": args_json}
                        }
                        yield f'data: {{"choices":[{{"delta":{{"tool_calls":[{json.dumps(tc, ensure_ascii=False)}]}}}}]}}\n\n'
                        continue

                    if not getattr(part, "text", None):
                        continue
                    if getattr(part, "thought", False):
                        yield f'data: {{"choices":[{{"delta":{{"reasoning_content":{json.dumps(part.text, ensure_ascii=False)}}}}}]}}\n\n'
                    else:
                        yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(part.text, ensure_ascii=False)}}}}}]}}\n\n'

            if final_usage:
                # Gemini'de candidates ve thoughts birbirine dahil DEĞİLDİR (tamamen ayrı hesaplanır).
                # total_token_count = prompt + candidates + thoughts
                # O yüzden completion_tokens = candidates, thoughts_tokens = thoughts olur.
                candidates = getattr(final_usage, "candidates_token_count", 0) or 0
                thoughts   = getattr(final_usage, "thoughts_token_count", 0) or 0
                prompt     = getattr(final_usage, "prompt_token_count", 0) or 0
                total      = getattr(final_usage, "total_token_count", 0) or 0

                logger.info(
                    f"Gemini usage: prompt={prompt} candidates={candidates} "
                    f"thoughts={thoughts} total={total}"
                )

                yield {
                    "internal_usage": {
                        "prompt_tokens": prompt,
                        "completion_tokens": candidates,
                        "thoughts_tokens": thoughts,
                        "total_tokens": total,
                    }
                }
        except Exception as e:
            err_msg = f"Gemini stream error: {e}"
            yield f'data: {json.dumps({"error": {"message": err_msg, "type": "api_error"}}, ensure_ascii=False)}\n\n'
