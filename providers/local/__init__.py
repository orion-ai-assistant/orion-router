"""
providers/local/
----------------
Yerel (self-hosted) servislere yönlendiren provider paketi.

Desteklenen yetenekler:
  - Chat     → llama-cpp sunucusu (/v1/chat/completions)
  - Embed    → llama-cpp-embed sunucusu (/embed)
"""
from .chat import LocalChatProvider
from .embeddings import LocalEmbedProvider

__all__ = ["LocalChatProvider", "LocalEmbedProvider"]
