"""
providers/local/stt.py
----------------------
Yerel Whisper STT mikroservisi üzerinden ses transkripsiyonu (Speech-to-Text).
Faster-Whisper (CTranslate2) motoruna HTTP POST /v1/audio/transcriptions isteği atar.
"""
import logging
import httpx
from typing import Any

from providers.base import BaseSTT
from core.config import STT_HOST, STT_PORT
from core.http_client import get_http_client

logger = logging.getLogger("service-router.local.stt")

# Whisper tarafından resmi olarak desteklenen diller (alfabetik)
WHISPER_SUPPORTED_LANGUAGES = {
    "af": "Afrikaans",
    "sq": "Albanian",
    "am": "Amharic",
    "ar": "Arabic",
    "hy": "Armenian",
    "as": "Assamese",
    "az": "Azerbaijani",
    "ba": "Bashkir",
    "eu": "Basque",
    "be": "Belarusian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "br": "Breton",
    "bg": "Bulgarian",
    "my": "Burmese",
    "ca": "Catalan",
    "zh": "Chinese",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "et": "Estonian",
    "fo": "Faroese",
    "fi": "Finnish",
    "fr": "French",
    "gl": "Galician",
    "ka": "Georgian",
    "de": "German",
    "el": "Greek",
    "gu": "Gujarati",
    "ht": "Haitian Creole",
    "ha": "Hausa",
    "haw": "Hawaiian",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "is": "Icelandic",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "jw": "Javanese",
    "kn": "Kannada",
    "kk": "Kazakh",
    "km": "Khmer",
    "ko": "Korean",
    "lo": "Lao",
    "la": "Latin",
    "lv": "Latvian",
    "ln": "Lingala",
    "lt": "Lithuanian",
    "lb": "Luxembourgish",
    "mk": "Macedonian",
    "mg": "Malagasy",
    "ms": "Malay",
    "ml": "Malayalam",
    "mt": "Maltese",
    "mi": "Maori",
    "mr": "Marathi",
    "mn": "Mongolian",
    "ne": "Nepali",
    "nn": "Nynorsk",
    "no": "Norwegian",
    "oc": "Occitan",
    "ps": "Pashto",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese",
    "pa": "Punjabi",
    "ro": "Romanian",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sr": "Serbian",
    "sn": "Shona",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "so": "Somali",
    "es": "Spanish",
    "su": "Sundanese",
    "sw": "Swahili",
    "sv": "Swedish",
    "tl": "Tagalog",
    "tg": "Tajik",
    "ta": "Tamil",
    "tt": "Tatar",
    "te": "Telugu",
    "th": "Thai",
    "bo": "Tibetan",
    "tr": "Turkish",
    "tk": "Turkmen",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "cy": "Welsh",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "yue": "Cantonese",
}


class LocalSTTProvider(BaseSTT):
    provider_name: str = "local"

    def get_languages(self) -> list[dict[str, str]]:
        """Yerel Whisper mikroservisine GET /v1/audio/languages isteği atarak dilleri çeker."""
        url = f"http://{STT_HOST}:{STT_PORT}/v1/audio/languages"
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    langs = data.get("languages", [])
                    if langs:
                        return langs
        except Exception as e:
            logger.debug(f"Could not fetch languages from local Whisper STT: {e}")

        # Mikroservis henüz güncellenmediyse veya kapalıysa alfabetik tam Whisper dil listesi
        result = [{"code": "", "name": "Otomatik Algıla (Auto Detect)"}]
        sorted_whisper = sorted(
            [{"code": code, "name": f"{name} ({code})"} for code, name in WHISPER_SUPPORTED_LANGUAGES.items()],
            key=lambda x: x["name"].lower(),
        )
        return result + sorted_whisper

    async def generate_transcription(
        self,
        model: str,
        file_bytes: bytes,
        filename: str = "audio.wav",
        language: str | None = None,
        prompt: str | None = None,
        response_format: str = "json",
        temperature: float | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> dict:
        """Yerel Faster-Whisper servisine multipart/form-data isteği atarak sesi metne döker."""
        url = f"http://{STT_HOST}:{STT_PORT}/v1/audio/transcriptions"

        # Form verisi hazırla
        data: dict[str, Any] = {}
        if language and language.strip().lower() not in ("auto", "none", ""):
            data["language"] = language.strip().lower()

        if prompt:
            data["prompt"] = prompt
        if temperature is not None:
            data["temperature"] = str(temperature)
        if response_format:
            data["response_format"] = response_format

        # Dosya MIME belirle
        content_type = "audio/wav"
        fn = filename.lower()
        if fn.endswith(".mp3"):
            content_type = "audio/mpeg"
        elif fn.endswith(".ogg"):
            content_type = "audio/ogg"
        elif fn.endswith(".flac"):
            content_type = "audio/flac"
        elif fn.endswith(".m4a"):
            content_type = "audio/m4a"
        elif fn.endswith(".webm"):
            content_type = "audio/webm"

        files = {
            "file": (filename or "audio.wav", file_bytes, content_type)
        }

        logger.info(
            f"Routing Local STT: model={model}, filename={filename} ({len(file_bytes)} bytes), "
            f"language={data.get('language', 'auto')}, url={url}"
        )

        client = get_http_client(timeout=120.0)
        try:
            response = await client.post(url, data=data, files=files)
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to local STT server at {url}: {e}")
            raise RuntimeError(f"Local STT Service Unreachable ({url}): {e}")

        if response.status_code != 200:
            logger.error(f"Local STT API Error [{response.status_code}]: {response.text}")
            raise RuntimeError(f"Local STT API Error: {response.status_code} - {response.text}")

        try:
            result = response.json()
        except Exception:
            result = {"text": response.text.strip()}

        logger.info(f"Local STT completed successfully: text_len={len(result.get('text', ''))}")
        return result
