"""
providers/gemini/embeddings.py
------------------------------
Google Gemini text embedding provider.
Varsayılan model: models/text-embedding-004
"""
import logging

from google import genai

from providers.base import BaseEmbed


logger = logging.getLogger("service-router.gemini.embed")


class GeminiEmbedProvider(BaseEmbed):
    provider_name = "gemini"

    async def generate_embeddings(
        self,
        model: str,
        input_text: str | list[str],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> dict:
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
        )

        if not resolved_key:
            raise ValueError("Gemini Embed Error: No API key provided.")

        if not model:
            raise ValueError("Gemini Embed Error: Model name is required.")

        client = genai.Client(api_key=resolved_key)
        embed_model = model

        logger.info(f"Generating Gemini embeddings with model: {embed_model}")

        result = await client.aio.models.embed_content(
            model=embed_model,
            contents=input_text,
        )

        embeddings_out = []
        for i, emb in enumerate(result.embeddings):
            embeddings_out.append(
                {
                    "object": "embedding",
                    "embedding": list(emb.values),
                    "index": i,
                }
            )

        return {
            "object": "list",
            "data": embeddings_out,
            "model": embed_model,
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
