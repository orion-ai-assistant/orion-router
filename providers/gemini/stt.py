"""
providers/gemini/stt.py
-----------------------
Google Gemini Audio Transcription (Speech-to-Text) provider.
Gemini'nin ses işleme yeteneğini (özellikle gemini-3.5-transcribe modelini)
Files API ve Interactions API kullanarak yüksek doğrulukla metne döker.
"""
import asyncio
import base64
import io
import logging
from typing import Any

from google import genai
from google.genai import types

from providers.base import BaseSTT
from providers.gemini.client import get_gemini_client

logger = logging.getLogger("service-router.gemini.stt")

# Gemini 3.5 Transcribe resmi BCP-47 dil kodları ve adları (Google AI Studio Belgeleri)
GEMINI_STT_LANGUAGES: dict[str, str] = {
    "af-ZA": "Afrikaans",
    "am-ET": "Amharic",
    "ar-EG": "Arabic (Egypt)",
    "hy-AM": "Armenian",
    "as-IN": "Assamese",
    "az-AZ": "Azerbaijani",
    "be-BY": "Belarusian",
    "bn-BD": "Bengali (Bangladesh)",
    "bn-IN": "Bengali (India)",
    "bs-BA": "Bosnian",
    "bg-BG": "Bulgarian",
    "rup-BG": "Bulgarian (Aromanian)",
    "my-MM": "Burmese",
    "yue-Hant-HK": "Cantonese (Traditional)",
    "ca-ES": "Catalan",
    "ceb": "Cebuano",
    "km-KH": "Central Khmer",
    "hr-HR": "Croatian",
    "cs-CZ": "Czech",
    "da-DK": "Danish",
    "nl-NL": "Dutch",
    "en-GB": "English (Great Britain)",
    "en-IN": "English (India)",
    "en-US": "English (United States)",
    "et-EE": "Estonian",
    "fa-IR": "Farsi",
    "fil-PH": "Filipino",
    "fi-FI": "Finnish",
    "fr-FR": "French",
    "gl-ES": "Galician",
    "ka-GE": "Georgian",
    "de-DE": "German",
    "el-GR": "Greek",
    "gu-IN": "Gujarati",
    "ha-NG": "Hausa",
    "he-IL": "Hebrew",
    "hi-IN": "Hindi",
    "hu-HU": "Hungarian",
    "is-IS": "Icelandic",
    "id-ID": "Indonesian",
    "it-IT": "Italian",
    "ja-JP": "Japanese",
    "jv-ID": "Javanese",
    "kea-CV": "Kabuverdianu",
    "kn-IN": "Kannada",
    "kk-KZ": "Kazakh",
    "ko-KR": "Korean",
    "ky-KG": "Kyrgyz",
    "lv-LV": "Latvian",
    "ln-CD": "Lingala",
    "lt-LT": "Lithuanian",
    "mk-MK": "Macedonian",
    "ms-MY": "Malay",
    "ml-IN": "Malayalam",
    "mt-MT": "Maltese",
    "cmn-Hans-CN": "Mandarin Chinese (Simplified)",
    "mr-IN": "Marathi",
    "mn-MN": "Mongolian",
    "ne-NP": "Nepali",
    "nb-NO": "Norwegian",
    "or-IN": "Oriya",
    "pl-PL": "Polish",
    "pt-BR": "Portuguese (Brazil)",
    "pt-PT": "Portuguese (Portugal)",
    "pa-IN": "Punjabi",
    "pa-Guru-IN": "Punjabi (Gurmukhi script)",
    "ro-RO": "Romanian",
    "ru-RU": "Russian",
    "sr-RS": "Serbian",
    "sd-Arab-IN": "Sindhi (Arabic script)",
    "sk-SK": "Slovak",
    "sl-SI": "Slovenian",
    "es-419": "Spanish (Latin America)",
    "es-US": "Spanish (United States)",
    "sw-KE": "Swahili (Kenya)",
    "sv-SE": "Swedish",
    "tg-TJ": "Tajik",
    "te-IN": "Telugu",
    "th-TH": "Thai",
    "tr-TR": "Turkish",
    "uk-UA": "Ukrainian",
    "uz-UZ": "Uzbek",
    "vi-VN": "Vietnamese",
}

# 2 harfli ISO kodlarını veya yaygın kısaltmaları BCP-47 kodlarına eşleme
GEMINI_LANGUAGE_SHORTCUTS: dict[str, str] = {
    "tr": "tr-TR",
    "en": "en-US",
    "de": "de-DE",
    "fr": "fr-FR",
    "es": "es-US",
    "it": "it-IT",
    "ru": "ru-RU",
    "ar": "ar-EG",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "pt": "pt-BR",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "az": "az-AZ",
    "uk": "uk-UA",
    "hi": "hi-IN",
    "id": "id-ID",
    "sv": "sv-SE",
    "no": "nb-NO",
    "da": "da-DK",
    "fi": "fi-FI",
    "el": "el-GR",
    "cs": "cs-CZ",
    "ro": "ro-RO",
    "hu": "hu-HU",
    "vi": "vi-VN",
    "th": "th-TH",
    "he": "he-IL",
    "fa": "fa-IR",
    "bg": "bg-BG",
    "hr": "hr-HR",
    "sr": "sr-RS",
    "sk": "sk-SK",
    "sl": "sl-SI",
    "et": "et-EE",
    "lv": "lv-LV",
    "lt": "lt-LT",
    "ms": "ms-MY",
    "fil": "fil-PH",
    "bn": "bn-BD",
    "ta": "ta-IN",
    "te": "te-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "pa": "pa-IN",
    "ka": "ka-GE",
    "hy": "hy-AM",
    "kk": "kk-KZ",
    "uz": "uz-UZ",
    "af": "af-ZA",
    "sw": "sw-KE",
    "is": "is-IS",
    "ca": "ca-ES",
    "gl": "gl-ES",
    "bs": "bs-BA",
    "mn": "mn-MN",
    "ne": "ne-NP",
    "km": "km-KH",
    "my": "my-MM",
    "am": "am-ET",
    "zh": "cmn-Hans-CN",
}


def resolve_gemini_bcp47(lang: str) -> str:
    """Girilen dil kodunu (örn: 'tr' veya 'tr-TR') Gemini 3.5 Transcribe BCP-47 koduna dönüştürür."""
    cleaned = lang.strip()
    for code in GEMINI_STT_LANGUAGES:
        if code.lower() == cleaned.lower():
            return code
    if cleaned.lower() in GEMINI_LANGUAGE_SHORTCUTS:
        return GEMINI_LANGUAGE_SHORTCUTS[cleaned.lower()]
    return cleaned


class GeminiSTTProvider(BaseSTT):
    provider_name: str = "gemini"

    def get_languages(self) -> list[dict[str, str]]:
        """Gemini 3.5 Transcribe tarafından desteklenen dillerin listesini BCP-47 kodları ve adları ile alfabetik döner."""
        langs = [
            {"code": "", "name": "Otomatik Algıla (Auto Detect)"},
        ]
        sorted_items = sorted(GEMINI_STT_LANGUAGES.items(), key=lambda x: x[1].lower())
        for code, name in sorted_items:
            langs.append({"code": code, "name": f"{name} ({code})"})
        return langs

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
        """Gemini API üzerinden ses dosyasını metne dönüştürür.
        gemini-3.5-transcribe modeli için Files API + Interactions API kullanılır.
        Diğer genel modeller için generate_content fallback olarak çalışır.
        """
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )

        if not resolved_key:
            raise ValueError("Gemini STT Error: No API key provided.")
        if not model:
            raise ValueError("Gemini STT Error: Model name is required.")

        client = get_gemini_client(resolved_key)

        # Content type belirleme
        content_type = "audio/wav"
        fn = (filename or "audio.wav").lower()
        if fn.endswith(".mp3"):
            content_type = "audio/mp3"
        elif fn.endswith(".ogg"):
            content_type = "audio/ogg"
        elif fn.endswith(".flac"):
            content_type = "audio/flac"
        elif fn.endswith(".m4a") or fn.endswith(".aac"):
            content_type = "audio/aac"
        elif fn.endswith(".webm"):
            content_type = "audio/webm"

        is_transcribe_model = "transcribe" in model.lower()

        # =====================================================================
        # 1. gemini-3.5-transcribe Modeli (Files API + Interactions API)
        # =====================================================================
        if is_transcribe_model:
            audio_file = None
            use_inline = len(file_bytes) <= 20 * 1024 * 1024  # 20MB ve altı için doğrudan inline base64 (çok hızlı ~1-2s)
            try:
                if use_inline:
                    encoded_audio = base64.b64encode(file_bytes).decode("utf-8")
                    audio_input = {
                        "type": "audio",
                        "data": encoded_audio,
                        "mime_type": content_type,
                    }
                else:
                    # 20MB üzeri büyük ses dosyaları için Files API ile yükle
                    audio_file = await client.aio.files.upload(
                        file=io.BytesIO(file_bytes),
                        config=types.UploadFileConfig(
                            mime_type=content_type,
                            display_name=filename or "audio.wav",
                        ),
                    )

                    wait_count = 0
                    while getattr(audio_file, "state", None) == types.FileState.PROCESSING and wait_count < 30:
                        await asyncio.sleep(0.5)
                        audio_file = await client.aio.files.get(name=audio_file.name)
                        wait_count += 1

                    if getattr(audio_file, "state", None) == types.FileState.FAILED:
                        raise ValueError("Gemini Audio upload processing failed.")

                    audio_input = {
                        "type": "audio",
                        "uri": audio_file.uri,
                        "mime_type": audio_file.mime_type or content_type,
                    }

                # 2. Generation / Transcription konfigürasyonu
                generation_config: dict[str, Any] = {}
                transcription_config: dict[str, Any] = {}

                if language and language.strip().lower() not in ("auto", "none", ""):
                    bcp_code = resolve_gemini_bcp47(language)
                    transcription_config["language_codes"] = [bcp_code]

                if transcription_config:
                    generation_config["transcription_config"] = transcription_config

                call_kwargs: dict[str, Any] = {
                    "model": model,
                    "input": [audio_input],
                }
                if generation_config:
                    call_kwargs["generation_config"] = generation_config

                logger.info(
                    f"Routing Gemini 3.5 Transcribe (Interactions API): model={model}, filename={filename} "
                    f"({len(file_bytes)} bytes), inline={use_inline}, lang={transcription_config.get('language_codes')}"
                )

                interaction = await client.aio.interactions.create(**call_kwargs)

                # 3. Transkripsiyon metnini doğru alandan oku
                text = ""
                # Öncelik 1: Doğrudan interaction.output_text
                if hasattr(interaction, "output_text") and interaction.output_text:
                    text = interaction.output_text
                # Öncelik 2: interaction.steps içindeki model_output içerikleri
                elif getattr(interaction, "steps", None):
                    for step in interaction.steps:
                        contents = getattr(step, "content", None) or []
                        if isinstance(contents, list):
                            for c in contents:
                                if hasattr(c, "text") and c.text:
                                    text += c.text
                                elif isinstance(c, dict) and c.get("text"):
                                    text += c["text"]
                # Öncelik 3: model_dump veya dict fallback
                if not text and hasattr(interaction, "model_dump"):
                    dump = interaction.model_dump()
                    if dump.get("output_text"):
                        text = dump["output_text"]
                    elif "steps" in dump and isinstance(dump["steps"], list):
                        for s in dump["steps"]:
                            for c in s.get("content", []):
                                if isinstance(c, dict) and c.get("text"):
                                    text += c["text"]

                # 4. Token kullanım istatistikleri
                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(interaction, "usage") and interaction.usage:
                    u = interaction.usage
                    prompt_tokens = getattr(u, "total_input_tokens", 0) or getattr(u, "input_tokens", 0) or 0
                    completion_tokens = getattr(u, "total_output_tokens", 0) or getattr(u, "output_tokens", 0) or 0
                    if not prompt_tokens and hasattr(u, "model_dump"):
                        ud = u.model_dump()
                        prompt_tokens = ud.get("total_input_tokens", 0) or ud.get("input_tokens", 0) or 0
                        completion_tokens = ud.get("total_output_tokens", 0) or ud.get("output_tokens", 0) or 0

                logger.info(
                    f"Gemini 3.5 Transcribe complete: text_len={len(text)} "
                    f"(In: {prompt_tokens}, Out: {completion_tokens})"
                )

                detected_lang = language or "auto"
                return {
                    "text": text.strip(),
                    "language": detected_lang,
                    "duration": 0.0,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    },
                }

            finally:
                # 5. Google AI Studio depolamasındaki geçici dosyayı temizle
                if audio_file and getattr(audio_file, "name", None):
                    try:
                        await client.aio.files.delete(name=audio_file.name)
                    except Exception as del_err:
                        logger.debug(f"Failed to delete uploaded Gemini audio file {audio_file.name}: {del_err}")

        # =====================================================================
        # 2. Standart Gemini Çok Modlu (Multimodal) Modelleri (generate_content)
        # =====================================================================
        audio_part = types.Part.from_bytes(data=file_bytes, mime_type=content_type)

        instruction_parts = ["Transcribe the audio exactly as spoken. Output ONLY the verbatim transcribed text without any extra commentary."]
        if language and language.strip().lower() not in ("auto", "none", ""):
            bcp_code = resolve_gemini_bcp47(language)
            lang_name = GEMINI_STT_LANGUAGES.get(bcp_code, language.strip())
            instruction_parts.append(f"The spoken language is {lang_name}.")

        user_prompt = " ".join(instruction_parts)
        contents = [
            types.Content(
                role="user",
                parts=[
                    audio_part,
                    types.Part.from_text(text=user_prompt),
                ],
            )
        ]

        logger.info(
            f"Routing Gemini Multimodal STT: model={model}, filename={filename} ({len(file_bytes)} bytes), "
            f"mime={content_type}, language={language or 'auto'}"
        )

        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
        )

        text = ""
        if hasattr(response, "text") and response.text:
            text = response.text
        elif hasattr(response, "candidates") and response.candidates:
            for cand in response.candidates:
                content_obj = getattr(cand, "content", None)
                parts = getattr(content_obj, "parts", None) if content_obj else None
                if parts:
                    for part in parts:
                        if hasattr(part, "text") and part.text:
                            text += part.text
                        elif hasattr(part, "audio_transcription") and part.audio_transcription:
                            at = part.audio_transcription
                            if hasattr(at, "words") and at.words:
                                words = [getattr(w, "word", "") for w in at.words if getattr(w, "word", "")]
                                text += " ".join(words)
                            elif isinstance(at, dict) and "words" in at:
                                words = [w.get("word", "") for w in at["words"] if w.get("word")]
                                text += " ".join(words)
                            elif hasattr(at, "text") and at.text:
                                text += at.text

        prompt_tokens = 0
        completion_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0

        logger.info(
            f"Gemini Multimodal STT complete: text_len={len(text)} "
            f"(In: {prompt_tokens}, Out: {completion_tokens})"
        )

        detected_lang = language or "auto"
        return {
            "text": text.strip(),
            "language": detected_lang,
            "duration": 0.0,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        }
