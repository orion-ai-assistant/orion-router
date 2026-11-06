import httpx
import logging
from providers.base import BaseTTS
from core.availability import available, not_listening, unavailable
from core.config import TTS_HOST, TTS_PORT
from core.http_client import get_http_client
from core.model_catalog import bundled_model

logger = logging.getLogger("service-router.local.tts")
TTS_SERVICE = "Local text-to-speech service"
_LOCAL_TTS_NAMES = {bundled_model("local", "tts")["name"]}

class LocalTTSProvider(BaseTTS):

    def get_voices(self) -> list[str]:
        """Yerel TTS motorundan klonlanmış sesleri döner."""
        cloned_voices = []
        if not_listening(TTS_HOST, TTS_PORT):
            return []  # The service is off: no 2 s wait for a refused connection (core.availability).
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
        if not_listening(TTS_HOST, TTS_PORT):
            return []  # The service is off: no 2 s wait for a refused connection (core.availability).
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

    @staticmethod
    def _foreign_voice(payload: dict, status: int, detail: str) -> bool:
        """The service refused a saved voice that was made for another engine (switching OmniVoice and VoxCPM2
        leaves it in the settings): the request is then made again without it, with the engine's own voice."""
        return bool(status == 400 and payload.get("voice") and "uyumlu değil" in detail)

    def _payload(self, model: str, input_text: str, voice: str | None, kwargs: dict) -> dict:
        """The local TTS service's request, the same with or without streaming."""
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
            kwargs.get("guidance_scale") or kwargs.get("guidance"), None
        )
        # The "temperature" of a speech request is its creativity (0-2); the TTS service lines it up with its
        # engine's own guidance range (VoxCPM2: 2-4). Not given: the engine's own default.
        creativity_val = safe_float(kwargs.get("temperature"), None) if guidance_val is None else None
        steps_val = safe_int(kwargs.get("steps"), None)  # not given: the TTS service's engine default
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
            "stream": False
        }
        if steps_val is not None:
            payload["steps"] = steps_val
        if guidance_val is not None:
            payload["guidance_scale"] = guidance_val
        elif creativity_val is not None:
            payload["creativity"] = creativity_val
        if tts_instruct and not has_persona:
            payload["instructions"] = tts_instruct
        return payload

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
        payload = self._payload(model, input_text, voice, kwargs)

        logger.info(f"Generating Local TTS: model={model}, voice={voice}, url={url}")

        client = get_http_client(timeout=120.0)
        try:
            response = await client.post(url, json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            unavailable(TTS_SERVICE, e)  # Not running: a state, logged once; tried again with every request.
            raise RuntimeError(f"Could not connect to local TTS service ({TTS_HOST}:{TTS_PORT}).")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to local TTS server: {e}")
            raise RuntimeError(f"Local TTS Service Unreachable: {e}")
        available(TTS_SERVICE)

        if self._foreign_voice(payload, response.status_code, response.text):
            logger.warning(f"Voice '{payload['voice']}' is not for the running TTS engine; using its own voice")
            payload["voice"] = ""
            response = await client.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Local TTS API Error: {response.text}")
            raise RuntimeError(f"Local TTS API Error: {response.status_code} - {response.text}")
        
        audio_bytes = response.content
        content_type = response.headers.get("content-type", "audio/wav")
            
        # Basit kullanım istatistiği dönüyoruz
        usage_dict = {
            "prompt_tokens": max(1, len(input_text)),
            "completion_tokens": max(1, len(audio_bytes) // 100) if audio_bytes else 0
        }
        if payload["response_format"] == "pcm":
            # Raw PCM must be explicitly described by the local engine.
            rate = response.headers.get("x-audio-sample-rate") or response.headers.get("x-sample-rate")
            channels = response.headers.get("x-audio-channels", "")
            sample_format = response.headers.get("x-audio-format", "")
            widths = {"u8": 1, "s16le": 2, "s24le": 3, "s32le": 4, "f32le": 4, "f64le": 8}
            if rate and rate.isdigit() and channels.isdigit() and sample_format in widths:
                usage_dict["audio_format"] = {"format": sample_format, "sample_rate": int(rate),
                    "channels": int(channels), "sample_width": widths[sample_format]}

        logger.info(f"Local TTS complete: {len(audio_bytes)} bytes WAV")
        return audio_bytes, content_type, usage_dict

    async def generate_speech_stream(
        self,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ):
        """Passes the audio on as the local TTS service makes it. An engine that streams (VoxCPM2) sends raw
        24 kHz 16-bit mono PCM pieces from the first words on; one that does not (OmniVoice) answers with one
        whole WAV, which goes on as it is (the stream is then labelled audio/wav). Only a caller that asked for
        PCM gets the raw stream: any other format is the whole file, as before."""
        if str(kwargs.get("response_format") or "").lower() not in ("pcm", "s16le"):
            async for chunk in super().generate_speech_stream(model, input_text, voice, api_key, auth_header, **kwargs):
                yield chunk
            return

        url = f"http://{TTS_HOST}:{TTS_PORT}/v1/audio/speech"
        payload = self._payload(model, input_text, voice, dict(kwargs, response_format="pcm"))
        payload["stream"] = True
        logger.info(f"Generating Local TTS stream: model={model}, voice={voice}, url={url}")

        client = get_http_client(timeout=120.0)
        try:
            response = await client.send(client.build_request("POST", url, json=payload), stream=True)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            unavailable(TTS_SERVICE, e)
            raise RuntimeError(f"Could not connect to local TTS service ({TTS_HOST}:{TTS_PORT}).")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to local TTS server: {e}")
            raise RuntimeError(f"Local TTS Service Unreachable: {e}")
        available(TTS_SERVICE)

        try:
            if response.status_code != 200:
                detail = (await response.aread()).decode(errors="ignore")
                if self._foreign_voice(payload, response.status_code, detail):
                    logger.warning(f"Voice '{payload['voice']}' is not for the running TTS engine; using its own voice")
                    await response.aclose()
                    payload["voice"] = ""
                    response = await client.send(client.build_request("POST", url, json=payload), stream=True)
                    detail = "" if response.status_code == 200 else (await response.aread()).decode(errors="ignore")
            if response.status_code != 200:
                logger.error(f"Local TTS API Error: {detail}")
                raise RuntimeError(f"Local TTS API Error: {response.status_code} - {detail}")
            content_type = response.headers.get("content-type", "audio/wav")
            callback = kwargs.get("_archive_metadata")
            if "pcm" in content_type:
                rate = response.headers.get("x-sample-rate", "")
                rate = int(rate) if rate.isdigit() else 24000
                if rate != 24000:  # The Router labels every PCM stream 24 kHz (core/audio_container.py).
                    logger.warning(f"Local TTS streams {rate} Hz PCM; it is passed on labelled 24000 Hz")
                if callback:
                    callback({"format": "s16le", "sample_rate": rate, "channels": 1, "sample_width": 2})
            elif callback:
                callback({"content_type": content_type})
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await response.aclose()
