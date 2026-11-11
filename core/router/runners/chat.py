from core.secret_guard import redact
from core.key_policy import authorize_attempt, ACCESS_MESSAGE
from core.logging_utils import log_chat_stream_start, log_chat_failure
from fastapi import HTTPException
import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator

from providers.base import BaseChat
from core.outgoing import logged, record_outgoing
from core.local_chat_defaults import LOCAL_SAMPLING_DEFAULTS  # only its keys: which sampling values a model can have
from core.prompt_cache import normalize_usage
from core import token_estimate as estimate

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


def is_error_chunk(chunk) -> bool:
    if not isinstance(chunk, str):
        return False
    data = chunk.strip()
    if data.startswith("data:"):
        data = data[5:].strip()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and "error" in payload


def is_key_specific_error(error_str: str | None) -> bool:
    """Return True if the error is likely due to the specific API key (auth, quota, rate limit, provider network).
    Return False if the error is client-side or model/modality incompatibility that trying another key cannot fix.
    """
    if not error_str:
        return True
    err = error_str.lower()

    # Non-retryable model/modality/client errors (trying another key won't help):
    non_retryable_markers = (
        "does not support",
        "no endpoints found that support",
        "modality is not enabled",
        "modality not supported",
        "unsupported modality",
        "context_length_exceeded",
        "maximum context length",
        "invalid_request_error",
        "content policy",
        "safety filter",
        "blocked by safety",
    )
    if any(marker in err for marker in non_retryable_markers):
        return False

    # Retryable key/quota/network errors:
    retryable_markers = (
        "401", "403", "unauthorized", "authentication", "api key", "api_key",
        "429", "rate limit", "quota", "credits", "insufficient",
        "500", "502", "503", "504", "timeout", "connection",
    )
    if any(marker in err for marker in retryable_markers):
        return True

    # Generic 400 or 404 without auth/quota mentions are client/model errors:
    if "400" in err or "404" in err:
        return False

    return True


class _ProcessingLog:
    """The request-log row of one run_combo call, once it has been created."""
    __slots__ = ("id",)

    def __init__(self) -> None:
        self.id: int | None = None


class ChatRunner:
    MAX_TRACKED_LOGS = 4096

    def __init__(self, registry, route_resolver, key_pool, telemetry) -> None:
        self.registry = registry
        self.route_resolver = route_resolver
        self.key_pool = key_pool
        self.telemetry = telemetry
        # Request logs whose final state is written by someone else already (stream() or an explicit finish).
        self._settled_logs: dict[int, None] = {}
        self._log_writers: set[asyncio.Task] = set()

    def _settle(self, log_id: int | None) -> None:
        if log_id is None:
            return
        self._settled_logs[log_id] = None
        while len(self._settled_logs) > self.MAX_TRACKED_LOGS:
            del self._settled_logs[next(iter(self._settled_logs))]

    async def _finish_log(self, lease: _ProcessingLog, response: dict, status: str, success: bool | None) -> None:
        self._settle(lease.id)
        await self.telemetry.finish_processing_log(lease.id, response, status, success)

    async def _close_unsettled_log(self, log_id: int | None, status: str, success: bool | None, message: str) -> None:
        """A request that ended before stream() took over its log (client gone, access denied, an error)."""
        if log_id is None:
            return
        if log_id in self._settled_logs:
            del self._settled_logs[log_id]
            return
        try:
            await asyncio.shield(self.telemetry.finish_processing_log(log_id, {"error": message}, status, success))
        except Exception as exc:
            logger.warning("Could not close request log %s: %s", log_id, exc)

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
        # From here this generator writes the log's final state, also when the client leaves (finally below).
        self._settle(log_id)
        accumulated_content = ""
        accumulated_reasoning = ""
        accumulated_tool_calls: list[dict] = []
        usage = None
        has_error = False
        status_val = True
        error_details = None
        is_estimated = False
        generation_id = None

        start_time = time.perf_counter()
        ttft_ms: float | None = None

        log_chat_stream_start(logger, provider, model, messages, kwargs)

        if provider != "gemini":
            messages = sanitize_tool_ids_for_non_gemini(messages)

        # The request log shows the body the provider was sent, as it was sent (core/outgoing.py).
        sent = record_outgoing()
        shown = False

        try:
            async for chunk in plugin.stream_chat(
                model=model,
                messages=messages,
                api_key=api_key,
                auth_header=auth_header,
                **kwargs,
            ):
                if not shown and sent.body is not None:
                    shown = True
                    await self.telemetry.update_processing_request(log_id, logged(sent.body, model))
                chunk = redact(chunk)
                if isinstance(chunk, dict) and "internal_usage" in chunk:
                    usage = normalize_usage(chunk["internal_usage"])
                elif isinstance(chunk, dict) and "internal_generation_id" in chunk:
                    generation_id = chunk["internal_generation_id"]
                else:
                    if isinstance(chunk, str):
                        try:
                            data_str = chunk.strip()
                            if data_str.startswith("data:"):
                                data_str = data_str[5:].strip()
                            if data_str and data_str != "[DONE]":
                                chunk_data = json.loads(data_str)
                                if "error" in chunk_data:
                                    has_error = True
                                    status_val = False
                                    error = chunk_data["error"]
                                    if isinstance(error, dict) and error.get("message"):
                                        error_details = str(error["message"])
                                    elif error:
                                        error_details = str(error)
                                    log_chat_failure(logger, provider, model, error_details or "Empty error response", log_id)
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
                    estimate.text_tokens(accumulated_content) if is_estimated else 0
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
            log_chat_failure(logger, provider, model, exc, log_id)
            if not shown and sent.body is not None:
                # Refused before any answer (DeepSeek's 401): the log still shows what the provider was sent.
                shown = True
                await self.telemetry.update_processing_request(log_id, logged(sent.body, model))

            err_msg = redact(str(exc))
            error_details = err_msg
            yield f"data: {json.dumps({'error': {'message': err_msg, 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
        finally:
            total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if ttft_ms is None and (accumulated_content or accumulated_reasoning or accumulated_tool_calls):
                ttft_ms = total_duration_ms
            if ttft_ms is None and status_val is None:
                ttft_ms = total_duration_ms

            if usage is None and status_val in (True, None):
                # By script (Chinese counts about a token a character, Latin about four); the tool definitions
                # go to the model too, often more than the chat itself.
                usage = {
                    "prompt_tokens": estimate.prompt_tokens(messages, kwargs.get("tools")),
                    "completion_tokens": max(1, estimate.text_tokens(accumulated_content)) if accumulated_content else 0,
                    "thoughts_tokens": max(1, estimate.text_tokens(accumulated_reasoning)) if accumulated_reasoning else 0,
                }
                is_estimated = True

            if usage and accumulated_content and usage.get("completion_tokens", 0) == 0:
                est_c = max(1, estimate.text_tokens(accumulated_content))
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
            if sent.body is not None:
                req_data = logged(sent.body, model)  # what was really sent; the summary above only when nothing was

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
                    estimate.text_tokens(accumulated_content) if is_estimated else 0
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

            writer = asyncio.create_task(
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
            # The loop holds tasks weakly; without this a log write could be collected before it finishes.
            self._log_writers.add(writer)
            writer.add_done_callback(self._log_writers.discard)
            if status_val is None and is_estimated and generation_id:
                # Stopped before the usage chunk: the estimate above is replaced by what the provider billed,
                # when it can tell afterwards (OpenRouter's generation stats).
                recovery = asyncio.create_task(self._recover_usage(
                    plugin, generation_id, api_key, auth_header, writer, key_id, provider, model, req_data, res_data,
                    ttft_ms=ttft_ms, duration_ms=total_duration_ms, log_id=log_id))
                self._log_writers.add(recovery)
                recovery.add_done_callback(self._log_writers.discard)

    async def _recover_usage(self, plugin, generation_id, api_key, auth_header, writer, key_id, provider, model,
                             req_data, res_data, **log):
        try:
            usage = await plugin.recover_usage(generation_id, api_key=api_key, auth_header=auth_header)
        except Exception as exc:
            logger.warning("[%s] Usage of stopped generation %s not recovered: %s", provider, generation_id, exc)
            return
        if not usage:
            return
        usage = normalize_usage(usage)
        await writer  # The estimate is written first, so this one is the last word.
        res_data = {**res_data, "usage": usage}
        await self.telemetry.log_usage(
            key_id, provider, model, usage,
            request_json=json.dumps(req_data, ensure_ascii=False) if req_data else None,
            response_json=json.dumps(res_data, ensure_ascii=False),
            success=None, is_estimated=False, **log)
        logger.info("[%s] Stopped generation %s: usage recovered from the provider", provider, generation_id)

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
        """Stream a chat; its request log never stays "processing".

        stream() writes the final state of every request that reached a provider. One that ends before that
        (the client left while keys were being picked, access denied, an unexpected error) is closed here.
        """
        lease = _ProcessingLog()
        outcome = ("failed", False, "Request ended without a result")
        try:
            async for chunk in self._run_combo(lease, provider, model, messages, api_key, auth_header, key_id, **kwargs):
                yield chunk
        except Exception as exc:
            outcome = ("failed", False, redact(str(exc)))
            raise
        except BaseException:
            outcome = ("interrupted", None, "Client disconnected / Request Cancelled")
            raise
        finally:
            await self._close_unsettled_log(lease.id, *outcome)

    async def _run_combo(
        self,
        lease: _ProcessingLog,
        provider: str | None,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        # Standardize thinking key to "thinking" in req_data (which is saved as request_json)
        think_val = next(
            (
                kwargs[k]
                for k in ("thinking", "thinking_level", "reasoning_effort", "thinking_budget")
                if kwargs.get(k) not in (None, "")
            ),
            None,
        )
        filtered_kwargs = {
            k: v for k, v in kwargs.items()
            if v is not None and k not in ("thinking", "thinking_level", "reasoning_effort", "thinking_budget", "is_playground", "bypass_defaults")
        }
        if think_val not in (None, "", "api_default"):
            filtered_kwargs["thinking"] = think_val

        req_data = {
            "model": model,
            "messages": messages,
            **filtered_kwargs,
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

        if not route_resolution_error and route_plan.is_group and think_val not in (None, "", "api_default"):
            route_resolution_error = (
                f"Thinking cannot be specified when requesting model group '{model}'. "
                "Thinking settings must be configured per model in group settings."
            )

        log_id = await self.telemetry.create_processing_log(
            key_id,
            route_plan.primary_provider or provider or "unknown",
            model,
            "chat",
            req_data,
        )
        lease.id = log_id

        if route_resolution_error:
            await self._finish_log(
                lease,
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
                    # Only the model's own saved values (the page shows them); none saved: the local server's own.
                    for key in LOCAL_SAMPLING_DEFAULTS:
                        configured = sampling.get(key) if isinstance(sampling, dict) else None
                        if route_kwargs.get(key) is None and configured not in (None, ""):
                            route_kwargs[key] = configured

                bypass_defaults = (
                    kwargs.get("bypass_defaults", False)
                    or kwargs.get("is_playground", False)
                    or route_kwargs.pop("bypass_defaults", False)
                    or route_kwargs.pop("is_playground", False)
                )

                if not bypass_defaults:
                    if route_kwargs.get("temperature") is None and route.temperature is not None:
                        try:
                            route_kwargs["temperature"] = float(route.temperature)
                        except (ValueError, TypeError):
                            pass
                    # No temperature saved for the model and none asked for: none is sent (the provider's own
                    # default). The Router puts in only what the model page shows as a value.

                    if not route_kwargs.get("system_prompt") and route.system_prompt:
                        route_kwargs["system_prompt"] = route.system_prompt

                incoming_think = next(
                    (
                        route_kwargs[key]
                        for key in ("thinking", "thinking_level", "reasoning_effort", "thinking_budget")
                        if route_kwargs.get(key) not in (None, "")
                    ),
                    None,
                )
                if incoming_think == "api_default" or (bypass_defaults and not incoming_think):
                    route_kwargs["thinking"] = None
                else:
                    route_kwargs["thinking"] = (
                        incoming_think if incoming_think not in (None, "") else route.thinking_level
                    )

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
                    key_id=key_id,
                )

                should_retry_keys = True
                for key_val, key_pool_id in keys_to_try:
                    try:
                        await authorize_attempt(key_id, p_provider, key_pool_id, key_val)
                    except HTTPException as denied:
                        if denied.status_code != 403:
                            raise
                        last_error_chunk = "data: " + json.dumps({"error": {"message": ACCESS_MESSAGE}}) + "\n\n"
                        continue
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
                            auth_header=None,
                            log_id=log_id,
                            **route_kwargs,
                        ):
                            if is_error_chunk(chunk):
                                if not yielded_any_this_try:
                                    failed = True
                                    last_error_chunk = chunk
                                    err_msg = extract_error_message(chunk) or "API returned error chunk"
                                    if is_key_specific_error(err_msg):
                                        await self.key_pool.mark_key_error(
                                            key_pool_id,
                                            err_msg,
                                        )
                                    else:
                                        logger.info(
                                            "Route %s/%s | log_id=%s | Key rotation skipped: request/model error; checking fallback routes.",
                                            p_provider,
                                            p_model,
                                            log_id if log_id is not None else "-",
                                        )
                                        should_retry_keys = False
                                    break

                            yielded_any = True
                            yielded_any_this_try = True
                            yield chunk

                        if not failed:
                            success = True
                            break
                    except Exception as exc:
                        log_chat_failure(logger, p_provider, p_model, exc, log_id)
                        err_str = redact(str(exc))
                        if is_key_specific_error(err_str):
                            await self.key_pool.mark_key_error(key_pool_id, err_str)
                        else:
                            logger.info(
                                "Route %s/%s | log_id=%s | Key rotation skipped: request/model error; checking fallback routes.",
                                p_provider,
                                p_model,
                                log_id if log_id is not None else "-",
                            )
                            should_retry_keys = False
                        failed = True
                        last_error_chunk = (
                            f"data: {json.dumps({'error': {'message': err_str, 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
                        )

                    if not should_retry_keys:
                        break

                    if failed and yielded_any_this_try:
                        success = True
                        break

                if success:
                    break

            if not success and not yielded_any:
                error_message = extract_error_message(last_error_chunk)
                final_error = error_message or (ACCESS_MESSAGE if key_id else "All routes and fallbacks failed.")
                await self._finish_log(
                    lease,
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
            await self._finish_log(lease, {"error": err_msg}, "failed", False)
            yield f"data: {json.dumps({'error': {'message': err_msg, 'type': 'api_error'}}, ensure_ascii=False)}\n\n"
            return

        keys = await self.key_pool.get_keys_for_provider(provider, api_key or auth_header, key_id=key_id)
        if not keys:
            raise HTTPException(403, ACCESS_MESSAGE)
        await authorize_attempt(key_id, provider, keys[0][1], keys[0][0])
        db_key = keys[0][0]
        route_messages = inject_system_prompt(messages, kwargs.pop("system_prompt", None))

        async for chunk in self.stream(
            self.registry.chat_providers[provider],
            key_id,
            provider,
            model,
            route_messages,
            db_key,
            None,
            log_id=log_id,
            **kwargs,
        ):
            yield chunk
