"""
api/transcriptions.py
---------------------
OpenAI uyumlu ses transkripsiyonu (Speech-to-Text) endpoint'i.
Tüm yönlendirme ve fallback mantığı DynamicLLMRouter üzerinden yürütülür.
"""
import asyncio
import logging
import urllib.parse
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.websockets import WebSocketState
import websockets

from core.config import STT_HOST, STT_PORT
from core.dependencies import authenticate_request, authenticate_websocket
from core.utils import run_with_disconnect_check
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.transcriptions")

router = APIRouter(tags=["Audio", "Transcriptions"])


@router.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("whisper-small-finetuned-tr"),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
    temperature: float | None = Form(None),
    auth: dict = Depends(authenticate_request),
):
    """OpenAI standardında ses dosyasını metne dönüştürür (Speech-to-Text).

    Desteklenen form alanları:
      - file: Transcribe edilecek ses dosyası (WAV, MP3, OGG, FLAC, M4A, WebM vb.)
      - model: Hedef STT modeli (Varsayılan: whisper-small-finetuned-tr)
      - language: Hedef dil kodu (örn: 'tr', 'en')
      - prompt: Whisper'a ipucu / bağlam metni
      - response_format: 'json', 'text', 'verbose_json'
      - temperature: Sampling sıcaklığı
    """
    provider = request.headers.get("x-orion-provider")
    api_key = request.headers.get("x-orion-api-key")
    auth_header = request.headers.get("authorization")

    # Dosya baytlarını oku
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded audio file: {e}")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    filename = file.filename or "audio.wav"
    target_model = (model or "whisper-small-finetuned-tr").strip()

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router

    try:
        result = await run_with_disconnect_check(
            request,
            dynamic_router.run_transcription(
                provider=provider,
                model=target_model,
                file_bytes=file_bytes,
                filename=filename,
                language=language,
                prompt=prompt,
                response_format=response_format,
                temperature=temperature,
                api_key=api_key,
                auth_header=auth_header,
                key_id=auth.get("key_id") if auth else None,
            ),
        )

        if response_format == "text":
            return PlainTextResponse(content=result.get("text", ""))

        return JSONResponse(content=result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e)
        status_code = 500
        if "429" in err_str or "rate limit" in err_str.lower() or "too many requests" in err_str.lower():
            status_code = 429
        elif "401" in err_str or "unauthorized" in err_str.lower() or "invalid api key" in err_str.lower():
            status_code = 401
        logger.error(f"Transcription error ({provider or target_model}): [{status_code}] {err_str}")
        raise HTTPException(status_code=status_code, detail=err_str)


@router.websocket("/v1/audio/transcriptions/stream")
async def audio_transcriptions_stream(
    websocket: WebSocket,
    language: str | None = None,
    prompt: str | None = None,
    auth: dict = Depends(authenticate_websocket),
):
    """Canlı ses transkripsiyonu (Streaming STT) için WebSocket köprüsü.

    İstemciden (tarayıcı/mikrofon) gelen 16 kHz Mono PCM baytlarını yerel
    Whisper STT mikroservisine yönlendirir ve modelden dönen canlı ("live")
    ve nihai ("final") transkripsiyonları istemciye iletir.
    """
    await websocket.accept()

    # Query parametrelerini hazırla
    params = {}
    if language and language.strip():
        params["language"] = language.strip()
    if prompt and prompt.strip():
        params["prompt"] = prompt.strip()

    query_str = f"?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}" if params else ""
    backend_url = f"ws://{STT_HOST}:{STT_PORT}/v1/audio/transcriptions/stream{query_str}"

    try:
        async with websockets.connect(backend_url) as backend_ws:
            key_repr = auth.get("name") or auth.get("source") or "authenticated"
            logger.info(f"WebSocket STT streaming started for '{key_repr}', proxied to {backend_url}")

            async def client_to_backend():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"]:
                            await backend_ws.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            await backend_ws.send(msg["text"])
                except WebSocketDisconnect:
                    pass
                except Exception as err:
                    logger.debug(f"Client to backend stream finished: {err}")

            async def backend_to_client():
                try:
                    async for msg in backend_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        elif isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                except Exception as err:
                    logger.debug(f"Backend to client stream finished: {err}")

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_backend()),
                    asyncio.create_task(backend_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except (ConnectionRefusedError, OSError, websockets.exceptions.WebSocketException) as e:
        logger.error(f"Failed to connect to local Whisper STT at {backend_url}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Yerel STT servisine bağlanılamadı ({STT_HOST}:{STT_PORT}). Lütfen Whisper servisinin aktif olduğundan emin olun."
            })
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
        return
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
        logger.info("WebSocket STT streaming closed cleanly.")

