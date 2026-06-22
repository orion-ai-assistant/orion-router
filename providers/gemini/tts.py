"""
providers/gemini/tts.py
-----------------------
Google Gemini Text-to-Speech provider.

Gemini, sesi PCM formatında döner. Bu modül PCM'i WAV'a dönüştürüp
(bytes, "audio/wav") tuple'ı olarak döner.

Desteklenen sesler (Voice):
  Aoede, Charon, Fenrir, Kore, Leda, Orus, Puck, Sulafat, Zephyr

Varsayılan model: gemini-3.1-flash-tts-preview
PCM parametreleri: 24000 Hz, 16-bit, mono
"""
import io
import logging
import wave

from google import genai
from google.genai import types

from providers.base import BaseTTS


logger = logging.getLogger("service-router.gemini.tts")

# PCM audio parametreleri (Gemini sabit döner)
PCM_CHANNELS = 1
PCM_SAMPLE_RATE = 24000
PCM_SAMPLE_WIDTH = 2  # 16-bit


def _pcm_to_wav(pcm_data: bytes) -> bytes:
    """Ham PCM verisini bellekte WAV dosyasına dönüştürür."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(PCM_CHANNELS)
        wf.setsampwidth(PCM_SAMPLE_WIDTH)
        wf.setframerate(PCM_SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return buffer.getvalue()


def _build_tts_contents(input_text: str) -> list[types.Content]:
    """Gemini TTS resmi formatı — 2.5 ve 3.1 modelleri için ortak."""
    return [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=f"## Transcript:\n{input_text}"),
            ],
        ),
    ]


def _extract_audio_from_response(response) -> bytes:
    """Tüm candidate/part'ları tarayıp inline_data ses parçalarını birleştirir."""
    audio_chunks: list[bytes] = []
    text_parts: list[str] = []

    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                audio_chunks.append(inline_data.data)
                continue

            text = getattr(part, "text", None)
            if text:
                text_parts.append(text)

    if not audio_chunks:
        detail = ""
        if text_parts:
            preview = " ".join(text_parts)[:200]
            detail = f" Text parts returned: {preview!r}"
        raise RuntimeError(
            "Gemini TTS Error: Model did not return any audio data." + detail
        )

    if text_parts:
        logger.debug(
            "Gemini TTS: skipped %d text part(s); found audio in part index >= 0.",
            len(text_parts),
        )

    return b"".join(audio_chunks)


class GeminiTTSProvider(BaseTTS):


    def get_voices(self) -> list[str]:
        """Gemini tarafından desteklenen prebuilt seslerin listesini döner."""
        return [
            "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe",
            "Callirrhoe", "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux",
            "Iapetus", "Kore", "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima",
            "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Sulafat", "Umbriel",
            "Vindemiatrix", "Zephyr", "Zubenelgenubi"
        ]

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
            raise ValueError("Gemini TTS Error: No API key provided.")
        if not model:
            raise ValueError("Gemini TTS Error: Model name is required.")

        client = genai.Client(api_key=resolved_key)
        voice_name = voice or self.get_voices()[0]

        # Temperature: güvenli parse — geçersiz değer gelirse loglanıp atlanır
        config_kwargs: dict = {}
        raw_temp = kwargs.get("temperature")
        if raw_temp is not None:
            try:
                config_kwargs["temperature"] = float(raw_temp)
            except (ValueError, TypeError):
                logger.warning(f"Gemini TTS: Invalid temperature value '{raw_temp}', ignoring.")

        logger.info(f"Generating Gemini TTS: model={model}, voice={voice_name}, temperature={config_kwargs.get('temperature')}")

        config = types.GenerateContentConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
            **config_kwargs,
        )

        response = await client.aio.models.generate_content(
            model=model,
            contents=_build_tts_contents(input_text),
            config=config,
        )

        pcm_data = _extract_audio_from_response(response)
        wav_bytes = _pcm_to_wav(pcm_data)

        prompt_tokens = 0
        completion_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0

        usage_dict = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

        logger.info(f"Gemini TTS complete: {len(wav_bytes)} bytes WAV (In tokens: {prompt_tokens}, Out tokens: {completion_tokens})")
        return wav_bytes, "audio/wav", usage_dict

