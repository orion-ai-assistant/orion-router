"""
dynamic_router.py
-----------------
Public facade for capability-based provider routing.

The routing, provider discovery, telemetry, and capability-specific request
flows live under core/. This module keeps the application-facing API stable.
"""

import logging
from typing import Any, AsyncGenerator

from core.router.provider_registry import ALLOWED_CAPABILITIES, ProviderRegistry
from core.router.route_types import ResolvedRoute, RoutePlan
from core.router.routing_services import (
    ProviderKeyPool,
    RouteResolver,
    pool_key_on_quota_cooldown,
)
from core.router.runners.chat import (
    ChatRunner,
    inject_system_prompt,
    sanitize_tool_ids_for_non_gemini,
)
from core.router.runners.embeddings import EmbeddingsRunner
from core.router.runners.stt import STTRunner
from core.router.runners.tts import TTSRunner
from core.router.telemetry import TelemetryService

logger = logging.getLogger("service-router.dynamic")

_pool_key_on_quota_cooldown = pool_key_on_quota_cooldown
_sanitize_tool_ids_for_non_gemini = sanitize_tool_ids_for_non_gemini
_inject_system_prompt = inject_system_prompt


async def _log_usage(app_state, *args, **kwargs):
    return await TelemetryService(app_state).log_usage(*args, **kwargs)


async def _create_processing_log(*args, **kwargs):
    return await TelemetryService().create_processing_log(*args, **kwargs)


async def _finish_processing_log(*args, **kwargs):
    return await TelemetryService().finish_processing_log(*args, **kwargs)


class DynamicLLMRouter:
    def __init__(self, app_state=None):
        self.app_state = app_state
        self.registry = ProviderRegistry()
        self.route_resolver = RouteResolver()
        self.key_pool = ProviderKeyPool(app_state)
        self.telemetry = TelemetryService(app_state)
        self.chat_runner = ChatRunner(
            self.registry,
            self.route_resolver,
            self.key_pool,
            self.telemetry,
        )
        self.embeddings_runner = EmbeddingsRunner(
            self.registry,
            self.route_resolver,
            self.key_pool,
            self.telemetry,
        )
        self.tts_runner = TTSRunner(
            self.registry,
            self.route_resolver,
            self.key_pool,
            self.telemetry,
        )
        self.stt_runner = STTRunner(
            self.registry,
            self.route_resolver,
            self.key_pool,
            self.telemetry,
        )

    @property
    def chat_providers(self):
        return self.registry.chat_providers

    @property
    def embed_providers(self):
        return self.registry.embed_providers

    @property
    def tts_providers(self):
        return self.registry.tts_providers

    @property
    def stt_providers(self):
        return self.registry.stt_providers

    @property
    def file_providers(self):
        return self.registry.file_providers

    def _load_providers(self):
        self.registry.load()

    def _get_db_key(self, provider: str) -> str | None:
        return self.key_pool.get_db_key(provider)

    async def _get_keys_for_provider(
        self,
        provider: str,
        client_key: str | None = None,
    ) -> list[tuple[str | None, str | None]]:
        return await self.key_pool.get_keys_for_provider(provider, client_key)

    async def _resolve_route_plan(
        self,
        capability: str,
        model: str,
        provider: str | None,
    ) -> RoutePlan:
        return await self.route_resolver.resolve(capability, model, provider)

    async def _stream(self, *args, **kwargs):
        async for chunk in self.chat_runner.stream(*args, **kwargs):
            yield chunk

    async def run_combo(
        self,
        provider: str | None,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self.chat_runner.run_combo(
            provider,
            model,
            messages,
            api_key=api_key,
            auth_header=auth_header,
            key_id=key_id,
            **kwargs,
        ):
            yield chunk

    async def run_embeddings(
        self,
        provider: str | None,
        model: str,
        input_text: str | list[str],
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
    ) -> dict:
        return await self.embeddings_runner.run_embeddings(
            provider,
            model,
            input_text,
            api_key=api_key,
            auth_header=auth_header,
            key_id=key_id,
        )

    async def run_speech(
        self,
        provider: str | None,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ) -> tuple[bytes, str, dict[str, float]]:
        return await self.tts_runner.run_speech(
            provider,
            model,
            input_text,
            voice=voice,
            api_key=api_key,
            auth_header=auth_header,
            key_id=key_id,
            **kwargs,
        )

    async def run_transcription(
        self,
        provider: str | None,
        model: str,
        file_bytes: bytes,
        filename: str = "audio.wav",
        language: str | None = None,
        prompt: str | None = None,
        response_format: str = "json",
        temperature: float | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ) -> dict:
        return await self.stt_runner.run_transcription(
            provider,
            model,
            file_bytes,
            filename=filename,
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
            api_key=api_key,
            auth_header=auth_header,
            key_id=key_id,
            **kwargs,
        )

    async def upload_file(
        self,
        provider: str,
        file_bytes: bytes,
        mime_type: str,
        display_name: str,
        api_key: str | None = None,
    ) -> dict:
        plugin = self.file_providers.get(provider)
        if not plugin:
            raise ValueError(f"File upload provider not available: {provider}")

        db_key = self._get_db_key(provider)
        logger.info("Routing file upload to %s: %s (%s)", provider, display_name, mime_type)
        return await plugin.upload_file(
            file_bytes=file_bytes,
            mime_type=mime_type,
            display_name=display_name,
            api_key=db_key or api_key,
        )

    def get_capabilities(self) -> dict:
        return self.registry.get_capabilities()
