import asyncio
import json
import logging
import time
from core.tts_archive import ArchiveSession, background
from core.secret_guard import redact
from core.key_policy import authorize_attempt, ACCESS_MESSAGE
from core.logging_utils import format_tts_kwargs_summary, log_provider_failure
from fastapi import HTTPException

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


# The dashboard's own notes in a model's settings (which engine view was on screen, each engine's values kept
# apart): not speech settings, never given to a provider nor shown as sent.
_DASHBOARD_NOTES = ("engine", "per_engine")
# A local TTS model's settings that belong to one engine (the dashboard keeps them per engine, in "per_engine").
_ENGINE_FIELDS = ("voice", "gender", "age", "pitch", "style", "accent", "dialect", "language", "speed", "steps",
                  "seed", "tts_instruct")
# OmniVoice's character design: VoxCPM2 takes a written description (tts_instruct) instead.
_OMNIVOICE_DESIGN = ("gender", "age", "pitch", "style", "accent", "dialect")
# What an engine does not take, so the model page does not show it for that engine: a value saved there (by an
# older page, or while the other engine was on screen) is not sent. VoxCPM2 has no speed or language setting.
_NOT_TAKEN = {"voxcpm2": _OMNIVOICE_DESIGN + ("speed", "language")}


def _engine_defaults(defaults: dict, engine: str | None) -> dict:
    """The model's settings for the engine that runs now. The top-level fields are only the engine that was on
    screen when the model was saved: with the other engine running they would carry its values over (OmniVoice's
    "female, young adult" made VoxCPM2 design a new voice instead of its warm-up voice). Engine unknown (the
    service did not answer): the settings as saved."""
    if not engine:
        return defaults
    per_engine = defaults.get("per_engine") if isinstance(defaults.get("per_engine"), dict) else {}
    own = per_engine.get(engine)
    shared = {k: v for k, v in defaults.items() if k not in _ENGINE_FIELDS}
    if isinstance(own, dict):
        chosen = {**shared, **{k: v for k, v in own.items() if k in _ENGINE_FIELDS}}
    elif str(defaults.get("engine") or "omnivoice").lower() == engine:
        chosen = dict(defaults)
    else:
        chosen = shared  # nothing saved for this engine: its own defaults
    for key in _NOT_TAKEN.get(engine, ()):
        chosen.pop(key, None)
    return chosen


def _route_request(route, kwargs: dict, voice: str | None, engine: str | None = None) -> tuple[dict, str | None, dict]:
    """What goes to the provider on this route: the caller's values, and the model's saved settings (Router →
    Modeller) for whatever the caller left out. Also returns those filled-in values alone, so the request log shows
    them: a caller that sent no seed must not look as if it spoke with the engine's default when the model's
    saved seed was used. engine: the local TTS engine running now, whose own saved settings apply."""
    defaults = {k: v for k, v in _engine_defaults(_coerce_default_config(route.default_config), engine).items()
                if k not in _DASHBOARD_NOTES}
    given = {key: value for key, value in kwargs.items() if value is not None and value != ""}
    route_kwargs = {key: value for key, value in defaults.items() if value is not None and value != ""}
    route_kwargs.update(given)

    if route.temperature is not None and route_kwargs.get("temperature") is None:
        try:
            route_kwargs["temperature"] = float(route.temperature)
        except Exception:
            pass

    if not route_kwargs.get("tts_instruct") and not route_kwargs.get("instructions"):
        instructs = []
        for field in ("gender", "age", "pitch", "style", "accent", "dialect"):
            val = route_kwargs.get(field)
            if val and str(val).strip() and str(val).strip().lower() != "auto":
                instructs.append(str(val).strip())
        if instructs:
            route_kwargs["tts_instruct"] = ", ".join(instructs)

    # No voice given (or "default"): the provider's saved default voice. "none" is "no voice at all":
    # the description (or the engine's own voice) speaks, not the saved clone.
    target_voice = voice
    if (not target_voice or str(target_voice).lower() in ("default", "alloy")) and defaults.get("voice"):
        target_voice = defaults.get("voice")

    clean_kwargs = {
        k: v for k, v in route_kwargs.items()
        if k not in ("voice", "model", "input_text", "api_key", "auth_header", "_archive_metadata")
    }
    added = {
        k: v for k, v in clean_kwargs.items()
        if k not in given and not k.startswith("_")
    }
    if target_voice != voice:
        added["voice"] = target_voice
    return clean_kwargs, target_voice, added


class TTSRunner:
    def __init__(self, registry, route_resolver, key_pool, telemetry) -> None:
        self.registry = registry
        self.route_resolver = route_resolver
        self.key_pool = key_pool
        self.telemetry = telemetry

    async def _log_with_archive(self, archive, *, requested_model, input_text, **log_kwargs):
        response = json.loads(log_kwargs["response_json"])
        if archive:
            response.update(await archive.finish(
                log_id=log_kwargs.get("log_id"), provider=log_kwargs["provider"],
                requested_model=requested_model, resolved_model=log_kwargs["model"], text=input_text,
                status="completed" if log_kwargs["success"] is True else "interrupted",
            ))
        log_kwargs["response_json"] = json.dumps(response, ensure_ascii=False)
        await self.telemetry.log_usage(**log_kwargs)

    async def _show_added(self, log_id, req_data: dict, added: dict) -> None:
        """Puts what the Router itself filled in from the model's settings into the logged request, under its own
        key: the caller's request stays as it came, and nothing the provider got is hidden."""
        if added == req_data.get("added_by_router", {}):
            return
        if added:
            req_data["added_by_router"] = added
        else:
            req_data.pop("added_by_router", None)
        await self.telemetry.update_processing_request(log_id, req_data)

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

        req_data = {"model": model, "input": input_text, "voice": voice, "stream": False, **kwargs}
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
                plugin = self.registry.tts_providers.get(p_provider)
                if not plugin:
                    last_err = ValueError(f"TTS provider not available: {p_provider}")
                    continue
                engine = await plugin.active_engine() if hasattr(plugin, "active_engine") else None
                clean_kwargs, target_voice, added = _route_request(route, kwargs, voice, engine)
                if not target_voice and hasattr(plugin, "default_voice"):
                    # A provider that needs a voice (OpenAI, Gemini) would pick one itself: named here, and logged.
                    try:
                        target_voice = plugin.default_voice(p_model)
                        added["voice"] = target_voice
                    except Exception:
                        pass

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
                    tts_params = format_tts_kwargs_summary(clean_kwargs)
                    logger.info(
                        "Routing TTS to %s (model=%s, voice=%s) using key %s%s%s",
                        p_provider,
                        p_model,
                        target_voice,
                        key_pool_id or "default",
                        f", params={tts_params}" if tts_params else "",
                        f", from model settings={added}" if added else "",
                    )
                    await self._show_added(log_id, req_data, added)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("TTS route debug: keys=%s", sorted(clean_kwargs.keys()))
                    try:
                        audio_bytes, content_type, usage_meta = await plugin.generate_speech(
                            model=p_model,
                            input_text=input_text,
                            voice=target_voice,
                            api_key=key_val,
                            auth_header=None,
                            **clean_kwargs,
                        )

                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        archive = ArchiveSession()
                        archive.set_metadata(usage_meta.get("audio_format", {"content_type": content_type}))
                        async def archive_response(source):
                            for offset in range(0, len(source), 65536):
                                if archive.error:
                                    break
                                while archive.queued_bytes > 1024 * 1024 and not archive.error:
                                    await asyncio.sleep(0.01)
                                archive.feed(source[offset:offset + 65536])
                                await asyncio.sleep(0)
                            del source
                            await self._log_with_archive(archive, requested_model=model, input_text=input_text,
                                key_id=key_id, provider=p_provider, model=p_model, usage=usage,
                                request_json=json.dumps(req_data, ensure_ascii=False),
                                response_json=json.dumps(res_success, ensure_ascii=False), success=True,
                                capability="tts", duration_ms=duration_ms, log_id=log_id)

                        prompt_tokens = usage_meta.get("prompt_tokens")
                        completion_tokens = usage_meta.get("completion_tokens")
                        usage = None if prompt_tokens is None and completion_tokens is None else {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "thoughts_tokens": 0,
                        }
                        res_success = {
                            "content_type": content_type,
                            "size_bytes": len(audio_bytes),
                            "estimated_duration_seconds": completion_tokens / 25.0 if completion_tokens is not None else None,
                            "metrics": {"total_duration_ms": duration_ms},
                        }
                        background(archive_response(audio_bytes if not archive.error else b""))
                        response_metadata = {
                            key: value for key, value in res_success.items()
                        }
                        return audio_bytes, content_type, response_metadata
                    except Exception as exc:
                        log_provider_failure(logger, "TTS", p_provider, p_model, exc, log_id)
                        exc = RuntimeError(redact(str(exc)))
                        await self.key_pool.mark_key_error(key_pool_id, str(exc))
                        last_err = exc
        except asyncio.CancelledError:
            res_err = {"error": "Client disconnected / Request Cancelled"}
            background(
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

        final_error = last_err or (HTTPException(403, ACCESS_MESSAGE) if key_id else ValueError(f"Could not resolve TTS route for model: {model}"))
        await self.telemetry.finish_processing_log(log_id, {"error": str(final_error)}, "failed", False)
        raise final_error

    async def run_speech_stream(
        self,
        provider: str | None,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ):
        route_plan = RoutePlan.direct(model, provider)
        try:
            route_plan = await self.route_resolver.resolve("tts", model, provider)
        except Exception as exc:
            logger.warning("TTS route resolution failed for '%s': %s", model, exc)

        req_data = {"model": model, "input": input_text, "voice": voice, "stream": True, **kwargs}
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
        stream_started = False
        total_bytes = 0
        archive = None
        try:
            for route in route_plan.routes:
                p_provider = route.provider
                p_model = route.model
                plugin = self.registry.tts_providers.get(p_provider)
                if not plugin:
                    last_err = ValueError(f"TTS provider not available: {p_provider}")
                    continue
                engine = await plugin.active_engine() if hasattr(plugin, "active_engine") else None
                clean_kwargs, target_voice, added = _route_request(route, kwargs, voice, engine)
                if not target_voice and hasattr(plugin, "default_voice"):
                    # A provider that needs a voice (OpenAI, Gemini) would pick one itself: named here, and logged.
                    try:
                        target_voice = plugin.default_voice(p_model)
                        added["voice"] = target_voice
                    except Exception:
                        pass

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
                    tts_params = format_tts_kwargs_summary(clean_kwargs)
                    logger.info(
                        "Routing TTS stream to %s (model=%s, voice=%s) using key %s%s%s",
                        p_provider,
                        p_model,
                        target_voice,
                        key_pool_id or "default",
                        f", params={tts_params}" if tts_params else "",
                        f", from model settings={added}" if added else "",
                    )
                    await self._show_added(log_id, req_data, added)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("TTS route stream debug: keys=%s", sorted(clean_kwargs.keys()))
                    try:
                        archive = ArchiveSession()
                        stream_gen = plugin.generate_speech_stream(
                            model=p_model,
                            input_text=input_text,
                            voice=target_voice,
                            api_key=key_val,
                            auth_header=None,
                            **clean_kwargs,
                            _archive_metadata=archive.set_metadata,
                        )
                        try:
                            async for chunk in stream_gen:
                                stream_started = True
                                total_bytes += len(chunk)
                                archive.feed(chunk)
                                yield chunk
                        finally:
                            close_stream = getattr(stream_gen, "aclose", None)
                            if close_stream:
                                await close_stream()
                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        content_type = archive.metadata.get("content_type", "audio/pcm")
                        res_success = {
                            "content_type": content_type,
                            "size_bytes": total_bytes,
                            "metrics": {"total_duration_ms": duration_ms},
                        }
                        background(
                            self._log_with_archive(
                                archive, requested_model=model, input_text=input_text,
                                key_id=key_id, provider=p_provider, model=p_model, usage=None,
                                request_json=json.dumps(req_data, ensure_ascii=False),
                                response_json=json.dumps(res_success, ensure_ascii=False),
                                success=True,
                                capability="tts",
                                duration_ms=duration_ms,
                                log_id=log_id,
                            )
                        )
                        return
                    except Exception as exc:
                        log_provider_failure(logger, "TTS stream", p_provider, p_model, exc, log_id)
                        if stream_started:
                            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                            content_type = archive.metadata.get("content_type", "audio/pcm")
                            res_err = {
                                "stopped_early": True,
                                "content_type": content_type,
                                "size_bytes": total_bytes,
                                "error": redact(str(exc)),
                                "metrics": {"total_duration_ms": duration_ms},
                            }
                            background(
                                self._log_with_archive(
                                    archive, requested_model=model, input_text=input_text,
                                    key_id=key_id, provider=p_provider, model=p_model, usage=None,
                                    request_json=json.dumps(req_data, ensure_ascii=False),
                                    response_json=json.dumps(res_err, ensure_ascii=False),
                                    success=False,
                                    capability="tts",
                                    duration_ms=duration_ms,
                                    log_id=log_id,
                                )
                            )
                            raise
                        if archive:
                            await archive.finish(log_id=log_id, provider=p_provider, requested_model=model,
                                resolved_model=p_model, text=input_text, status="interrupted")
                            archive = None
                        exc = RuntimeError(redact(str(exc)))
                        await self.key_pool.mark_key_error(key_pool_id, str(exc))
                        last_err = exc
        except (asyncio.CancelledError, GeneratorExit):
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            content_type = archive.metadata.get("content_type", "audio/pcm") if archive else "audio/pcm"
            res_err = {
                "stopped_early": total_bytes > 0,
                "content_type": content_type,
                "size_bytes": total_bytes,
                "error": "Client disconnected / Request Cancelled",
                "metrics": {"total_duration_ms": duration_ms},
            }
            background(
                self._log_with_archive(
                    archive, requested_model=model, input_text=input_text,
                    key_id=key_id, provider=p_provider, model=p_model, usage=None,
                    request_json=json.dumps(req_data, ensure_ascii=False),
                    response_json=json.dumps(res_err, ensure_ascii=False),
                    success=None,
                    capability="tts",
                    duration_ms=duration_ms,
                    log_id=log_id,
                )
            )
            raise

        final_error = last_err or (HTTPException(403, ACCESS_MESSAGE) if key_id else ValueError(f"Could not resolve TTS route for model: {model}"))
        await self.telemetry.finish_processing_log(log_id, {"error": str(final_error)}, "failed", False)
        raise final_error
