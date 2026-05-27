"""
providers/gemini/files.py
-------------------------
Gemini File API aracılığıyla dosya yükleme.
Video, görsel, ses ve döküman dosyalarını Gemini'nin kalıcı depolama alanına yükler.

Yüklenen dosyalar, chat isteklerinde `file_uri` olarak referans gösterilebilir:
  {
    "role": "user",
    "content": [
      {"type": "text", "text": "Bu videoyu açıkla"},
      {"type": "file_uri", "file_uri": "files/...", "mime_type": "video/mp4"}
    ]
  }

Önemli: Video dosyaları yüklendikten sonra Gemini tarafında işlenmeyi bekler.
`state` alanı ACTIVE olana kadar chat'te kullanılamaz.
"""
import io
import logging
import asyncio

from google import genai
from google.genai import types

from providers.base import BaseFileUpload


logger = logging.getLogger("service-router.gemini.files")

# Dosya işlenmesini beklerken kullanılan polling aralığı (saniye)
_POLL_INTERVAL = 2
_POLL_TIMEOUT = 120  # maksimum bekleme süresi


class GeminiFileProvider(BaseFileUpload):
    provider_name = "gemini"

    async def upload_file(
        self,
        file_bytes: bytes,
        mime_type: str,
        display_name: str,
        api_key: str | None = None,
    ) -> dict:
        if not api_key:
            raise ValueError("Gemini File Upload Error: No API key provided.")

        client = genai.Client(api_key=api_key)

        logger.info(
            f"Uploading file to Gemini File API: name={display_name}, "
            f"mime={mime_type}, size={len(file_bytes)} bytes"
        )

        # Dosyayı yükle
        upload_config = types.UploadFileConfig(
            mime_type=mime_type,
            display_name=display_name,
        )
        file_obj = await client.aio.files.upload(
            file=io.BytesIO(file_bytes),
            config=upload_config,
        )

        logger.info(f"File uploaded: uri={file_obj.uri}, state={file_obj.state}")

        # Video gibi dosyalar için ACTIVE durumunu bekle
        if hasattr(file_obj, "state") and str(file_obj.state) not in ("FileState.ACTIVE", "ACTIVE"):
            elapsed = 0
            while elapsed < _POLL_TIMEOUT:
                await asyncio.sleep(_POLL_INTERVAL)
                elapsed += _POLL_INTERVAL
                refreshed = await client.aio.files.get(name=file_obj.name)
                state_str = str(refreshed.state)
                logger.info(f"File state: {state_str} (waited {elapsed}s)")
                if "ACTIVE" in state_str:
                    file_obj = refreshed
                    break
                if "FAILED" in state_str:
                    raise RuntimeError(f"Gemini file processing failed: {file_obj.name}")
            else:
                logger.warning(
                    f"File {file_obj.name} did not become ACTIVE within {_POLL_TIMEOUT}s"
                )

        return {
            "file_uri": file_obj.uri,
            "name": file_obj.name,
            "mime_type": file_obj.mime_type,
            "display_name": getattr(file_obj, "display_name", display_name),
            "state": str(getattr(file_obj, "state", "ACTIVE")),
        }
