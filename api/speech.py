"""
api/speech.py
-------------
OpenAI-compatible text-to-speech endpoint.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from core.audio_container import finalize_buffered_wav
from core.dependencies import authenticate_request
from core.utils import run_with_disconnect_check
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.speech")

router = APIRouter(tags=["Speech"])

@router.post("/v1/audio/speech")
@router.post("/v1/audio/speech/stream")
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
    req_url = getattr(request, "url", None)
    url_path = getattr(req_url, "path", "") if req_url else ""
    is_stream = bool(body.get("stream", False)) or url_path.endswith("/stream")

    if not input_text:
        raise HTTPException(status_code=400, detail="'input' field is required")

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router

    extra_kwargs = {k: v for k, v in body.items() if k not in ("input", "model", "voice", "stream")}

    if is_stream:
        stream_gen = dynamic_router.run_speech_stream(
            provider=provider,
            model=model,
            input_text=input_text,
            voice=voice,
            api_key=api_key,
            auth_header=auth_header,
            key_id=auth.get("key_id") if auth else None,
            **extra_kwargs,
        )
        try:
            first_chunk = await stream_gen.__anext__()
        except StopAsyncIteration:
            first_chunk = None
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"TTS stream error ({provider or model})")
            err_msg = str(e)
            status_code = 429 if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg else 500
            raise HTTPException(status_code=status_code, detail=err_msg)

        async def audio_stream_generator():
            try:
                if first_chunk is not None:
                    yield first_chunk
                async for chunk in stream_gen:
                    yield chunk
            except Exception as e:
                logger.exception("Error in TTS streaming generation mid-transmission")
                raise

        media_type = "audio/pcm"
        headers = {
            "Content-Disposition": 'inline; filename="speech.pcm"',
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Channels": "1",
            "X-Audio-Bits-Per-Sample": "16",
        }

        if first_chunk:
            if first_chunk[:4] == b"RIFF" and len(first_chunk) >= 12 and first_chunk[8:12] == b"WAVE":
                media_type = "audio/wav"
                headers = {"Content-Disposition": 'inline; filename="speech.wav"'}
            elif first_chunk[:3] == b"ID3" or (len(first_chunk) >= 2 and first_chunk[0] == 0xFF and (first_chunk[1] & 0xE0) == 0xE0):
                media_type = "audio/mpeg"
                headers = {"Content-Disposition": 'inline; filename="speech.mp3"'}

        return StreamingResponse(
            audio_stream_generator(),
            media_type=media_type,
            headers=headers,
        )

    try:
        audio_bytes, content_type, metrics = await run_with_disconnect_check(
            request,
            dynamic_router.run_speech(
                provider=provider,
                model=model,
                input_text=input_text,
                voice=voice,
                api_key=api_key,
                auth_header=auth_header,
                key_id=auth.get("key_id") if auth else None,
                **extra_kwargs,
            )
        )
        audio_bytes = finalize_buffered_wav(audio_bytes)
        extension = {
            'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3', 'audio/ogg': 'ogg', 'audio/aac': 'aac',
            'audio/flac': 'flac', 'audio/pcm': 'pcm',
        }.get(content_type.split(';', 1)[0].strip().lower(), 'audio')
        return Response(
            content=audio_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="speech.{extension}"',
                "X-Orion-Metrics": json.dumps(metrics),
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"TTS error ({provider or model})")
        err_msg = str(e)
        status_code = 429 if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg else 500
        raise HTTPException(status_code=status_code, detail=err_msg)
