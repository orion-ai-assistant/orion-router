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
from providers.gemini.client import get_gemini_client


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


from core.http_client import get_http_client

# Klasik popüler astronomik sesler (Gemini 3.1 & 2.x modelleri)
CLASSIC_GEMINI_VOICES = [
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe",
    "Callirrhoe", "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux",
    "Iapetus", "Kore", "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima",
    "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Sulafat", "Umbriel",
    "Vindemiatrix", "Zephyr", "Zubenelgenubi",
]

# Yeni nesil Gemini 3.8+ sesleri
NEW_GEMINI_VOICES = [
    "Arlo", "Bodi", "Brio", "Cleo", "Cruz", "Daro", "Elio", "Enya", "Enzo",
    "Finn", "Fola", "Gero", "Hali", "Jett", "Jori", "Kira", "Knox", "Koda",
    "Lora", "Ludo", "Lumi", "Mako", "Milo", "Neno", "Nika", "Nyla", "Olin",
    "Rami", "Riko", "Rina", "Sami", "Sola", "Tari", "Tavi", "Tova", "Varo",
    "Veda", "Zali", "Zeno", "Zuri",
]

_FALLBACK_VOICES = CLASSIC_GEMINI_VOICES + NEW_GEMINI_VOICES

# Aynı sesleri paylaşan modeller için grup tanımları
MODEL_VOICE_GROUPS = [
    {
        "group_id": "gemini_preview_3_1",
        "label": "Gemini 3.1 & 2.x Önizleme Modelleri",
        "models": ["gemini-3.1-flash-tts-preview", "gemini-2.0-flash-preview", "gemini-2.5-flash-preview"],
        "match_patterns": ["3.1", "2.0", "2.5", "1.5"],
        "voices": CLASSIC_GEMINI_VOICES,
    },
    {
        "group_id": "gemini_modern_3_8",
        "label": "Gemini 3.8+ Güncel Modeller",
        "models": ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"],
        "match_patterns": ["3.8", "default"],
        "voices": _FALLBACK_VOICES,
    },
]


class GeminiTTSProvider(BaseTTS):

    def __init__(self):
        super().__init__()
        self._cached_voices: list[str] = list(_FALLBACK_VOICES)

    def get_voices(self, model: str | None = None) -> list[str]:
        """Gemini tarafından desteklenen seslerin listesini döner. Model verilirse modele özel grubu döner."""
        if model:
            model_lower = model.lower()
            for grp in MODEL_VOICE_GROUPS:
                if any(m.lower() == model_lower for m in grp.get("models", [])):
                    return list(grp["voices"])
                if any(p != "default" and p in model_lower for p in grp.get("match_patterns", [])):
                    return list(grp["voices"])
        return list(self._cached_voices)

    def get_model_voice_groups(self) -> list[dict]:
        """Model grupları ve desteklenen ses kümesini döner."""
        return [
            {
                "group_id": grp["group_id"],
                "label": grp["label"],
                "models": grp["models"],
                "match_patterns": grp["match_patterns"],
                "voices": list(grp["voices"]),
            }
            for grp in MODEL_VOICE_GROUPS
        ]

    async def fetch_remote_voices(self, api_key: str | None = None) -> list[str]:
        """Google Gemini Voices API (v1beta/voices) üzerinden tüm sesleri dinamik çeker ve önbelleğe alır."""
        resolved_key = self._resolve_api_key(api_key=api_key)
        if not resolved_key:
            return list(self._cached_voices)

        all_names: list[str] = []
        token = None
        client = get_http_client(timeout=15.0)

        try:
            while True:
                url = f"https://generativelanguage.googleapis.com/v1beta/voices?key={resolved_key}&pageSize=1000"
                if token:
                    url += f"&page_token={token}"
                res = await client.get(url)
                if res.status_code != 200:
                    logger.debug("Gemini voices API returned status %s: %s", res.status_code, res.text[:200])
                    break
                data = res.json()
                for v in data.get("voices", []):
                    name = v.get("display_name") or v.get("name") or v.get("id")
                    if name and name not in all_names:
                        all_names.append(name)
                token = data.get("next_page_token")
                if not token:
                    break

            if all_names:
                personas = [n for n in all_names if not any(role in n for role in ("Advisor", "Agent", "Voiceover", "Assistant", "Concierge", "Tutor", "Podcaster", "Storyteller"))]
                roles = [n for n in all_names if n not in personas]
                sorted_voices = sorted(personas) + sorted(roles)
                self._cached_voices = sorted_voices
                logger.info("Loaded %d dynamic Gemini voices from Google API.", len(sorted_voices))
        except Exception as exc:
            logger.warning("Could not dynamically load Gemini voices from Google API: %s", exc)

        return list(self._cached_voices)

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

        client = get_gemini_client(resolved_key)
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
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **config_kwargs,
        )

        # Google Gemini Audio unary çağrılarda 30sn bekletme yapabildiği için
        # generate_content_stream ile parça parça alıp birleştiriyoruz (~1 sn sürer).
        response_stream = await client.aio.models.generate_content_stream(
            model=model,
            contents=_build_tts_contents(input_text),
            config=config,
        )

        audio_chunks: list[bytes] = []
        text_parts: list[str] = []
        usage_metadata = None

        async for chunk in response_stream:
            if getattr(chunk, "usage_metadata", None):
                usage_metadata = chunk.usage_metadata
            for candidate in getattr(chunk, "candidates", None) or []:
                content = getattr(candidate, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", None) or []:
                    inline_data = getattr(part, "inline_data", None)
                    if inline_data and getattr(inline_data, "data", None):
                        audio_chunks.append(inline_data.data)
                    elif getattr(part, "text", None):
                        text_parts.append(part.text)

        if not audio_chunks:
            detail = ""
            if text_parts:
                preview = " ".join(text_parts)[:200]
                detail = f" Text parts returned: {preview!r}"
            raise RuntimeError(
                "Gemini TTS Error: Model did not return any audio data." + detail
            )

        pcm_data = b"".join(audio_chunks)
        wav_bytes = _pcm_to_wav(pcm_data)

        prompt_tokens = 0
        completion_tokens = 0
        if usage_metadata:
            prompt_tokens = usage_metadata.prompt_token_count or 0
            completion_tokens = usage_metadata.candidates_token_count or 0

        usage_dict = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

        logger.info(f"Gemini TTS complete: {len(wav_bytes)} bytes WAV (In tokens: {prompt_tokens}, Out tokens: {completion_tokens})")
        return wav_bytes, "audio/wav", usage_dict

    async def generate_speech_stream(
        self,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ):
        """Gemini TTS anlık akış (stream) üreteci. Ham PCM parçaları (24kHz, 16-bit, mono) anında yield eder."""
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )

        if not resolved_key:
            raise ValueError("Gemini TTS Error: No API key provided.")
        if not model:
            raise ValueError("Gemini TTS Error: Model name is required.")

        client = get_gemini_client(resolved_key)
        voice_name = voice or self.get_voices()[0]

        config_kwargs: dict = {}
        raw_temp = kwargs.get("temperature")
        if raw_temp is not None:
            try:
                config_kwargs["temperature"] = float(raw_temp)
            except (ValueError, TypeError):
                pass

        config = types.GenerateContentConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **config_kwargs,
        )

        response_stream = await client.aio.models.generate_content_stream(
            model=model,
            contents=_build_tts_contents(input_text),
            config=config,
        )

        async for chunk in response_stream:
            for candidate in getattr(chunk, "candidates", None) or []:
                content = getattr(candidate, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", None) or []:
                    inline_data = getattr(part, "inline_data", None)
                    if inline_data and getattr(inline_data, "data", None):
                        yield inline_data.data


