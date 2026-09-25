import httpx
import logging
from providers.base import BaseTTS
from core.config import TTS_HOST, TTS_PORT
from core.http_client import get_http_client
from core.model_catalog import bundled_model

logger = logging.getLogger("service-router.local.tts")
_LOCAL_TTS_NAMES = {bundled_model("local", "tts")["name"]}

class LocalTTSProvider(BaseTTS):

    def get_voices(self) -> list[str]:
        """Yerel TTS motorundan klonlanmış sesleri döner."""
        cloned_voices = []
        try:
            import httpx
            res = httpx.get(f"http://{TTS_HOST}:{TTS_PORT}/v1/voices", timeout=1.0)
            if res.status_code == 200:
                data = res.json()
                cloned_voices = data.get("voices", [])
        except Exception as e:
            logger.debug(f"Could not fetch cloned voices from local TTS: {e}")

        return [v for v in cloned_voices if v.lower() != "none"]

    _cached_languages = None

    def get_languages(self) -> list[str]:
        """Yerel TTS motorundan desteklenen dilleri döner (statik liste önbelleklenir)."""
        if self._cached_languages:
            return self._cached_languages
        try:
            import httpx
            res = httpx.get(f"http://{TTS_HOST}:{TTS_PORT}/v1/languages", timeout=1.5)
            if res.status_code == 200:
                data = res.json()
                langs = data.get("languages", [])
                if langs:
                    self._cached_languages = langs
                return langs
        except Exception as e:
            logger.debug(f"Could not fetch languages from local TTS: {e}")
        return []

    async def generate_speech(
        self,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> tuple[bytes, str, dict]:
        
        url = f"http://{TTS_HOST}:{TTS_PORT}/v1/audio/speech"
        
        def safe_float(val, default):
            if val is None or val == "":
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        def safe_int(val, default):
            if val is None or val == "":
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        tts_instruct = kwargs.get("tts_instruct") or kwargs.get("instructions")
        if not tts_instruct:
            instructs = []
            for field in ("gender", "age", "pitch", "style", "accent", "dialect"):
                val = kwargs.get(field)
                if val and str(val).strip() and str(val).strip().lower() != "auto":
                    instructs.append(str(val).strip())
            if instructs:
                tts_instruct = ", ".join(instructs)

        has_persona = bool(voice and str(voice).strip() and str(voice).lower() not in ("none", "null", "default", "alloy"))
        payload_voice = voice if has_persona else ""

        if tts_instruct and not has_persona:
            payload_model = tts_instruct
        elif model not in _LOCAL_TTS_NAMES and model not in ("local", "test", "default", "none"):
            payload_model = model
        else:
            payload_model = ""

        speed_val = safe_float(kwargs.get("speed"), 1.0)
        guidance_val = safe_float(
            kwargs.get("guidance_scale") or kwargs.get("guidance") or kwargs.get("temperature"),
            2.0
        )
        steps_val = safe_int(kwargs.get("steps"), 15)
        seed_val = safe_int(kwargs.get("seed"), -1)
        lang_val = kwargs.get("language") or "Auto"

        payload = {
            "model": payload_model,
            "input": input_text,
            "voice": payload_voice,
            "response_format": kwargs.get("response_format", "wav"),
            "speed": speed_val,
            "language": lang_val,
            "seed": seed_val,
            "guidance_scale": guidance_val,
            "steps": steps_val,
            "stream": False
        }
        if tts_instruct and not has_persona:
            payload["instructions"] = tts_instruct

        logger.info(f"Generating Local TTS: model={model}, voice={voice}, url={url}")

        client = get_http_client(timeout=120.0)
        try:
            response = await client.post(url, json=payload)
        except httpx.ConnectError:
            raise RuntimeError(f"Yerel TTS servisine ({TTS_HOST}:{TTS_PORT}) bağlanılamadı. Lütfen OmniVoice/TTS servisinin açık olduğundan emin olun.")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to local TTS server: {e}")
            raise RuntimeError(f"Local TTS Service Unreachable: {e}")

        if response.status_code != 200:
            logger.error(f"Local TTS API Error: {response.text}")
            raise RuntimeError(f"Local TTS API Error: {response.status_code} - {response.text}")
        
        audio_bytes = response.content
        content_type = response.headers.get("content-type", "audio/wav")
            
        # Basit kullanım istatistiği dönüyoruz
        usage_dict = {
            "prompt_tokens": len(input_text),
            "completion_tokens": len(audio_bytes) // 100  # kaba bir tahmin
        }

        logger.info(f"Local TTS complete: {len(audio_bytes)} bytes WAV")
        return audio_bytes, content_type, usage_dict
