"""
dynamic_router.py
-----------------
Yetenek tabanlı (capability-based) LLM yönlendirici.

providers/ altındaki her alt paketin __init__.py'sini tarar:
  - BaseChat impl'leri    → chat_providers
  - BaseEmbed impl'leri   → embed_providers
  - BaseTTS impl'leri     → tts_providers
  - BaseFileUpload impl'leri → file_providers

Combo route (alias → primary/fallback) desteği chat için korunmuştur.
"""
import asyncio
import json
import importlib
import inspect
import logging
import pkgutil
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Any

import providers
from providers.base import BaseChat, BaseEmbed, BaseTTS, BaseFileUpload
from database import db_manager

logger = logging.getLogger("service-router.dynamic")

# Quota aşılmış key'leri kısa süre atla — gereksiz 429 round-trip'lerini keser.
QUOTA_COOLDOWN_SECONDS = 45


def _pool_key_on_quota_cooldown(pool_key: dict) -> bool:
    last_error = pool_key.get("last_error") or ""
    if "RESOURCE_EXHAUSTED" not in last_error and "429" not in last_error:
        return False
    last_at = pool_key.get("last_error_at")
    if not last_at:
        return False
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_at < timedelta(seconds=QUOTA_COOLDOWN_SECONDS)


# ---------------------------------------------------------------------------
#  İç Yardımcılar
# ---------------------------------------------------------------------------

async def _log_usage(app_state, key_id: str | None, provider: str, model: str, usage: dict, request_json: str | None = None, response_json: str | None = None, success: bool = True, capability: str = 'chat'):
    """Arka plan görevi: token kullanımını ve request/response JSON verilerini DB'ye kaydeder."""
    try:
        p = usage.get("prompt_tokens", 0)
        c = usage.get("completion_tokens", 0)
        t = usage.get("thoughts_tokens", 0)
        cost = None

        if success:
            pricing_cache = app_state.pricing_cache if hasattr(app_state, "pricing_cache") else {}
            if model in pricing_cache:
                prices = pricing_cache[model]
                cost = (
                    (p * prices.get("input", 0.0))
                    + (c * prices.get("output", 0.0))
                    + (t * prices.get("think", 0.0))
                )
        else:
            cost = 0.0

        await db_manager.log_request(
            key_id=key_id,
            provider=provider,
            model=model,
            tokens_used=p + c + t,
            prompt_tokens=p,
            completion_tokens=c,
            thoughts_tokens=t,
            cost=cost,
            request_json=request_json,
            response_json=response_json,
            success=success,
            capability=capability
        )
        logger.info(f"Logged usage for {provider}/{model} [{capability}]: (In:{p} Out:{c} Think:{t}) Success: {success}")
    except Exception as e:
        logger.error(f"Failed to log usage: {e}")


# ---------------------------------------------------------------------------
#  Tool-call ID sanitiser
# ---------------------------------------------------------------------------

def _sanitize_tool_ids_for_non_gemini(messages: list[dict]) -> list[dict]:
    """Gemini'nin uzun Base64 tool_call_id değerlerini kısa ID'lere dönüştürür.

    Gemini, thought_signature verisini ``call_<name>__ts__<b64>`` biçiminde tool_call_id'ye
    gömer.  Bu değerler Gemini-dışı modellere gönderildiğinde gereksiz yüzlerce token
    harcar.  Bu fonksiyon:
      1) assistant mesajlarındaki tool_calls[].id içinde ``__ts__`` varsa kısa bir ID ile
         değiştirir (``call_0``, ``call_1``, …).
      2) Takip eden ``role: tool`` mesajlarındaki tool_call_id'yi de aynı kısa ID ile eşler.
    """
    id_map: dict[str, str] = {}
    counter = 0
    out: list[dict] = []

    for msg in messages:
        msg = dict(msg)  # shallow copy – orijinali değiştirme

        # --- assistant + tool_calls ---
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

        # --- tool response ---
        if msg.get("role") == "tool":
            old_tcid = msg.get("tool_call_id", "")
            if old_tcid in id_map:
                msg = dict(msg)
                msg["tool_call_id"] = id_map[old_tcid]

        out.append(msg)
    return out


# ---------------------------------------------------------------------------
#  DynamicLLMRouter
# ---------------------------------------------------------------------------

class DynamicLLMRouter:
    def __init__(self, app_state=None):
        self.app_state = app_state
        self.chat_providers: dict[str, BaseChat] = {}
        self.embed_providers: dict[str, BaseEmbed] = {}
        self.tts_providers: dict[str, BaseTTS] = {}
        self.file_providers: dict[str, BaseFileUpload] = {}
        self._load_providers()

    def _load_providers(self):
        """providers/ altındaki tüm alt paketleri tarar ve yetenek sınıflarını yükler."""
        for _, name, is_pkg in pkgutil.iter_modules(providers.__path__):
            if not is_pkg:
                continue  # Yalnızca alt paketleri (klasörleri) yükle

            module = importlib.import_module(f"providers.{name}")

            for _, obj in inspect.getmembers(module, inspect.isclass):
                pname = getattr(obj, "provider_name", None)
                if not pname:
                    continue

                if issubclass(obj, BaseChat) and obj is not BaseChat:
                    self.chat_providers[pname] = obj()
                    logger.info(f"Loaded chat provider: {pname} ({obj.__name__})")

                if issubclass(obj, BaseEmbed) and obj is not BaseEmbed:
                    self.embed_providers[pname] = obj()
                    logger.info(f"Loaded embed provider: {pname} ({obj.__name__})")

                if issubclass(obj, BaseTTS) and obj is not BaseTTS:
                    self.tts_providers[pname] = obj()
                    logger.info(f"Loaded TTS provider: {pname} ({obj.__name__})")

                if issubclass(obj, BaseFileUpload) and obj is not BaseFileUpload:
                    self.file_providers[pname] = obj()
                    logger.info(f"Loaded file provider: {pname} ({obj.__name__})")

    def _get_db_key(self, provider: str) -> str | None:
        """DB'deki provider API anahtarını döner (gerçek upstream key).
        
        Orion sanal anahtarı (sk-orion-...) ile karıştırılmaz;
        bu key doğrudan upstream API'ye gönderilecek gerçek anahtardır.
        """
        db_keys = getattr(self.app_state, "provider_keys", {})
        key = db_keys.get(provider)
        return key if key else None

    async def _get_keys_for_provider(self, provider: str, client_key: str | None = None) -> list[tuple[str | None, str | None]]:
        """Returns a list of (api_key, key_pool_id) for the provider.
        
        Ordered by priority. If key pool is empty, falls back to legacy config key or client-provided key.
        """
        keys = []
        try:
            pool_keys = await db_manager.get_active_provider_keys(provider)
            usable_keys = [pk for pk in pool_keys if not _pool_key_on_quota_cooldown(pk)]
            skipped = len(pool_keys) - len(usable_keys)
            if skipped:
                logger.info(
                    "Skipping %d provider key(s) for %s on quota cooldown.",
                    skipped,
                    provider,
                )
            if not usable_keys and pool_keys:
                usable_keys = pool_keys
                logger.info(
                    "All active key(s) for %s are on quota cooldown; trying anyway.",
                    provider,
                )
            for pk in usable_keys:
                keys.append((pk["api_key"], pk["id"]))
        except Exception as e:
            logger.error(f"Failed to fetch keys from pool for {provider}: {e}")
            
        if not keys:
            db_key = self._get_db_key(provider)
            if db_key:
                keys.append((db_key, None))
            elif client_key and not client_key.startswith("sk-orion-"):
                keys.append((client_key, None))
            else:
                keys.append((None, None))
        return keys

    # -----------------------------------------------------------------------
    #  Chat
    # -----------------------------------------------------------------------

    async def _stream(
        self, plugin: BaseChat, key_id, provider, model, messages, api_key, auth_header, **kwargs
    ):
        """Pluginden SSE chunk'larını yield eder; internal_usage'ı DB'ye kaydeder. Hataları merkezi loglar."""
        accumulated_content = ""
        accumulated_reasoning = ""
        accumulated_tool_calls: list[dict] = []
        usage = None
        has_error = False
        error_details = None
        
        logger.info(f"Starting chat stream: provider={provider}, model={model}, kwargs={kwargs}")
        
        # Gemini-dışı provider'lara giden mesajlardaki uzun tool_call_id'leri kısalt
        if provider != "gemini":
            messages = _sanitize_tool_ids_for_non_gemini(messages)
        
        try:
            async for chunk in plugin.stream_chat(
                model=model, messages=messages,
                api_key=api_key, auth_header=auth_header, **kwargs
            ):
                if isinstance(chunk, dict) and "internal_usage" in chunk:
                    usage = chunk["internal_usage"]
                else:
                    if isinstance(chunk, str):
                        if '"error":' in chunk:
                            logger.error(f"[{provider}] API Error chunk: {chunk.strip()}")
                            has_error = True
                            error_details = chunk.strip()
                        # Accumulate content and reasoning content from JSON chunk
                        try:
                            data_str = chunk.strip()
                            if data_str.startswith("data:"):
                                data_str = data_str[5:].strip()
                            if data_str and data_str != "[DONE]":
                                chunk_data = json.loads(data_str)
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    if "reasoning_content" in delta and delta["reasoning_content"]:
                                        accumulated_reasoning += delta["reasoning_content"]
                                    if "content" in delta and delta["content"]:
                                        accumulated_content += delta["content"]
                                    if "tool_calls" in delta:
                                        for tc_delta in delta["tool_calls"]:
                                            idx = tc_delta.get("index", 0)
                                            # Yeni tool_call mı, yoksa mevcut olana ekleme mi?
                                            while len(accumulated_tool_calls) <= idx:
                                                accumulated_tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                            entry = accumulated_tool_calls[idx]
                                            if tc_delta.get("id"):
                                                entry["id"] = tc_delta["id"]
                                            fn = tc_delta.get("function", {})
                                            if fn.get("name"):
                                                entry["function"]["name"] = fn["name"]
                                            if fn.get("arguments"):
                                                entry["function"]["arguments"] += fn["arguments"]
                        except Exception:
                            pass
                    yield chunk
        except Exception as e:
            has_error = True
            error_details = str(e)
            if isinstance(e, RuntimeError):
                logger.error(f"[{provider}] Stream Exception: {e}")
            else:
                logger.error(f"[{provider}] Stream Exception: {e}", exc_info=True)
                
            err_msg = f"Provider Exception ({provider}): {str(e)}"
            yield f'data: {json.dumps({"error": {"message": err_msg, "type": "api_error"}}, ensure_ascii=False)}\n\n'
        finally:
            if usage is None:
                usage = {
                    "prompt_tokens": len(json.dumps(messages)) // 4,
                    "completion_tokens": len(accumulated_content) // 4,
                    "thoughts_tokens": len(accumulated_reasoning) // 4
                }

            # Provider'dan gelen usage'ı kontrol et, 0 ise ücret yansımamış demektir, sadece uyar
            if accumulated_content and usage.get("completion_tokens", 0) == 0:
                logger.warning(f"[{provider}] API reported 0 completion_tokens despite generating {len(accumulated_content)} chars.")
            if accumulated_reasoning and usage.get("thoughts_tokens", 0) == 0:
                logger.warning(f"[{provider}] API reported 0 thoughts_tokens despite generating {len(accumulated_reasoning)} reasoning chars.")
                
            req_data = {
                "model": model,
                "messages": messages,
                **kwargs
            }
            if has_error:
                res_data = {
                    "error": error_details or "Unknown error"
                }
            else:
                msg_data: dict[str, Any] = {
                    "role": "assistant",
                    "content": accumulated_content,
                }
                if accumulated_reasoning:
                    msg_data["reasoning_content"] = accumulated_reasoning
                if accumulated_tool_calls:
                    msg_data["tool_calls"] = accumulated_tool_calls
                res_data = {"choices": [{"message": msg_data}]}
            
            asyncio.create_task(
                _log_usage(
                    self.app_state,
                    key_id,
                    provider,
                    model,
                    usage,
                    request_json=json.dumps(req_data, ensure_ascii=False),
                    response_json=json.dumps(res_data, ensure_ascii=False),
                    success=not has_error
                )
            )

    async def run_combo(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Model registry tablosunu sorgulayıp, fallback'leri ve key havuzunu döndürerek sohbet akışını yönetir."""
        routes = []
        try:
            routes = await db_manager.resolve_model_route("chat", model)
        except ValueError as e:
            yield f'data: {json.dumps({"error": {"message": str(e), "type": "api_error"}}, ensure_ascii=False)}\n\n'
            return
        except Exception as e:
            logger.warning(f"Model route resolution failed for '{model}': {e}")

        if routes:
            success = False
            last_error_chunk = None
            for route in routes:
                p_provider = route["provider"]
                p_model = route["name"]
                p_temp = route.get("temperature")
                p_think = route.get("thinking_level")
                
                route_kwargs = {**kwargs}
                
                if p_temp is not None:
                    incoming_temp = route_kwargs.get("temperature")
                    if incoming_temp is None:
                        try:
                            route_kwargs["temperature"] = float(p_temp)
                        except Exception:
                            pass
                        
                if p_think is not None:
                    incoming_think = route_kwargs.get("thinking_level")
                    if incoming_think in (None, ""):
                        route_kwargs["thinking_level"] = p_think
                
                plugin = self.chat_providers.get(p_provider)
                if not plugin:
                    logger.warning(f"Provider plugin {p_provider} not loaded, skipping route.")
                    continue
                
                keys_to_try = await self._get_keys_for_provider(p_provider, api_key or auth_header)
                
                for key_val, key_pool_id in keys_to_try:
                    logger.info(f"Trying route {p_provider}/{p_model} using key {key_pool_id or 'default'}")
                    failed = False
                    yielded_any = False
                    
                    try:
                        async for chunk in self._stream(
                            plugin=plugin,
                            key_id=key_id,
                            provider=p_provider,
                            model=p_model,
                            messages=messages,
                            api_key=key_val,
                            auth_header=auth_header if not key_val else None,
                            **route_kwargs
                        ):
                            if isinstance(chunk, str) and '"error"' in chunk:
                                if not yielded_any:
                                    logger.warning(f"Route {p_provider}/{p_model} failed with error chunk, trying fallback.")
                                    failed = True
                                    last_error_chunk = chunk
                                    if key_pool_id:
                                        await db_manager.mark_provider_key_error(key_pool_id, "API returned error chunk")
                                    break
                            
                            yielded_any = True
                            yield chunk
                        
                        if not failed:
                            success = True
                            break
                            
                    except Exception as e:
                        logger.error(f"Route {p_provider}/{p_model} failed: {e}")
                        if key_pool_id:
                            await db_manager.mark_provider_key_error(key_pool_id, str(e))
                        failed = True
                        last_error_chunk = f'data: {json.dumps({"error": {"message": str(e), "type": "api_error"}}, ensure_ascii=False)}\n\n'
                        
                    if failed and yielded_any:
                        success = True # Stop attempting other fallbacks to prevent corrupted streams
                        break
                        
                if success:
                    break
            
            if not success and not yielded_any:
                if last_error_chunk:
                    yield last_error_chunk
                else:
                    yield f'data: {json.dumps({"error": {"message": "All routes and fallbacks failed.", "type": "api_error"}}, ensure_ascii=False)}\n\n'
            return

        # Backend Registry'de bulunamadıysa: Geriye uyumlu eski yönlendirme akışı (Direct routing)
        logger.info(f"No routes found in database for model '{model}'. Falling back to direct provider routing.")
        if provider not in self.chat_providers:
            err_msg = f"Unknown chat provider: {provider}"
            yield f'data: {json.dumps({"error": {"message": err_msg, "type": "api_error"}}, ensure_ascii=False)}\n\n'
            return

        db_key = self._get_db_key(provider)
        async for chunk in self._stream(
            self.chat_providers[provider], key_id, provider, model,
            messages, db_key or api_key, auth_header, **kwargs
        ):
            yield chunk

    # -----------------------------------------------------------------------
    #  Embeddings
    # -----------------------------------------------------------------------

    async def run_embeddings(
        self,
        provider: str,
        model: str,
        input_text: str | list[str],
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
    ) -> dict:
        """Belirtilen model üzerinden embedding üretir (otomatik route ve key fallbacks ile)."""
        routes = []
        try:
            routes = await db_manager.resolve_model_route("embed", model)
        except Exception as e:
            logger.warning(f"Embed route resolution failed for '{model}': {e}")

        if not routes:
            routes = [{"provider": provider, "name": model}]

        req_data = {
            "model": model,
            "input": input_text,
        }

        last_err = None
        for route in routes:
            p_provider = route["provider"]
            p_model = route["name"]
            
            plugin = self.embed_providers.get(p_provider)
            if not plugin:
                last_err = ValueError(f"Embed provider not available: {p_provider}")
                continue
                
            keys_to_try = await self._get_keys_for_provider(p_provider, api_key or auth_header)
            
            for key_val, key_pool_id in keys_to_try:
                logger.info(f"Routing embeddings to {p_provider} (model={p_model}) using key {key_pool_id or 'default'}")
                try:
                    result = await plugin.generate_embeddings(
                        model=p_model,
                        input_text=input_text,
                        api_key=key_val,
                        auth_header=auth_header if not key_val else None,
                    )
                    
                    # Log success — store vector dimension in completion_tokens
                    p_tokens = 0
                    vector_dim = 0
                    if isinstance(result, dict):
                        if "usage" in result:
                            p_tokens = result["usage"].get("prompt_tokens", 0)
                        try:
                            vector_dim = len(result["data"][0]["embedding"])
                        except Exception:
                            pass
                    
                    usage = {"prompt_tokens": p_tokens, "completion_tokens": vector_dim, "thoughts_tokens": 0}
                    asyncio.create_task(
                        _log_usage(
                            self.app_state,
                            key_id,
                            p_provider,
                            p_model,
                            usage,
                            request_json=json.dumps(req_data, ensure_ascii=False),
                            response_json=json.dumps(result, ensure_ascii=False),
                            success=True,
                            capability='embed'
                        )
                    )
                    return result
                except Exception as e:
                    logger.error(f"Embed route {p_provider}/{p_model} failed: {e}")
                    if key_pool_id:
                        await db_manager.mark_provider_key_error(key_pool_id, str(e))
                    last_err = e
                    
                    # Log attempt failure
                    usage = {"prompt_tokens": 0, "completion_tokens": 0, "thoughts_tokens": 0}
                    res_err = {"error": str(e)}
                    asyncio.create_task(
                        _log_usage(
                            self.app_state,
                            key_id,
                            p_provider,
                            p_model,
                            usage,
                            request_json=json.dumps(req_data, ensure_ascii=False),
                            response_json=json.dumps(res_err, ensure_ascii=False),
                            success=False,
                            capability='embed'
                        )
                    )
                    
        raise last_err or ValueError(f"Could not resolve embed route for model: {model}")

    # -----------------------------------------------------------------------
    #  TTS
    # -----------------------------------------------------------------------

    async def run_speech(
        self,
        provider: str,
        model: str,
        input_text: str,
        voice: str | None = None,
        api_key: str | None = None,
        auth_header: str | None = None,
        key_id: str | None = None,
        **kwargs,
    ) -> tuple[bytes, str]:
        """Belirtilen model üzerinden ses üretir (otomatik route ve key fallbacks ile)."""
        routes = []
        try:
            routes = await db_manager.resolve_model_route("tts", model)
        except Exception as e:
            logger.warning(f"TTS route resolution failed for '{model}': {e}")

        if not routes:
            routes = [{"provider": provider, "name": model}]

        req_data = {
            "model": model,
            "input": input_text,
            "voice": voice,
            **kwargs
        }

        last_err = None
        for route in routes:
            p_provider = route["provider"]
            p_model = route["name"]
            p_temp = route.get("temperature")
            
            route_kwargs = {**kwargs}
            if p_temp is not None and route_kwargs.get("temperature") is None:
                try:
                    route_kwargs["temperature"] = float(p_temp)
                except Exception:
                    pass
            
            plugin = self.tts_providers.get(p_provider)
            if not plugin:
                last_err = ValueError(f"TTS provider not available: {p_provider}")
                continue
                
            keys_to_try = await self._get_keys_for_provider(p_provider, api_key or auth_header)
            
            for key_val, key_pool_id in keys_to_try:
                logger.info(f"Routing TTS to {p_provider} (model={p_model}, voice={voice}) using key {key_pool_id or 'default'}, kwargs={route_kwargs}")
                try:
                    audio_bytes, content_type, usage_meta = await plugin.generate_speech(
                        model=p_model,
                        input_text=input_text,
                        voice=voice,
                        api_key=key_val,
                        auth_header=auth_header if not key_val else None,
                        **route_kwargs
                    )
                    
                    # Log success — store audio tokens
                    import base64
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    prompt_tokens = usage_meta.get("prompt_tokens", 0)
                    completion_tokens = usage_meta.get("completion_tokens", 0)
                    usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "thoughts_tokens": 0}
                    res_success = {
                        "detail": "Audio generation successful",
                        "content_type": content_type,
                        "size_bytes": len(audio_bytes),
                        "estimated_duration_seconds": completion_tokens / 25.0,
                        "audio_base64": audio_b64
                    }
                    asyncio.create_task(
                        _log_usage(
                            self.app_state,
                            key_id,
                            p_provider,
                            p_model,
                            usage,
                            request_json=json.dumps(req_data, ensure_ascii=False),
                            response_json=json.dumps(res_success, ensure_ascii=False),
                            success=True,
                            capability='tts'
                        )
                    )
                    return audio_bytes, content_type
                except Exception as e:
                    logger.error(f"TTS route {p_provider}/{p_model} failed: {e}")
                    if key_pool_id:
                        await db_manager.mark_provider_key_error(key_pool_id, str(e))
                    last_err = e
                    
                    # Log attempt failure
                    usage = {"prompt_tokens": len(input_text), "completion_tokens": 0, "thoughts_tokens": 0}
                    res_err = {"error": str(e)}
                    asyncio.create_task(
                        _log_usage(
                            self.app_state,
                            key_id,
                            p_provider,
                            p_model,
                            usage,
                            request_json=json.dumps(req_data, ensure_ascii=False),
                            response_json=json.dumps(res_err, ensure_ascii=False),
                            success=False,
                            capability='tts'
                        )
                    )
                    
        raise last_err or ValueError(f"Could not resolve TTS route for model: {model}")

    # -----------------------------------------------------------------------
    #  File Upload
    # -----------------------------------------------------------------------

    async def upload_file(
        self,
        provider: str,
        file_bytes: bytes,
        mime_type: str,
        display_name: str,
        api_key: str | None = None,
    ) -> dict:
        """Belirtilen provider üzerinden dosya yükler."""
        plugin = self.file_providers.get(provider)
        if not plugin:
            raise ValueError(f"File upload provider not available: {provider}")

        db_key = self._get_db_key(provider)
        logger.info(f"Routing file upload to {provider}: {display_name} ({mime_type})")
        return await plugin.upload_file(
            file_bytes=file_bytes,
            mime_type=mime_type,
            display_name=display_name,
            api_key=db_key or api_key,
        )

    # -----------------------------------------------------------------------
    #  Yetenek Sorgusu
    # -----------------------------------------------------------------------

    def get_capabilities(self) -> dict:
        """Her provider için desteklenen yetenekleri döner (admin/debug için)."""
        all_providers = set(self.chat_providers) | set(self.embed_providers) \
                        | set(self.tts_providers) | set(self.file_providers)
        return {
            p: {
                "chat": p in self.chat_providers,
                "embed": p in self.embed_providers,
                "tts": p in self.tts_providers,
                "file_upload": p in self.file_providers,
            }
            for p in sorted(all_providers)
        }
