"""
api/transcriptions.py
---------------------
OpenAI uyumlu ses transkripsiyonu (Speech-to-Text) endpoint'i.
Tüm yönlendirme ve fallback mantığı DynamicLLMRouter üzerinden yürütülür.
"""
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from core.dependencies import authenticate_request
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
