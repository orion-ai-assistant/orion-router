"""
providers/gemini/
-----------------
Google Gemini (google-genai SDK) provider paketi.

Desteklenen yetenekler:
  - Chat        → generate_content_stream (OpenAI uyumlu SSE)
  - Embed       → embed_content (text-embedding-004)
  - TTS         → generate_content (response_modalities=["AUDIO"])
  - FileUpload  → files.upload  (video, görsel vb. için Gemini File API)
"""
from .chat import GeminiChatProvider
from .embeddings import GeminiEmbedProvider
from .tts import GeminiTTSProvider
from .files import GeminiFileProvider

__all__ = [
    "GeminiChatProvider",
    "GeminiEmbedProvider",
    "GeminiTTSProvider",
    "GeminiFileProvider",
]
