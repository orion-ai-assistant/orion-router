import json
import logging

from database import db_manager

logger = logging.getLogger("service-router.dynamic")


class TelemetryService:
    def __init__(self, app_state=None) -> None:
        self.app_state = app_state

    async def log_usage(
        self,
        key_id: str | None,
        provider: str,
        model: str,
        usage: dict | None,
        request_json: str | None = None,
        response_json: str | None = None,
        success: bool | None = True,
        capability: str = "chat",
        is_estimated: bool = False,
        ttft_ms: float | None = None,
        duration_ms: float | None = None,
        log_id: int | None = None,
    ) -> None:
        try:
            if usage is None:
                p, c, t = None, None, None
                tokens_used = None
            else:
                p = usage.get("prompt_tokens")
                c = usage.get("completion_tokens")
                t = usage.get("thoughts_tokens")
                tokens_used = (p or 0) + (c or 0) + (t or 0)

            cost = None
            p_cost, c_cost, t_cost = 0.0, 0.0, 0.0

            should_calculate = False
            if usage is not None:
                if capability in ("tts", "embed"):
                    should_calculate = success is True
                else:
                    should_calculate = success is True or (c or 0) > 0 or (t or 0) > 0

            if should_calculate:
                pricing_cache = (
                    self.app_state.pricing_cache
                    if hasattr(self.app_state, "pricing_cache")
                    else {}
                )
                if model in pricing_cache:
                    prices = pricing_cache[model]
                    p_cost = (p or 0) * prices.get("input", 0.0)
                    c_cost = (c or 0) * prices.get("output", 0.0)
                    t_cost = (t or 0) * prices.get("think", 0.0)
                    cost = p_cost + c_cost + t_cost
            else:
                cost = 0.0
                p, c, t = None, None, None
                tokens_used = None

            if log_id is None:
                await db_manager.log_request(
                    key_id=key_id,
                    provider=provider,
                    model=model,
                    tokens_used=tokens_used,
                    prompt_tokens=p,
                    completion_tokens=c,
                    thoughts_tokens=t,
                    cost=cost,
                    request_json=request_json,
                    response_json=response_json,
                    success=success,
                    capability=capability,
                    prompt_cost=p_cost,
                    completion_cost=c_cost,
                    thoughts_cost=t_cost,
                    ttft_ms=ttft_ms,
                    duration_ms=duration_ms,
                )
            else:
                await db_manager.update_streaming_log(
                    log_id=log_id,
                    response_json=response_json,
                    status="success"
                    if success is True
                    else ("failed" if success is False else "interrupted"),
                    success=success,
                    tokens_used=tokens_used,
                    prompt_tokens=p,
                    completion_tokens=c,
                    thoughts_tokens=t,
                    cost=cost,
                    prompt_cost=p_cost,
                    completion_cost=c_cost,
                    thoughts_cost=t_cost,
                    key_id=key_id,
                    duration_ms=duration_ms,
                    ttft_ms=ttft_ms,
                )
            logger.info(
                "Logged usage for %s/%s [%s]: (In:%s Out:%s Think:%s) | "
                "TTFT:%sms Dur:%sms | Costs: (In:%.4f Out:%.4f Think:%.4f) | Success: %s",
                provider,
                model,
                capability,
                p,
                c,
                t,
                ttft_ms,
                duration_ms,
                p_cost,
                c_cost,
                t_cost,
                success,
            )
        except Exception as exc:
            logger.error("Failed to log usage: %s", exc)

    async def create_processing_log(
        self,
        key_id: str | None,
        provider: str | None,
        model: str,
        capability: str,
        request_data: dict,
    ) -> int | None:
        if not provider:
            logger.warning("Cannot create processing log without a resolved provider for model '%s'", model)
            return None
        try:
            return await db_manager.create_streaming_log(
                key_id=key_id,
                provider=provider,
                model=model,
                request_json=json.dumps(request_data, ensure_ascii=False),
                response_json=json.dumps({"status": "processing"}, ensure_ascii=False),
                capability=capability,
                status="processing",
            )
        except Exception as exc:
            logger.warning("Failed to create processing log: %s", exc)
            return None

    async def finish_processing_log(
        self,
        log_id: int | None,
        response: dict,
        status: str,
        success: bool | None,
    ) -> None:
        if log_id is None:
            return
        await db_manager.update_streaming_log(
            log_id=log_id,
            response_json=json.dumps(response, ensure_ascii=False),
            status=status,
            success=success,
        )
