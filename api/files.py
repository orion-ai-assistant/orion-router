"""
api/files.py
------------
Dosya yükleme endpoint'i (video, görsel, ses vb.).

Yüklenen dosyalar provider'ın File API'sine gönderilir (şimdilik Gemini).
Dönen file_uri, sonraki chat isteklerinde mesaj içeriğinde kullanılabilir:

  {
    "role": "user",
    "content": [
      {"type": "text", "text": "Bu videoyu anlat"},
      {"type": "file_uri", "file_uri": "files/...", "mime_type": "video/mp4"}
    ]
  }
"""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from core.dependencies import authenticate_request
from dynamic_router import DynamicLLMRouter

logger = logging.getLogger("service-router.files")

router = APIRouter(tags=["Files"])

# Desteklenen MIME türleri
ALLOWED_MIME_TYPES = {
    # Video
    "video/mp4", "video/mpeg", "video/mov", "video/avi", "video/webm",
    "video/x-matroska", "video/3gpp",
    # Görsel
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
    # Ses
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/flac", "audio/aac",
    # Döküman
    "application/pdf", "text/plain",
}

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("/v1/files")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    provider: str = Form(default="gemini"),
    display_name: str = Form(default=""),
    auth: dict = Depends(authenticate_request),
):
    """Provider'a dosya yükler (video, görsel, ses, PDF).

    Form parametreleri:
      - file: Yüklenecek dosya
      - provider: Hedef provider (varsayılan: gemini)
      - display_name: Dosya için görüntülenecek isim (opsiyonel)

    Döner:
      {
        "file_uri": "files/...",
        "name": "files/...",
        "mime_type": "video/mp4",
        "display_name": "my_video.mp4",
        "state": "ACTIVE"
      }
    """
    # MIME türü kontrolü
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type: {mime_type}. "
                   f"Allowed: {sorted(ALLOWED_MIME_TYPES)}",
        )

    # Dosya içeriğini oku
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(file_bytes)} bytes. Max: {MAX_FILE_SIZE} bytes.",
        )

    name = display_name or file.filename or "uploaded_file"

    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router

    if provider not in dynamic_router.file_providers:
        raise HTTPException(
            status_code=400,
            detail=f"File upload not supported for provider '{provider}'. "
                   f"Available: {list(dynamic_router.file_providers.keys())}",
        )

    try:
        result = await dynamic_router.upload_file(
            provider=provider,
            file_bytes=file_bytes,
            mime_type=mime_type,
            display_name=name,
        )
        return result
    except Exception as e:
        logger.exception(f"File upload error ({provider})")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/providers/capabilities")
async def get_provider_capabilities(request: Request):
    """Her provider için desteklenen yetenekleri listeler."""
    dynamic_router: DynamicLLMRouter = request.app.state.dynamic_router
    return dynamic_router.get_capabilities()
