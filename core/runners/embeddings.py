import asyncio
import json
import logging
import time

from core.route_types import RoutePlan

logger = logging.getLogger("service-router.dynamic")


class EmbeddingsRunner:
    def __init__(self, registry, route_resolver, key_pool, telemetry) -> None:
        self.registry = registry
        self.route_resolver = route_resolver
        self.key_pool = key_pool
        self.telemetry = telemetry

    async def run_embeddings(
        self,
        provider: str | None,
        model: str,
        input_text: str | list[str],
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
    ) -> dict:
        route_plan = RoutePlan.direct(model, provider)
        try:
            route_plan = await self.route_resolver.resolve("embed", model, provider)
        except Exception as exc:
            logger.warning("Embed route resolution failed for '%s': %s", model, exc)

        req_data = {"model": model, "input": input_text}
        log_id = await self.telemetry.create_processing_log(
            key_id,
            route_plan.primary_provider,
            model,
            "embed",
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

                plugin = self.registry.embed_providers.get(p_provider)
                if not plugin:
                    last_err = ValueError(f"Embed provider not available: {p_provider}")
                    continue

                keys_to_try = await self.key_pool.get_keys_for_provider(
                    p_provider,
                    api_key or auth_header,
                )

                for key_val, key_pool_id in keys_to_try:
                    logger.info(
                        "Routing embeddings to %s (model=%s) using key %s",
                        p_provider,
                        p_model,
                        key_pool_id or "default",
                    )
                    try:
                        result = await plugin.generate_embeddings(
                            model=p_model,
                            input_text=input_text,
                            api_key=key_val,
                            auth_header=auth_header if not key_val else None,
                        )

                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        p_tokens = 0
                        vector_dim = 0
                        if isinstance(result, dict):
                            if "usage" in result:
                                p_tokens = result["usage"].get("prompt_tokens", 0)
                            try:
                                vector_dim = len(result["data"][0]["embedding"])
                            except Exception:
                                pass
                            if "metrics" not in result:
                                result["metrics"] = {"total_duration_ms": duration_ms}

                        usage = {
                            "prompt_tokens": p_tokens,
                            "completion_tokens": vector_dim,
                            "thoughts_tokens": 0,
                        }
                        asyncio.create_task(
                            self.telemetry.log_usage(
                                key_id,
                                p_provider,
                                p_model,
                                usage,
                                request_json=json.dumps(req_data, ensure_ascii=False),
                                response_json=json.dumps(result, ensure_ascii=False),
                                success=True,
                                capability="embed",
                                duration_ms=duration_ms,
                                log_id=log_id,
                            )
                        )
                        return result
                    except Exception as exc:
                        logger.error("Embed route %s/%s failed: %s", p_provider, p_model, exc)
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
                    capability="embed",
                    log_id=log_id,
                )
            )
            raise

        final_error = last_err or ValueError(f"Could not resolve embed route for model: {model}")
        await self.telemetry.finish_processing_log(log_id, {"error": str(final_error)}, "failed", False)
        raise final_error
