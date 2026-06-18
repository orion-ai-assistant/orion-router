"""
api/chat.py
-----------
Chat completions ve model bilgisi endpoint'leri.
"""
import logging
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

from core.dependencies import authenticate_request
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.chat")

router = APIRouter(tags=["Chat"])


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    key_info: dict = Depends(authenticate_request),
):
    """OpenAI uyumlu chat completions endpoint'i (yalnızca streaming)."""
    # --- Başlıkları parse et ---
    provider = request.headers.get("x-orion-provider", "local")
    api_key = request.headers.get("x-orion-api-key")
    auth_header = request.headers.get("authorization")

    # --- Body'yi oku ---
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    stream = body.get("stream", False)

    messages = body.get("messages", [])
    raw_model = body.get("model", "")
    model = (raw_model or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="'model' field is required. Please specify a model name explicitly.")
    thinking_level = body.get("thinking_level")
    system_prompt = body.get("system_prompt")
    tools = body.get("tools")
    tool_choice = body.get("tool_choice")

    # Pass remaining keys to dynamic router
    kwargs = {
        k: v for k, v in body.items()
        if k not in ("stream", "messages", "model", "thinking_level", "system_prompt", "tools", "tool_choice")
    }

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router
    combo_generator = dynamic_router.run_combo(
        provider=provider,
        model=model,
        messages=messages,
        api_key=api_key,
        auth_header=auth_header,
        key_id=key_info.get("key_id") if key_info else None,
        thinking_level=thinking_level,
        system_prompt=system_prompt,
        tools=tools,
        tool_choice=tool_choice,
        **kwargs
    )

    if stream:
        return StreamingResponse(
            combo_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        accumulated_content = ""
        accumulated_reasoning = ""
        accumulated_tool_calls = []
        error_response = None
        
        async for chunk in combo_generator:
            if isinstance(chunk, str):
                data_str = chunk.strip()
                if data_str.startswith("data:"):
                    data_str = data_str[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    chunk_data = json.loads(data_str)
                    if "error" in chunk_data:
                        error_response = chunk_data
                        break
                    
                    choices = chunk_data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            accumulated_reasoning += delta["reasoning_content"]
                        if "content" in delta and delta["content"]:
                            accumulated_content += delta["content"]
                        if "tool_calls" in delta:
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                while len(accumulated_tool_calls) <= idx:
                                    accumulated_tool_calls.append({
                                        "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                                    })
                                entry = accumulated_tool_calls[idx]
                                if tc_delta.get("id"):
                                    entry["id"] = tc_delta["id"]
                                fn = tc_delta.get("function", {})
                                if fn.get("name"):
                                    entry["function"]["name"] = fn["name"]
                                if fn.get("arguments"):
                                    entry["function"]["arguments"] += fn["arguments"]
                except Exception:
                    pass

        if error_response:
            return JSONResponse(status_code=400, content=error_response)
            
        msg_data = {
            "role": "assistant",
            "content": accumulated_content
        }
        if accumulated_reasoning:
            msg_data["reasoning_content"] = accumulated_reasoning
        if accumulated_tool_calls:
            msg_data["tool_calls"] = accumulated_tool_calls

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": msg_data,
                "logprobs": None,
                "finish_reason": "stop"
            }]
        }


@router.get("/v1/model-info")
async def get_model_info(request: Request):
    """Önbellekteki model bilgisini döner."""
    return request.app.state.model_info_cache
