import asyncio
import base64
import json
import logging
import time

from core.router.route_types import RoutePlan

logger = logging.getLogger("service-router.dynamic")


def _coerce_default_config(default_config) -> dict:
    if isinstance(default_config, str):
        try:
            return json.loads(default_config)
        except Exception:
            return {}
    if isinstance(default_config, dict):
        return default_config
    return {}


class TTSRunner:
    def __init__(self, registry, route_resolver, key_pool, telemetry) -> None:
        self.registry = registry
        self.route_resolver = route_resolver
        self.key_pool = key_pool
        self.telemetry = telemetry

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
        route_plan = RoutePlan.direct(model, provider)
        try:
            route_plan = await self.route_resolver.resolve("tts", model, provider)
        except Exception as exc:
            logger.warning("TTS route resolution failed for '%s': %s", model, exc)

        req_data = {"model": model, "input": input_text, "voice": voice, **kwargs}
        log_id = await self.telemetry.create_processing_log(
            key_id,
            route_plan.primary_provider,
            model,
            "tts",
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
                p_def_config = _coerce_default_config(route.default_config)

                route_kwargs = {
                    key: value
                    for key, value in p_def_config.items()
                    if value is not None and value != ""
                }
                route_kwargs.update(
                    {
                        key: value
                        for key, value in kwargs.items()
                        if value is not None and value != ""
                    }
                )

                if route.temperature is not None and route_kwargs.get("temperature") is None:
                    try:
                        route_kwargs["temperature"] = float(route.temperature)
                    except Exception:
                        pass

                target_voice = voice
                if (
                    not target_voice
                    or str(target_voice).lower() in ("none", "null", "default", "alloy")
                ) and p_def_config.get("voice"):
                    target_voice = p_def_config.get("voice")

                if not route_kwargs.get("tts_instruct") and not route_kwargs.get("instructions"):
                    instructs = []
                    for field in ("gender", "age", "pitch", "style", "accent", "dialect"):
                        val = route_kwargs.get(field)
                        if val and str(val).strip() and str(val).strip().lower() != "auto":
                            instructs.append(str(val).strip())
                    if instructs:
                        route_kwargs["tts_instruct"] = ", ".join(instructs)

                plugin = self.registry.tts_providers.get(p_provider)
                if not plugin:
                    last_err = ValueError(f"TTS provider not available: {p_provider}")
                    continue

                keys_to_try = await self.key_pool.get_keys_for_provider(
                    p_provider,
                    api_key or auth_header,
                )

                for key_val, key_pool_id in keys_to_try:
                    logger.info(
                        "Routing TTS to %s (model=%s, voice=%s) using key %s, kwargs=%s",
                        p_provider,
                        p_model,
                        target_voice,
                        key_pool_id or "default",
                        route_kwargs,
                    )
                    try:
                        audio_bytes, content_type, usage_meta = await plugin.generate_speech(
                            model=p_model,
                            input_text=input_text,
                            voice=target_voice,
                            api_key=key_val,
                            auth_header=auth_header if not key_val else None,
                            **route_kwargs,
                        )

                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                        prompt_tokens = usage_meta.get("prompt_tokens", 0)
                        completion_tokens = usage_meta.get("completion_tokens", 0)
                        usage = {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "thoughts_tokens": 0,
                        }
                        res_success = {
                            "detail": "Audio generation successful",
                            "content_type": content_type,
                            "size_bytes": len(audio_bytes),
                            "estimated_duration_seconds": completion_tokens / 25.0,
                            "audio_base64": audio_b64,
                            "metrics": {"total_duration_ms": duration_ms},
                        }
                        asyncio.create_task(
                            self.telemetry.log_usage(
                                key_id,
                                p_provider,
                                p_model,
                                usage,
                                request_json=json.dumps(req_data, ensure_ascii=False),
                                response_json=json.dumps(res_success, ensure_ascii=False),
                                success=True,
                                capability="tts",
                                duration_ms=duration_ms,
                                log_id=log_id,
                            )
                        )
                        response_metadata = {
                            key: value for key, value in res_success.items() if key != "audio_base64"
                        }
                        return audio_bytes, content_type, response_metadata
                    except Exception as exc:
                        logger.error("TTS route %s/%s failed: %s", p_provider, p_model, exc)
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
                    capability="tts",
                    log_id=log_id,
                )
            )
            raise

        final_error = last_err or ValueError(f"Could not resolve TTS route for model: {model}")
        await self.telemetry.finish_processing_log(log_id, {"error": str(final_error)}, "failed", False)
        raise final_error
