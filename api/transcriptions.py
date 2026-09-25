"""
api/transcriptions.py
---------------------
OpenAI uyumlu ses transkripsiyonu (Speech-to-Text) endpoint'i.
Tüm yönlendirme ve fallback mantığı DynamicLLMRouter üzerinden yürütülür.
"""
import asyncio
from datetime import datetime
import json
import logging
import time
import urllib.parse
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.websockets import WebSocketState
import websockets

from core.config import STT_HOST, STT_PORT
from core.dependencies import authenticate_request, authenticate_websocket
from core.model_catalog import bundled_model
from core.utils import run_with_disconnect_check
from database import db_manager
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.transcriptions")

router = APIRouter(tags=["Audio", "Transcriptions"])
LOCAL_STT_MODEL = bundled_model("local", "stt")


@router.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(LOCAL_STT_MODEL["name"]),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
    temperature: float | None = Form(None),
    auth: dict = Depends(authenticate_request),
):
    """OpenAI standardında ses dosyasını metne dönüştürür (Speech-to-Text).

    Desteklenen form alanları:
      - file: Transcribe edilecek ses dosyası (WAV, MP3, OGG, FLAC, M4A, WebM vb.)
      - model: Hedef STT modeli (varsayılan model katalogdan alınır)
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
    target_model = (model or LOCAL_STT_MODEL["name"]).strip()

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
    Ayrıca oturum metriklerini ve zaman etiketli segmentleri router_request_logs tablosuna kaydeder.
    """
    await websocket.accept()

    session_start_time = time.time()
    segments = []
    bytes_received = 0
    chunks_count = 0
    err_message = None
    log_id = None

    # Query parametrelerini hazırla
    params = {}
    if language and language.strip():
        params["language"] = language.strip()
    if prompt and prompt.strip():
        params["prompt"] = prompt.strip()

    query_str = f"?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}" if params else ""
    backend_url = f"ws://{STT_HOST}:{STT_PORT}/v1/audio/transcriptions/stream{query_str}"

    # 1. Başlangıçta canlı akış log kaydını oluştur (Status: streaming / İşleniyor)
    req_payload = {
        "type": "streaming",
        "protocol": "websocket",
        "endpoint": "/v1/audio/transcriptions/stream",
        "model": LOCAL_STT_MODEL["name"],
        "language": language or "tr",
        "prompt": prompt or None,
    }
    try:
        log_id = await db_manager.create_streaming_log(
            key_id=auth.get("key_id"),
            provider="local",
            model=LOCAL_STT_MODEL["name"],
            request_json=json.dumps(req_payload, ensure_ascii=False),
            response_json=json.dumps({
                "text": "",
                "status": "streaming",
                "segments": [],
            }, ensure_ascii=False),
            capability="stt",
            status="streaming",
        )
    except Exception as log_err:
        logger.warning(f"Failed to create initial streaming log: {log_err}")

    try:
        async with websockets.connect(backend_url) as backend_ws:
            key_repr = auth.get("name") or auth.get("source") or "authenticated"
            logger.info(f"WebSocket STT streaming started for '{key_repr}', proxied to {backend_url}")

            async def client_to_backend():
                nonlocal bytes_received, chunks_count
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"]:
                            bytes_received += len(msg["bytes"])
                            chunks_count += 1
                            await backend_ws.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            try:
                                control = json.loads(msg["text"])
                            except (TypeError, json.JSONDecodeError):
                                control = None
                            if isinstance(control, dict) and control.get("type") == "stop":
                                await backend_ws.close()
                                break
                            await backend_ws.send(msg["text"])
                except WebSocketDisconnect:
                    pass
                except Exception as err:
                    logger.debug(f"Client to backend stream finished: {err}")

            async def backend_to_client():
                nonlocal segments
                try:
                    async for msg in backend_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                            try:
                                parsed = json.loads(msg)
                                if isinstance(parsed, dict) and parsed.get("type") == "final":
                                    seg_text = (parsed.get("text") or "").strip()
                                    if seg_text:
                                        seg_duration = parsed.get("duration", 0.0)
                                        now_str = datetime.now().strftime("%H:%M:%S")
                                        rel_time = round(time.time() - session_start_time, 2)
                                        seg_item = {
                                            "id": len(segments) + 1,
                                            "text": seg_text,
                                            "duration": round(float(seg_duration), 2) if seg_duration else 0.0,
                                            "timestamp": now_str,
                                            "relative_time": rel_time,
                                            "language": parsed.get("language") or language or "tr",
                                        }
                                        segments.append(seg_item)
                                        if log_id:
                                            full_txt = " ".join(s["text"] for s in segments)
                                            intermediate_resp = {
                                                "text": full_txt,
                                                "status": "streaming",
                                                "language": language or "tr",
                                                "total_segments": len(segments),
                                                "segments": segments,
                                            }
                                            asyncio.create_task(
                                                db_manager.update_streaming_log(
                                                    log_id=log_id,
                                                    response_json=json.dumps(intermediate_resp, ensure_ascii=False),
                                                    status="streaming",
                                                    success=None,
                                                )
                                            )
                            except Exception:
                                pass
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
        err_message = str(e)
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
    except Exception as e:
        err_message = str(e)
        logger.error(f"Unexpected error during STT stream: {e}")
    finally:
        # Oturum bittiğinde nihai log kaydını güncelle
        if log_id:
            try:
                session_duration = round(time.time() - session_start_time, 2)
                full_text = " ".join(s["text"] for s in segments)

                # Token eşdeğeri hesaplama (dosya tabanlı STT ile uyumlu: süre * 25 ve kelime sayısı)
                prompt_tokens = int(session_duration * 25) if session_duration > 0 else max(1, bytes_received // 3200)
                completion_tokens = len(full_text.split()) if full_text else 0
                tokens_used = prompt_tokens + completion_tokens

                # Fiyatlandırma ve maliyet
                pricing_cache = getattr(websocket.app.state, "pricing_cache", {})
                prices = pricing_cache.get(LOCAL_STT_MODEL["name"], {})
                # Fiyatlar 1M token başına; birim maliyete çevirmek için 1_000_000'a bölüyoruz.
                p_cost = (prompt_tokens or 0) / 1_000_000 * (prices.get("input") or 0.0)
                c_cost = (completion_tokens or 0) / 1_000_000 * (prices.get("output") or 0.0)
                cost = p_cost + c_cost

                # Durum belirleme
                is_clean_close = err_message is None
                final_status = "success" if is_clean_close else ("interrupted" if segments else "failed")
                is_success = True if is_clean_close else False

                final_resp = {
                    "text": full_text,
                    "duration": session_duration,
                    "language": language or "tr",
                    "total_segments": len(segments),
                    "bytes_received": bytes_received,
                    "chunks_count": chunks_count,
                    "segments": segments,
                    "metrics": {
                        "total_duration_ms": round(session_duration * 1000, 2)
                    }
                }
                if err_message:
                    final_resp["error"] = err_message

                await db_manager.update_streaming_log(
                    log_id=log_id,
                    response_json=json.dumps(final_resp, ensure_ascii=False),
                    status=final_status,
                    success=is_success,
                    tokens_used=tokens_used,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost,
                    key_id=auth.get("key_id"),
                    duration_ms=round(session_duration * 1000, 2)
                )
                logger.info(
                    f"WebSocket STT session #{log_id} finalized: status={final_status}, "
                    f"duration={session_duration}s, segments={len(segments)}, tokens={tokens_used}"
                )
            except Exception as upd_err:
                logger.error(f"Failed to finalize streaming log #{log_id}: {upd_err}")

        # Stop sonrasında istemci bağlantıyı kapatmadan önce son süre JSON'unu alabilsin.
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                final_duration = round(time.time() - session_start_time, 2)
                await websocket.send_json({
                    "type": "metrics",
                    "text": " ".join(s["text"] for s in segments),
                    "status": "interrupted" if err_message else "success",
                    "metrics": {"total_duration_ms": round(final_duration * 1000, 2)},
                })
            except Exception as metrics_err:
                logger.debug(f"Could not send final STT metrics to client: {metrics_err}")

        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass

        logger.info("WebSocket STT streaming closed cleanly.")
