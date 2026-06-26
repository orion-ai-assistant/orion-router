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
            "model": model or "local-model"
        }

        logger.info(f"Routing embeddings to local: {url}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
