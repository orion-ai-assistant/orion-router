from core.secret_guard import redact
from core.key_policy import authorize_attempt, ACCESS_MESSAGE
from fastapi import HTTPException
import asyncio
import json
import logging
import time

from core.router.route_types import RoutePlan

logger = logging.getLogger("service-router.dynamic")


class STTRunner:
    def __init__(self, registry, route_resolver, key_pool, telemetry) -> None:
        self.registry = registry
        self.route_resolver = route_resolver
        self.key_pool = key_pool
        self.telemetry = telemetry

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
        route_plan = RoutePlan.direct(model, provider)
        try:
            route_plan = await self.route_resolver.resolve("stt", model, provider)
        except Exception as exc:
            logger.warning("STT route resolution failed for '%s': %s", model, exc)

        req_data = {
            "model": model,
            "filename": filename,
            "language": language,
            "bytes_len": len(file_bytes),
            **kwargs,
        }
        log_id = await self.telemetry.create_processing_log(
            key_id,
            route_plan.primary_provider,
            model,
            "stt",
            req_data,
        )

        p_provider = route_plan.primary_provider
        p_model = model
        last_err = None
        start_time = time.perf_counter()
        try:
            for route in route_plan.routes:
                p_provider = route.provider
                p_model = route.model

                plugin = self.registry.stt_providers.get(p_provider)
                if not plugin:
                    last_err = ValueError(f"STT provider not available: {p_provider}")
                    continue

                keys_to_try = await self.key_pool.get_keys_for_provider(
                    p_provider,
                    api_key or auth_header,
                    key_id=key_id,
                )

                for key_val, key_pool_id in keys_to_try:
                    try:
                        await authorize_attempt(key_id, p_provider, key_pool_id, key_val)
                    except HTTPException as denied:
                        if denied.status_code != 403:
                            raise
                        last_err = denied
                        continue
                    logger.info(
                        "Routing STT to %s (model=%s, filename=%s) using key %s",
                        p_provider,
                        p_model,
                        filename,
                        key_pool_id or "default",
                    )
                    try:
                        result = await plugin.generate_transcription(
                            model=p_model,
                            file_bytes=file_bytes,
                            filename=filename,
                            language=language,
                            prompt=prompt,
                            response_format=response_format,
                            temperature=temperature,
                            api_key=key_val,
                            auth_header=None,
                            **kwargs,
                        )

                        result = redact(result)
                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        duration = result.get("duration", 0) or 0
                        text_res = result.get("text", "")
                        reported_usage = result.get("usage")
                        if isinstance(reported_usage, dict):
                            usage = {
                                "prompt_tokens": reported_usage.get("prompt_tokens"),
                                "completion_tokens": reported_usage.get("completion_tokens"),
                                "thoughts_tokens": reported_usage.get("thoughts_tokens", 0),
                            }
                            if reported_usage.get("prompt_tokens") is None and reported_usage.get("completion_tokens") is None:
                                usage = None
                        else:
                            usage = None
                        if isinstance(result, dict) and "metrics" not in result:
                            result["metrics"] = {"total_duration_ms": duration_ms}

                        asyncio.create_task(
                            self.telemetry.log_usage(
                                key_id,
                                p_provider,
                                p_model,
                                usage,
                                request_json=json.dumps(req_data, ensure_ascii=False),
                                response_json=json.dumps(result, ensure_ascii=False),
                                success=True,
                                capability="stt",
                                usage_unit="token" if reported_usage else "second",
                                usage_amount=duration if duration else None,
                                duration_ms=duration_ms,
                                log_id=log_id,
                            )
                        )
                        return result
                    except Exception as exc:
                        exc = RuntimeError(redact(str(exc)))
                        logger.error("STT route %s/%s failed: %s", p_provider, p_model, exc)
                        await self.key_pool.mark_key_error(key_pool_id, str(exc))
                        last_err = exc
        except asyncio.CancelledError:
            res_err = {"error": "Client disconnected / Request Cancelled"}
            asyncio.create_task(
                self.telemetry.log_usage(
                    key_id,
                    p_provider,
                    p_model,
                    None,
                    request_json=json.dumps(req_data, ensure_ascii=False),
                    response_json=json.dumps(res_err, ensure_ascii=False),
                    success=None,
                    capability="stt",
                    log_id=log_id,
                )
            )
            raise

        final_error = last_err or (HTTPException(403, ACCESS_MESSAGE) if key_id else ValueError(f"Could not resolve STT route for model: {model}"))
        await self.telemetry.finish_processing_log(log_id, {"error": str(final_error)}, "failed", False)
        raise final_error
