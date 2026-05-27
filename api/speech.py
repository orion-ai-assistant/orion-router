"""
api/speech.py
-------------
OpenAI-compatible text-to-speech endpoint.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from core.dependencies import authenticate_request
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.speech")

router = APIRouter(tags=["Speech"])


@router.post("/v1/audio/speech")
async def audio_speech(
    request: Request,
    auth: dict = Depends(authenticate_request),
):
    provider = request.headers.get("x-orion-provider")
    api_key = request.headers.get("x-orion-api-key")
    auth_header = request.headers.get("authorization")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    input_text = body.get("input", "")
    model = (body.get("model", "") or "").strip()
    voice = body.get("voice")
    temperature = body.get("temperature")

    if not input_text:
        raise HTTPException(status_code=400, detail="'input' field is required")

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router

    try:
        audio_bytes, content_type = await dynamic_router.run_speech(
            provider=provider,
            model=model,
            input_text=input_text,
            voice=voice,
            api_key=api_key,
            auth_header=auth_header,
            key_id=auth.get("key_id") if auth else None,
            temperature=temperature,
        )
        return Response(
            content=audio_bytes,
            media_type=content_type,
            headers={"Content-Disposition": "inline; filename=\"speech.wav\""},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"TTS error ({provider or model})")
        raise HTTPException(status_code=500, detail=str(e))
