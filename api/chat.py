"""
api/chat.py
-----------
Chat completions ve model bilgisi endpoint'leri.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

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
    if not stream:
        raise HTTPException(
            status_code=400,
            detail="Only streaming is supported by DynamicLLMRouter currently.",
        )

    messages = body.get("messages", [])
    raw_model = body.get("model", "local-model")
    model = (raw_model or "local-model").strip()
    thinking_level = body.get("thinking_level")
    tools = body.get("tools")
    tool_choice = body.get("tool_choice")

    # Pass remaining keys to dynamic router
    kwargs = {
        k: v for k, v in body.items()
        if k not in ("stream", "messages", "model", "thinking_level", "tools", "tool_choice")
    }

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router
    return StreamingResponse(
        dynamic_router.run_combo(
            provider=provider,
            model=model,
            messages=messages,
            api_key=api_key,
            auth_header=auth_header,
            key_id=key_info.get("key_id") if key_info else None,
            thinking_level=thinking_level,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/v1/model-info")
async def get_model_info(request: Request):
    """Önbellekteki model bilgisini döner."""
    return request.app.state.model_info_cache
