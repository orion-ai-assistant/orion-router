"""
providers/gemini/client.py
--------------------------
Google GenAI SDK için Kalıcı İstemci Havuzu (Persistent LRU Client Pool).

Her istekte sıfırdan genai.Client oluşturmak yerine, API anahtarlarına göre
örnekleri bellekte sıcak (warm) tutar. Böylece:
- TLS 1.3 ve TCP el sıkışma maliyeti sıfırlanır (~300-400ms kazanç).
- Alt katmandaki HTTP/2 Keep-Alive soketleri açık tutulur.
- Soket tükenmesi (socket exhaustion) engellenir.
- LRU (Least Recently Used) sınırlandırması ile rastgele/sahte API anahtarlarıyla
  bellek ve açık soketlerin şişmesi (DoS/resource exhaustion) önlenir.
"""
import asyncio
import hashlib
import logging
import threading
from collections import OrderedDict
from typing import Optional

from google import genai

logger = logging.getLogger("service-router.gemini.client")

# Maksimum sıcak tutulacak eşzamanlı farklı API anahtarı istemci sayısı
MAX_GEMINI_CLIENTS = 32

_client_pool: OrderedDict[str, genai.Client] = OrderedDict()
_pool_lock = threading.Lock()


def _key_hash(api_key: str) -> str:
    """API anahtarının güvenli SHA-256 hash'ini döner (bellek anahtarı olarak kullanılır)."""
    return hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()


def _safe_close_client(client: genai.Client) -> None:
    """Bir genai.Client nesnesini arka planda bloklamadan güvenle kapatır."""
    try:
        if hasattr(client, "aio") and hasattr(client.aio, "aclose"):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(client.aio.aclose())
            except RuntimeError:
                if hasattr(client, "close"):
                    client.close()
        elif hasattr(client, "close"):
            client.close()
    except Exception as e:
        logger.debug(f"Non-critical error during Gemini client eviction close: {e}")


def get_gemini_client(api_key: str) -> genai.Client:
    """Belirtilen API anahtarı için havuzdan sıcak genai.Client döner.
    Havuzda varsa LRU sırasında en sona taşır (sıcak tutar).
    Yoksa oluşturup ekler; havuz kapasitesi aşılırsa en eski istemci tahliye edilir.
    """
    if not api_key:
        raise ValueError("Gemini Client Error: No API key provided.")

    kh = _key_hash(api_key)

    with _pool_lock:
        if kh in _client_pool:
            client = _client_pool[kh]
            _client_pool.move_to_end(kh)
            return client

        # Kapasite kontrolü: Doluysa en eski (LRU) istemciyi tahliye et ve soketini kapat
        if len(_client_pool) >= MAX_GEMINI_CLIENTS:
            evicted_kh, evicted_client = _client_pool.popitem(last=False)
            logger.info(f"Gemini client pool reached capacity ({MAX_GEMINI_CLIENTS}). Evicting oldest client [{evicted_kh[:8]}...]")
            _safe_close_client(evicted_client)

        masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
        logger.info(f"Initializing new persistent Gemini GenAI Client for key [{masked_key}]")
        client = genai.Client(api_key=api_key.strip())
        _client_pool[kh] = client
        return client


async def close_gemini_clients() -> None:
    """Router kapanırken havuzdaki tüm istemcileri ve açık HTTP/TLS bağlantılarını temizler."""
    global _client_pool
    with _pool_lock:
        clients_to_close = list(_client_pool.values())
        _client_pool.clear()

    for client in clients_to_close:
        try:
            if hasattr(client, "aio") and hasattr(client.aio, "aclose"):
                await client.aio.aclose()
            elif hasattr(client, "close"):
                client.close()
        except Exception as e:
            logger.warning(f"Error closing Gemini client: {e}")

    logger.info(f"Closed {len(clients_to_close)} persistent Gemini client instance(s).")
