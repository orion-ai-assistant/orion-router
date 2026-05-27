"""
providers/openai/
-----------------
OpenAI API provider paketi.

Desteklenen yetenekler:
  - Chat  → /v1/chat/completions (streaming)
  - TTS   → /v1/audio/speech
"""
from .chat import OpenAIChatProvider
from .tts import OpenAITTSProvider

__all__ = ["OpenAIChatProvider", "OpenAITTSProvider"]
