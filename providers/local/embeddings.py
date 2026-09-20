"""
providers/local/embeddings.py
-----------------------------
llama-cpp-embed sunucusuna embedding yönlendirmesi.
Yanıtı OpenAI uyumlu formata çevirir.
"""
import os
import logging

import httpx

from providers.base import BaseEmbed
from core.config import EMBED_HOST, EMBED_PORT
from core.http_client import get_http_client

logger = logging.getLogger("service-router.local.embed")


class LocalEmbedProvider(BaseEmbed):


    async def generate_embeddings(
        self,
        model: str,
        input_text: str | list[str],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> dict:
        embed_host = EMBED_HOST
        embed_port = EMBED_PORT
        url = f"http://{embed_host}:{embed_port}/v1/embeddings"

        # llama-cpp-embed OpenAI uyumlu {"input": text, "model": model} formatı bekler
        payload = {
            "input": input_text,
            "model": model or "local-embed"
        }

        logger.info(f"Routing embeddings to local: {url}")

        client = get_http_client(timeout=60.0)
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            raise RuntimeError(f"Yerel Embeddings servisine ({EMBED_HOST}:{EMBED_PORT}) bağlanılamadı. Servisin açık olduğundan emin olun.")
        except httpx.RequestError as e:
            raise RuntimeError(f"Yerel Embeddings servisine bağlanırken ağ hatası oluştu: {e}")
