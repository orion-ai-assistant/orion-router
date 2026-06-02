"""
providers/base.py
-----------------
Tüm provider yetenekleri (capability) için soyut temel sınıflar.

Yetenek sınıfları:
  - BaseChat        → stream_chat()
  - BaseEmbed       → generate_embeddings()
  - BaseTTS         → generate_speech()
  - BaseFileUpload  → upload_file()

Her provider alt paketi (__init__.py), desteklediği yetenek sınıflarından miras alan
somut sınıfları dışa aktarır. DynamicLLMRouter bu sınıfları otomatik yükler.
"""

import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any


class _ProviderMixin:
    """Tüm provider yetenek sınıfları için ortak yardımcı metotlar."""

    provider_name: str = ""

    @staticmethod
    def _resolve_api_key(
        auth_header: str | None,
        api_key: str | None,
    ) -> str | None:
        """Gerçek upstream API anahtarını belirler; Orion sanal anahtarlarını reddeder."""
        if auth_header:
            token = auth_header.removeprefix("Bearer ").strip()
            if not token.startswith("sk-orion-"):
                return token
        if api_key and not api_key.startswith("sk-orion-"):
            return api_key
        return None

    @staticmethod
    async def _iter_sse_lines(response) -> AsyncGenerator[dict, None]:
        """Ham SSE satırlarını JSON dict'e çevirir; [DONE] ve boşlukları atlar."""
        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                try:
                    yield json.loads(line[6:])
                except json.JSONDecodeError:
                    pass


# ---------------------------------------------------------------------------
#  Yetenek Soyut Sınıfları
# ---------------------------------------------------------------------------

class BaseChat(_ProviderMixin, ABC):
    """Streaming chat/completion yetenekleri için temel sınıf."""

    @abstractmethod
    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        raise NotImplementedError


class BaseEmbed(_ProviderMixin, ABC):
    """Metin vektörleştirme (embedding) yetenekleri için temel sınıf."""

    async def generate_embeddings(
        self,
        model: str,
        input_text: str | list[str],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> dict:
        """OpenAI uyumlu embeddings yanıt dict'i döner."""
        raise NotImplementedError


class BaseTTS(_ProviderMixin, ABC):
    """Metin-konuşma (TTS) yetenekleri için temel sınıf."""

    @abstractmethod
    async def generate_speech(
        self,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> tuple[bytes, str, dict]:
        """(ses_baytları, content_type, usage_dict) döner.
        Ör: (b"...", "audio/wav", {"prompt_tokens": 10, "completion_tokens": 20})
        """
        raise NotImplementedError

    def get_voices(self) -> list[str]:
        """Desteklenen seslerin listesini döner."""
        return []


class BaseFileUpload(_ProviderMixin, ABC):
    """Dosya yükleme (video, görsel vb.) yetenekleri için temel sınıf."""

    @abstractmethod
    async def upload_file(
        self,
        file_bytes: bytes,
        mime_type: str,
        display_name: str,
        api_key: str | None = None,
    ) -> dict:
        """Yüklenen dosya hakkında {file_uri, mime_type, display_name, ...} döner."""
        raise NotImplementedError


