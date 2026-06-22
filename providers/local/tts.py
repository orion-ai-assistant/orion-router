import httpx
import logging
from providers.base import BaseTTS
from core.config import TTS_HOST, TTS_PORT

logger = logging.getLogger("service-router.local.tts")

class LocalTTSProvider(BaseTTS):

    def get_voices(self) -> list[str]:
        """Yerel TTS motorundan klonlanmış sesleri döner."""
        cloned_voices = []
        try:
            import httpx
            res = httpx.get(f"http://{TTS_HOST}:{TTS_PORT}/v1/voices", timeout=1.5)
            if res.status_code == 200:
                data = res.json()
                cloned_voices = data.get("voices", [])
        except Exception as e:
            logger.debug(f"Could not fetch cloned voices from local TTS: {e}")

        return [v for v in cloned_voices if v.lower() != "none"]

    def get_languages(self) -> list[str]:
        """Yerel TTS motorundan desteklenen dilleri döner."""
        try:
            import httpx
            res = httpx.get(f"http://{TTS_HOST}:{TTS_PORT}/v1/languages", timeout=1.5)
            if res.status_code == 200:
                data = res.json()
                return data.get("languages", [])
        except Exception as e:
            logger.debug(f"Could not fetch languages from local TTS: {e}")
        return ["Turkish", "English"]

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

        tts_instruct = kwargs.get("tts_instruct")
        
        if tts_instruct is not None:
            # Dashboard / direct API with tts_instruct
            payload_model = tts_instruct
            payload_voice = voice if voice and voice != "None" else ""
        else:
            # Fallback for standard OpenAI requests (e.g. OpenAI client)
            instructs = [
                "american accent", "australian accent", "british accent", "canadian accent", 
                "child", "chinese accent", "elderly", "female", "high pitch", "indian accent", 
                "japanese accent", "korean accent", "low pitch", "male", "middle-aged", 
                "moderate pitch", "portuguese accent", "russian accent", "teenager", 
                "very high pitch", "very low pitch", "whisper", "young adult"
            ]
            
            target_voice = voice or ""
            is_voice_instruct = any(inst in target_voice for inst in instructs) if target_voice else False
            
            if is_voice_instruct:
                payload_model = target_voice
                payload_voice = ""
            else:
                if model not in ("local", "test"):
                    payload_model = model
                else:
                    payload_model = ""
                payload_voice = voice if voice and voice != "None" else ""

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

        logger.info(f"Generating Local TTS: model={model}, voice={voice}, url={url}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload)
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
