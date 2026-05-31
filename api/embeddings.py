"""
api/embeddings.py
-----------------
Embedding endpoint'i. Yönlendirme mantığı tamamen DynamicLLMRouter'a delege edilir.
Hardcoded provider kontrolü yoktur; yeni provider eklemek için api/ dosyasına dokunmak gerekmez.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from core.dependencies import authenticate_request
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.embeddings")

router = APIRouter(tags=["Embeddings"])

async def run_with_disconnect_check(request: Request, coro):
    task = asyncio.create_task(coro)
    
    async def check_disconnect():
        while True:
            if await request.is_disconnected():
                task.cancel()
                return
            await asyncio.sleep(0.1)
            
    checker = asyncio.create_task(check_disconnect())
    try:
        return await task
    finally:
        checker.cancel()

@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    key_info: dict = Depends(authenticate_request),
):
    """OpenAI uyumlu embeddings endpoint'i.

    x-orion-provider başlığı ile hangi provider kullanılacağı belirlenir.
    Desteklenen provider'lar: dynamic_router.embed_providers'da kayıtlı olanlar.
    """
    provider = request.headers.get("x-orion-provider", "local")
    api_key = request.headers.get("x-orion-api-key")
    auth_header = request.headers.get("authorization")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    input_text = body.get("input", "")
    model = body.get("model", "")

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router

    if provider not in dynamic_router.embed_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Embed not supported for provider '{provider}'. "
                   f"Available: {list(dynamic_router.embed_providers.keys())}",
        )

    try:
        result = await run_with_disconnect_check(
            request,
            dynamic_router.run_embeddings(
                provider=provider,
                model=model,
                input_text=input_text,
                api_key=api_key,
                auth_header=auth_header,
                key_id=key_info.get("key_id") if key_info else None,
            )
        )
        return result
    except Exception as e:
        logger.exception(f"Embedding error ({provider})")
        raise HTTPException(status_code=500, detail=str(e))
