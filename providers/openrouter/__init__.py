"""
providers/openrouter/
---------------------
OpenRouter API provider paketi.

Desteklenen yetenekler:
  - Chat  → /api/v1/chat/completions (streaming)
"""
from .chat import OpenRouterChatProvider

__all__ = ["OpenRouterChatProvider"]
