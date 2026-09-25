import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator

from providers.base import BaseChat
from core.local_chat_defaults import LOCAL_SAMPLING_DEFAULTS, LOCAL_TEMPERATURE_DEFAULT

logger = logging.getLogger("service-router.dynamic")


def sanitize_tool_ids_for_non_gemini(messages: list[dict]) -> list[dict]:
    id_map: dict[str, str] = {}
    counter = 0
    out: list[dict] = []

    for msg in messages:
        msg = dict(msg)
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            new_tcs = []
            for tc in msg["tool_calls"]:
                tc = dict(tc)
                old_id = tc.get("id", "")
                if "__ts__" in old_id:
                    if old_id not in id_map:
                        id_map[old_id] = f"call_{counter}"
                        counter += 1
                    tc["id"] = id_map[old_id]
                new_tcs.append(tc)
            msg["tool_calls"] = new_tcs

        if msg.get("role") == "tool":
            old_tcid = msg.get("tool_call_id", "")
            if old_tcid in id_map:
                msg = dict(msg)
                msg["tool_call_id"] = id_map[old_tcid]

        out.append(msg)
    return out


def inject_system_prompt(
    messages: list[dict[str, Any]],
    system_prompt: str | None,
) -> list[dict[str, Any]]:
    route_messages = list(messages)
    if not system_prompt:
        return route_messages

    existing_sys = [m.get("content", "") for m in route_messages if m.get("role") == "system"]
    combined_sys = system_prompt + ("\n" + "\n".join(existing_sys) if existing_sys else "")
    return [{"role": "system", "content": combined_sys}] + [
        m for m in route_messages if m.get("role") != "system"
    ]


def extract_error_message(error_chunk: str | None) -> str | None:
    if not error_chunk:
        return None

    data = error_chunk.strip()
    if data.startswith("data:"):
        data = data[5:].strip()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return data or None

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    if error:
        return str(error)
    return None


class ChatRunner:
    def __init__(self, registry, route_resolver, key_pool, telemetry) -> None:
        self.registry = registry
        self.route_resolver = route_resolver
        self.key_pool = key_pool
        self.telemetry = telemetry

    async def stream(
        self,
        plugin: BaseChat,
        key_id,
        provider,
        model,
        messages,
        api_key,
        auth_header,
        log_id=None,
        **kwargs,
    ):
        accumulated_content = ""
        accumulated_reasoning = ""
        accumulated_tool_calls: list[dict] = []
        usage = None
        has_error = False
        status_val = True
        error_details = None
        is_estimated = False

        start_time = time.perf_counter()
        ttft_ms: float | None = None

        logger.info("Starting chat stream: provider=%s, model=%s, kwargs=%s", provider, model, kwargs)

        if provider != "gemini":
            messages = sanitize_tool_ids_for_non_gemini(messages)

        if provider == "local" and hasattr(plugin, "build_payload"):
            await self.telemetry.update_processing_request(
                log_id,
                plugin.build_payload(model, messages, **kwargs),
            )

        try:
            async for chunk in plugin.stream_chat(
                model=model,
                messages=messages,
                api_key=api_key,
                auth_header=auth_header,
                **kwargs,
            ):
                if isinstance(chunk, dict) and "internal_usage" in chunk:
                    usage = chunk["internal_usage"]
                else:
                    if isinstance(chunk, str):
                        if '"error":' in chunk:
                            logger.error("[%s] API Error chunk: %s", provider, chunk.strip())
                            has_error = True
                            status_val = False
                            error_details = chunk.strip()
                        try:
                            data_str = chunk.strip()
                            if data_str.startswith("data:"):
                                data_str = data_str[5:].strip()
                            if data_str and data_str != "[DONE]":
                                chunk_data = json.loads(data_str)
                                if "error" in chunk_data:
                                    error = chunk_data["error"]
                                    if isinstance(error, dict) and error.get("message"):
                                        error_details = str(error["message"])
                                    elif error:
                                        error_details = str(error)
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    has_token = False
                                    if "reasoning_content" in delta and delta["reasoning_content"]:
                                        accumulated_reasoning += delta["reasoning_content"]
                                        has_token = True
                                    if "content" in delta and delta["content"]:
                                        accumulated_content += delta["content"]
                                        has_token = True
                                    if "tool_calls" in delta:
                                        has_token = True
                                        for tc_delta in delta["tool_calls"]:
                                            idx = tc_delta.get("index", 0)
                                            while len(accumulated_tool_calls) <= idx:
                                                accumulated_tool_calls.append(
                                                    {
                                                        "id": "",
                                                        "type": "function",
                                                        "function": {"name": "", "arguments": ""},
                                                    }
                                                )
                                            entry = accumulated_tool_calls[idx]
                                            if tc_delta.get("id"):
                                                entry["id"] = tc_delta["id"]
                                            fn = tc_delta.get("function", {})
                                            if fn.get("name"):
                                                entry["function"]["name"] = fn["name"]
                                            if fn.get("arguments"):
                                                entry["function"]["arguments"] += fn["arguments"]
                                    if has_token and ttft_ms is None:
                                        ttft_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        except Exception:
                            pass
                    yield chunk

            if not has_error and status_val is True:
                total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if ttft_ms is None:
                    ttft_ms = total_duration_ms

                comp_tokens = (usage.get("completion_tokens") if usage else None) or (
                    len(accumulated_content) // 4 if is_estimated else 0
                )
                metrics_payload = {
                    "ttft_ms": ttft_ms,
                    "total_duration_ms": total_duration_ms,
                }
                if comp_tokens and total_duration_ms > 0:
                    metrics_payload["tokens_per_second"] = round(
                        comp_tokens / (total_duration_ms / 1000.0),
                        2,
                    )

                final_chunk = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "metrics": metrics_payload,
                }
                if usage:
                    final_chunk["usage"] = usage

                yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            has_error = True
            status_val = None
            error_details = "Client disconnected / Request Cancelled"
            logger.info("[%s] Stream Cancelled", provider)
            raise
        except Exception as exc:
            has_error = True
            status_val = False
            if isinstance(exc, RuntimeError) or "connect" in str(exc).lower():
                logger.warning("[%s] Stream Connection Failed: %s", provider, exc)
            else:
                logger.error("[%s] Stream Exception: %s", provider, exc, exc_info=True)

            err_msg = str(exc)
            error_details = err_msg
            yield f"data: {json.dumps({'error': {'message': err_msg, 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
        finally:
            total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if ttft_ms is None and (accumulated_content or accumulated_reasoning or accumulated_tool_calls):
                ttft_ms = total_duration_ms
            if ttft_ms is None and status_val is None:
                ttft_ms = total_duration_ms

            if usage is None and status_val in (True, None):
                usage = {
                    "prompt_tokens": max(1, len(json.dumps(messages)) // 4),
                    "completion_tokens": max(1, len(accumulated_content) // 4)
                    if accumulated_content
                    else 0,
                    "thoughts_tokens": max(1, len(accumulated_reasoning) // 4)
                    if accumulated_reasoning
                    else 0,
                }
                is_estimated = True

            if usage and accumulated_content and usage.get("completion_tokens", 0) == 0:
                est_c = max(1, len(accumulated_content) // 4)
                t_tokens = usage.get("thoughts_tokens", 0) or 0
                if t_tokens > est_c:
                    usage["thoughts_tokens"] = t_tokens - est_c
                    usage["completion_tokens"] = est_c
                else:
                    usage["completion_tokens"] = est_c
                    usage["total_tokens"] = usage.get("prompt_tokens", 0) + t_tokens + est_c
                logger.info(
                    "[%s] Corrected 0 completion_tokens to %d for %d generated content characters.",
                    provider,
                    usage["completion_tokens"],
                    len(accumulated_content),
                )
            if usage and accumulated_reasoning and usage.get("thoughts_tokens", 0) == 0:
                logger.warning(
                    "[%s] API reported 0 thoughts_tokens despite generating %d reasoning chars.",
                    provider,
                    len(accumulated_reasoning),
                )

            req_data = {"model": model, "messages": messages}
            for key in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "presence_penalty", "frequency_penalty", "max_tokens", "max_completion_tokens", "seed"):
                if key in kwargs and kwargs[key] is not None:
                    req_data[key] = kwargs[key]
            for key in ("stream", "stream_options", "reasoning_effort", "thinking_budget_tokens", "chat_template_kwargs"):
                if key in kwargs and kwargs[key] is not None:
                    req_data[key] = kwargs[key]
            for key in ("tools", "tool_choice"):
                if key in kwargs and kwargs[key] is not None:
                    req_data[key] = kwargs[key]
            for key, value in kwargs.items():
                if key not in req_data and value is not None:
                    req_data[key] = value

            if status_val is False:
                res_data = {
                    "error": error_details,
                    "metrics": {"total_duration_ms": total_duration_ms},
                }
                if ttft_ms is not None:
                    res_data["metrics"]["ttft_ms"] = ttft_ms
            else:
                msg_data: dict[str, Any] = {
                    "role": "assistant",
                    "content": accumulated_content,
                }
                if accumulated_reasoning:
                    msg_data["reasoning_content"] = accumulated_reasoning
                if accumulated_tool_calls:
                    msg_data["tool_calls"] = accumulated_tool_calls

                metrics_dict = {
                    "ttft_ms": ttft_ms,
                    "total_duration_ms": total_duration_ms,
                }
                comp_tokens = (usage.get("completion_tokens") if usage else None) or (
                    len(accumulated_content) // 4 if is_estimated else 0
                )
                if comp_tokens and total_duration_ms > 0:
                    metrics_dict["tokens_per_second"] = round(
                        comp_tokens / (total_duration_ms / 1000.0),
                        2,
                    )

                res_data = {
                    "choices": [{"message": msg_data}],
                    "metrics": metrics_dict,
                }
                if usage:
                    res_data["usage"] = usage

            asyncio.create_task(
                self.telemetry.log_usage(
                    key_id,
                    provider,
                    model,
                    usage,
                    request_json=json.dumps(req_data, ensure_ascii=False) if req_data else None,
                    response_json=json.dumps(res_data, ensure_ascii=False) if res_data else None,
                    success=status_val,
                    is_estimated=is_estimated,
                    ttft_ms=ttft_ms,
                    duration_ms=total_duration_ms,
                    log_id=log_id,
                )
            )

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
        req_data = {
            "model": model,
            "messages": messages,
            **{key: value for key, value in kwargs.items() if value is not None},
        }
        route_plan = None
        route_resolution_error = None
        try:
            route_plan = await self.route_resolver.resolve("chat", model, provider)
        except ValueError as exc:
            route_resolution_error = str(exc)
        except Exception as exc:
            logger.warning("Model route resolution failed for '%s': %s", model, exc)

        if route_plan is None:
            from core.router.route_types import RoutePlan

            route_plan = RoutePlan.direct(model, provider)

        log_id = await self.telemetry.create_processing_log(
            key_id,
            route_plan.primary_provider or provider or "unknown",
            model,
            "chat",
            req_data,
        )

        if route_resolution_error:
            await self.telemetry.finish_processing_log(
                log_id,
                {"error": route_resolution_error},
                "failed",
                False,
            )
            yield f"data: {json.dumps({'error': {'message': route_resolution_error, 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
            return

        if route_plan.routes:
            success = False
            yielded_any = False
            last_error_chunk = None
            for route in route_plan.routes:
                p_provider = route.provider
                p_model = route.model
                route_kwargs = {**kwargs}

                if p_provider == "local":
                    config = route.default_config
                    if isinstance(config, str):
                        try:
                            config = json.loads(config)
                        except json.JSONDecodeError:
                            config = {}
                    sampling = config.get("local_sampling") if isinstance(config, dict) else None
                    for key, default in LOCAL_SAMPLING_DEFAULTS.items():
                        if route_kwargs.get(key) is None:
                            configured = sampling.get(key) if isinstance(sampling, dict) else None
                            route_kwargs[key] = default if configured is None else configured

                if route_kwargs.get("temperature") is None and route.temperature is not None:
                    try:
                        route_kwargs["temperature"] = float(route.temperature)
                    except (ValueError, TypeError):
                        pass
                if p_provider == "local" and route_kwargs.get("temperature") is None:
                    route_kwargs["temperature"] = LOCAL_TEMPERATURE_DEFAULT

                incoming_think = next(
                    (
                        route_kwargs[key]
                        for key in ("thinking_level", "reasoning_effort", "thinking_budget")
                        if route_kwargs.get(key) not in (None, "")
                    ),
                    None,
                )
                route_kwargs["thinking_level"] = (
                    incoming_think if incoming_think not in (None, "") else route.thinking_level
                )

                if not route_kwargs.get("system_prompt") and route.system_prompt:
                    route_kwargs["system_prompt"] = route.system_prompt

                plugin = self.registry.chat_providers.get(p_provider)
                if not plugin:
                    logger.warning("Provider plugin %s not loaded, skipping route.", p_provider)
                    continue

                route_messages = inject_system_prompt(
                    messages,
                    route_kwargs.pop("system_prompt", None),
                )
                keys_to_try = await self.key_pool.get_keys_for_provider(
                    p_provider,
                    api_key or auth_header,
                )

                for key_val, key_pool_id in keys_to_try:
                    logger.info(
                        "Trying route %s/%s using key %s",
                        p_provider,
                        p_model,
                        key_pool_id or "default",
                    )
                    failed = False
                    yielded_any_this_try = False

                    try:
                        async for chunk in self.stream(
                            plugin=plugin,
                            key_id=key_id,
                            provider=p_provider,
                            model=p_model,
                            messages=route_messages,
                            api_key=key_val,
                            auth_header=auth_header if not key_val else None,
                            log_id=log_id,
                            **route_kwargs,
                        ):
                            if isinstance(chunk, str) and '"error"' in chunk:
                                if not yielded_any_this_try:
                                    logger.warning(
                                        "Route %s/%s failed with error chunk, trying fallback.",
                                        p_provider,
                                        p_model,
                                    )
                                    failed = True
                                    last_error_chunk = chunk
                                    await self.key_pool.mark_key_error(
                                        key_pool_id,
                                        "API returned error chunk",
                                    )
                                    break

                            yielded_any = True
                            yielded_any_this_try = True
                            yield chunk

                        if not failed:
                            success = True
                            break
                    except Exception as exc:
                        logger.error("Route %s/%s failed: %s", p_provider, p_model, exc)
                        await self.key_pool.mark_key_error(key_pool_id, str(exc))
                        failed = True
                        last_error_chunk = (
                            f"data: {json.dumps({'error': {'message': str(exc), 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
                        )

                    if failed and yielded_any_this_try:
                        success = True
                        break

                if success:
                    break

            if not success and not yielded_any:
                error_message = extract_error_message(last_error_chunk)
                final_error = error_message or "All routes and fallbacks failed."
                await self.telemetry.finish_processing_log(
                    log_id,
                    {"error": final_error},
                    "failed",
                    False,
                )
                if last_error_chunk:
                    yield last_error_chunk
                else:
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "error": {
                                    "message": final_error,
                                    "type": "api_error",
                                }
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
            return

        logger.info(
            "No routes found in database for model '%s'. Falling back to direct provider routing.",
            model,
        )
        if provider not in self.registry.chat_providers:
            err_msg = f"Unknown chat provider: {provider}"
            await self.telemetry.finish_processing_log(log_id, {"error": err_msg}, "failed", False)
            yield f"data: {json.dumps({'error': {'message': err_msg, 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
            return

        db_key = self.key_pool.get_db_key(provider)
        route_messages = inject_system_prompt(messages, kwargs.pop("system_prompt", None))

        async for chunk in self.stream(
            self.registry.chat_providers[provider],
            key_id,
            provider,
            model,
            route_messages,
            db_key or api_key,
            auth_header,
            log_id=log_id,
            **kwargs,
        ):
            yield chunk
