"""
providers/openai/tts.py
------------------------
OpenAI Text-to-Speech provider.
"""
import httpx
import logging

from providers.base import BaseTTS

_BASE_URL = "https://api.openai.com"

logger = logging.getLogger("service-router.openai.tts")


class OpenAITTSProvider(BaseTTS):


    def get_voices(self) -> list[str]:
        """OpenAI tarafından desteklenen seslerin listesini döner."""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    async def generate_speech(
        self,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> tuple[bytes, str, dict]:
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )

        if not resolved_key:
            raise ValueError("OpenAI TTS Error: No API key provided.")

        if not model:
            raise ValueError("OpenAI TTS Error: Model name is required.")

        voice_name = voice or self.get_voices()[0]
        url = f"{_BASE_URL}/v1/audio/speech"

        headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "input": input_text,
            "voice": voice_name,
        }

        # OpenAI TTS yalnızca response_format ve speed'i destekler
        for key in ("response_format", "speed"):
            if kwargs.get(key) is not None:
                payload[key] = kwargs[key]

        logger.info(f"Generating OpenAI TTS: model={model}, voice={voice_name}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                err_detail = response.read().decode(errors="ignore")
                raise RuntimeError(f"OpenAI TTS API Error {response.status_code}: {err_detail}")

            content_type = response.headers.get("content-type", "audio/mpeg")
            audio_bytes = response.content

            # OpenAI TTS sadece girdi karakter sayısı üzerinden faturalandırır,
            # çıktı (ses) için ayrı ücret yoktur.
            character_count = len(input_text)
            usage_dict = {
                "prompt_tokens": character_count,
                "completion_tokens": 0,
            }

            logger.info(
                f"OpenAI TTS complete: {len(audio_bytes)} bytes, format={content_type} "
                f"(Billed characters: {character_count})"
            )
            return audio_bytes, content_type, usage_dict
