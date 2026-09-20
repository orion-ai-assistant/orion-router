"""
core/http_client.py
-------------------
Orion Router genelinde paylaşılan HTTP/2 & HTTP/1.1 kalıcı bağlantı havuzu (Persistent Connection Pool).

Her HTTP isteğinde sıfırdan TCP ve TLS el sıkışması yapılması önlenir.
Bağlantılar Keep-Alive ile sıcak (warm) tutularak ağ gecikmesi ~300-400ms düşürülür.
FastAPI lifespan kapanırken tüm bağlantılar temiz bir şekilde sonlandırılır.
"""
import logging
import threading
from typing import Optional
import httpx

logger = logging.getLogger("service-router.http_client")

_shared_async_client: Optional[httpx.AsyncClient] = None
_client_lock = threading.Lock()


def get_http_client(timeout: float = 120.0) -> httpx.AsyncClient:
    """Paylaşılan, Keep-Alive bağlantı havuzuna sahip AsyncClient örneğini döner.
    Henüz başlatılmamışsa veya kapatılmışsa thread-safe şekilde yeniden oluşturur.
    """
    global _shared_async_client
    if _shared_async_client is None or _shared_async_client.is_closed:
        with _client_lock:
            if _shared_async_client is None or _shared_async_client.is_closed:
                limits = httpx.Limits(
                    max_keepalive_connections=50,
                    max_connections=100,
                    keepalive_expiry=120.0,
                )
                timeouts = httpx.Timeout(
                    timeout=timeout,
                    connect=10.0,
                    read=timeout,
                    write=30.0,
                    pool=10.0,
                )
                _shared_async_client = httpx.AsyncClient(
                    limits=limits,
                    timeout=timeouts,
                )
                logger.debug("Initialized shared persistent httpx.AsyncClient with Keep-Alive pool.")
    return _shared_async_client


async def close_http_clients() -> None:
    """Router kapanırken bağlantı havuzunu temiz bir şekilde sonlandırır."""
    global _shared_async_client
    with _client_lock:
        client_to_close = _shared_async_client
        _shared_async_client = None

    if client_to_close is not None and not client_to_close.is_closed:
        try:
            await client_to_close.aclose()
            logger.info("Shared persistent HTTP client connections closed.")
        except Exception as e:
            logger.warning(f"Error closing shared HTTP client: {e}")
