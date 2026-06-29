"""
api/admin.py
------------
Admin paneli için UI sunumu ve CRUD endpoint'leri.
"""
import hashlib
import json
import logging
import os
import secrets

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse, Response

from database import db_manager
from core.dependencies import verify_admin

logger = logging.getLogger("service-router.admin")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Admin UI dizini: bu dosyanın bulunduğu konumdan (api/) iki üst dizin → dashboard/
_DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:4] + "*" * 10 + key[-4:] if len(key) > 8 else "***"


def _require_text(value, field_name: str) -> str:
    value = (value or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return value

def _parse_default_config(val):
    if not val:
        return {}
    if isinstance(val, str):
        import json as _json
        try:
            val = _json.loads(val)
        except Exception:
            return {}
    if isinstance(val, dict):
        return val
    return {}



@router.get("/api/settings/is-default-password")
async def is_default_password():
    from core.security import verify_secret
    from core import config
    hashed_db = await db_manager.get_config("admin_secret_hash")
    default_pass = config.ADMIN_SECRET
    
    if hashed_db:
        is_default = verify_secret(default_pass, hashed_db)
    else:
        is_default = True
        
    return {"is_default": is_default, "default_password": default_pass if is_default else None}


@router.put("/api/settings/admin-secret", dependencies=[Depends(verify_admin)])
async def update_admin_secret(request: Request):
    from core.security import verify_secret, hash_secret
    import json
    try:
        body = await request.json()
        old_secret = (body.get("old_secret") or "").strip()
        new_secret = (body.get("new_secret") or body.get("admin_secret") or "").strip()
        
        if not old_secret:
            raise HTTPException(status_code=400, detail="Current admin secret is required")
        if not new_secret:
            raise HTTPException(status_code=400, detail="New admin secret cannot be empty")
            
        # Verify old secret
        hashed_db = await db_manager.get_config("admin_secret_hash")
        if hashed_db:
            if not verify_secret(old_secret, hashed_db):
                raise HTTPException(status_code=400, detail="Incorrect current admin secret")
        else:
            from core import config
            if old_secret != config.ADMIN_SECRET:
                raise HTTPException(status_code=400, detail="Incorrect current admin secret")
        
        # Hash and store new secret
        hashed = hash_secret(new_secret)
        await db_manager.upsert_config("admin_secret_hash", json.dumps(hashed))
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating admin secret: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  API Keys
# ---------------------------------------------------------------------------

@router.get("/api/keys", dependencies=[Depends(verify_admin)])
async def get_admin_keys():
    """Tüm sanal API anahtarlarını listeler."""
    try:
        rows = await db_manager.fetch(
            "SELECT id, name, is_active, budget, used_amount, created_at "
            "FROM router_virtual_keys ORDER BY created_at DESC"
        )
        return {"keys": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/keys", dependencies=[Depends(verify_admin)])
async def create_admin_key(request: Request):
    """Yeni bir sanal API anahtarı oluşturur. Oluşturulan raw key yalnızca bir kez döner."""
    try:
        body = await request.json()
        name = body.get("name", "New Key")
        budget = float(body.get("budget", 0))

        raw_key = f"sk-orion-{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        row = await db_manager.fetchrow(
            "INSERT INTO router_virtual_keys (name, api_key_hash, budget) "
            "VALUES ($1, $2, $3) "
            "RETURNING id, name, is_active, budget, used_amount, created_at",
            name,
            key_hash,
            budget,
        )
        data = dict(row)
        data["raw_key"] = raw_key  # Önemli: raw key yalnızca bir kez gönderilir!
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/keys/{key_id}", dependencies=[Depends(verify_admin)])
async def update_admin_key(key_id: str, request: Request):
    """Sanal API anahtarını günceller."""
    try:
        body = await request.json()
        existing = await db_manager.fetchrow(
            "SELECT name, budget, is_active FROM router_virtual_keys WHERE id = $1",
            key_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Key not found")

        name = _require_text(body.get("name", existing["name"]), "name")
        budget = float(body.get("budget", existing["budget"]))
        is_active = bool(body.get("is_active", existing["is_active"]))

        row = await db_manager.fetchrow(
            """
            UPDATE router_virtual_keys
            SET name = $2, budget = $3, is_active = $4
            WHERE id = $1
            RETURNING id, name, is_active, budget, used_amount, created_at
            """,
            key_id,
            name,
            budget,
            is_active,
        )
        # Key deactivated or budget changed → invalidate auth cache
        from core.dependencies import invalidate_vkey_cache
        invalidate_vkey_cache()  # Basit: tümü temizle (hash erişimi yok)
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/keys/{key_id}", dependencies=[Depends(verify_admin)])
async def delete_admin_key(key_id: str):
    """Sanal API anahtarını siler."""
    try:
        # Delete and invalidate auth cache for this key
        row = await db_manager.fetchrow(
            "DELETE FROM router_virtual_keys WHERE id = $1 RETURNING api_key_hash",
            key_id,
        )
        if row:
            from core.dependencies import invalidate_vkey_cache
            import hashlib
            invalidate_vkey_cache()  # Tüm cache temizle (hash'i elde etmek güç)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  Logs & Stats
# ---------------------------------------------------------------------------

@router.get("/api/logs", dependencies=[Depends(verify_admin)])
async def get_admin_logs():
    """Son 100 istek kaydını key adıyla birlikte döner."""
    try:
        rows = await db_manager.fetch(
            """
            SELECT l.id, k.name as key_name, l.provider, l.requested_model,
                   l.tokens_used, l.prompt_tokens, l.completion_tokens, l.thoughts_tokens,
                   l.cost, l.success, l.created_at,
                   COALESCE(l.capability, 'chat') as capability
            FROM router_request_logs l
            LEFT JOIN router_virtual_keys k ON l.key_id = k.id
            ORDER BY l.created_at DESC
            LIMIT 100
            """
        )
        return {"logs": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/logs/{log_id}", dependencies=[Depends(verify_admin)])
async def get_admin_log_details(log_id: int):
    """Belirli bir log'un detaylarını (request ve response JSON) döner."""
    try:
        row = await db_manager.fetchrow(
            "SELECT request_json::text, response_json::text, COALESCE(capability, 'chat') as capability FROM router_request_logs WHERE id = $1", log_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Log not found")
        return {
            "request_json": row["request_json"],
            "response_json": row["response_json"],
            "capability": row["capability"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/logs", dependencies=[Depends(verify_admin)])
async def delete_all_logs():
    """Tüm istek loglarını siler ve sanal anahtarların kullanılan bütçe tutarlarını sıfırlar."""
    try:
        pool = await db_manager.get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Delete request logs
                await conn.execute("DELETE FROM router_request_logs")
                # 2. Reset virtual key usage statistics
                await conn.execute("UPDATE router_virtual_keys SET used_amount = 0.0")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats", dependencies=[Depends(verify_admin)])
async def get_admin_stats():
    """Toplam maliyet, token ve anahtar sayısını döner."""
    try:
        total_cost_row = await db_manager.fetchrow(
            """
            SELECT 
                SUM(cost) as total,
                SUM(prompt_cost) as prompt_cost,
                SUM(completion_cost) as completion_cost,
                SUM(thoughts_cost) as thoughts_cost
            FROM router_request_logs
            """
        )
        tokens_row = await db_manager.fetchrow(
            """
            SELECT 
                SUM(tokens_used) as total,
                SUM(prompt_tokens) as prompt,
                SUM(completion_tokens) as completion,
                SUM(thoughts_tokens) as thoughts
            FROM router_request_logs
            """
        )
        total_keys = await db_manager.fetchval(
            "SELECT COUNT(*) FROM router_virtual_keys"
        )
        
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        thoughts_tokens = 0
        if tokens_row:
            total_tokens = tokens_row["total"] or 0
            prompt_tokens = tokens_row["prompt"] or 0
            completion_tokens = tokens_row["completion"] or 0
            thoughts_tokens = tokens_row["thoughts"] or 0

        total_cost = 0.0
        prompt_cost = 0.0
        completion_cost = 0.0
        thoughts_cost = 0.0
        if total_cost_row:
            total_cost = float(total_cost_row["total"] or 0.0)
            prompt_cost = float(total_cost_row["prompt_cost"] or 0.0)
            completion_cost = float(total_cost_row["completion_cost"] or 0.0)
            thoughts_cost = float(total_cost_row["thoughts_cost"] or 0.0)

            # Fallback for legacy logs: approximate based on token proportions
            # Use sum of individual token columns since tokens_used may be NULL in old logs
            tracked_tokens = prompt_tokens + completion_tokens + thoughts_tokens
            if total_cost > 0 and prompt_cost == 0 and completion_cost == 0 and thoughts_cost == 0 and tracked_tokens > 0:
                prompt_cost = total_cost * (prompt_tokens / tracked_tokens)
                completion_cost = total_cost * (completion_tokens / tracked_tokens)
                thoughts_cost = total_cost * (thoughts_tokens / tracked_tokens)

        return {
            "total_cost": total_cost,
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "thoughts_cost": thoughts_cost,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "thoughts_tokens": thoughts_tokens,
            "total_keys": total_keys or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  Provider Keys
# ---------------------------------------------------------------------------

@router.get("/api/provider-keys", dependencies=[Depends(verify_admin)])
async def get_provider_keys():
    """Provider API key'lerini maskeli şekilde döner (yalnızca DB)."""
    try:
        raw_keys = await db_manager.get_config("provider_api_keys") or {}
        if not isinstance(raw_keys, dict):
            raw_keys = {}

        masked_keys = {}
        for provider, key in raw_keys.items():
            if key:
                masked_keys[provider] = key[:4] + "*" * 10 + key[-4:] if len(key) > 8 else "***"
            else:
                masked_keys[provider] = ""
        return {"keys": masked_keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/provider-keys", dependencies=[Depends(verify_admin)])
async def update_provider_keys(request: Request):
    """Provider API key'lerini günceller."""
    try:
        body = await request.json()
        keys_to_update = body.get("keys", {})
        
        current_keys = await db_manager.get_config("provider_api_keys") or {}
        if not isinstance(current_keys, dict):
            current_keys = {}

        for provider, new_key in keys_to_update.items():
            if new_key and not new_key.endswith("***") and "*" not in new_key:
                current_keys[provider] = new_key
            elif new_key == "": # boş gönderilirse sil
                current_keys[provider] = ""
                
        # DB'ye kaydet
        await db_manager.upsert_config("provider_api_keys", json.dumps(current_keys))
        
        # Cache'i güncelle
        request.app.state.provider_keys = current_keys
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  Provider Capabilities
# ---------------------------------------------------------------------------

@router.get("/api/providers", dependencies=[Depends(verify_admin)])
async def get_admin_providers(request: Request):
    """Return providers loaded from code and their capabilities."""
    try:
        return {"providers": request.app.state.dynamic_router.get_capabilities()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/voices", dependencies=[Depends(verify_admin)])
async def get_admin_voices(request: Request):
    """Her TTS sağlayıcısı için desteklenen sesleri döner."""
    try:
        router_instance = request.app.state.dynamic_router
        voices_by_provider = {}
        from fastapi.concurrency import run_in_threadpool
        for provider_name, provider_inst in router_instance.tts_providers.items():
            if hasattr(provider_inst, "get_voices"):
                voices_by_provider[provider_name] = await run_in_threadpool(provider_inst.get_voices)
            else:
                voices_by_provider[provider_name] = []
        return {"voices": voices_by_provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tts-languages", dependencies=[Depends(verify_admin)])
async def get_admin_tts_languages(request: Request):
    """Her TTS sağlayıcısı için desteklenen dilleri döner."""
    try:
        router_instance = request.app.state.dynamic_router
        languages_by_provider = {}
        from fastapi.concurrency import run_in_threadpool
        for provider_name, provider_inst in router_instance.tts_providers.items():
            if hasattr(provider_inst, "get_languages"):
                languages_by_provider[provider_name] = await run_in_threadpool(provider_inst.get_languages)
            else:
                languages_by_provider[provider_name] = []
        return {"languages": languages_by_provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/local-tts-info", dependencies=[Depends(verify_admin)])
async def get_local_tts_info():
    """Yerel TTS servisinin aktif model/motor bilgisini döner."""
    from core.config import TTS_HOST, TTS_PORT
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res_info = await client.get(f"http://{TTS_HOST}:{TTS_PORT}/v1/model_info")
            if res_info.status_code == 200:
                data = res_info.json()
                return {
                    "active": True,
                    "engine": data.get("engine", "omnivoice")
                }
    except Exception as e:
        logger.debug(f"Could not fetch model info from local TTS: {e}")
    return {"active": False, "engine": None}

# ---------------------------------------------------------------------------
#  Provider Key Pool
# ---------------------------------------------------------------------------

@router.get("/api/provider-key-pool", dependencies=[Depends(verify_admin)])
async def list_provider_key_pool():
    from core.security import decrypt
    rows = await db_manager.fetch(
        """
        SELECT id, provider, label, api_key, priority, is_active, last_error, last_error_at, created_at
        FROM router_provider_key_pool
        ORDER BY provider ASC, priority ASC, created_at ASC
        """
    )
    keys = []
    for row in rows:
        item = dict(row)
        item["masked_key"] = _mask_key(decrypt(item.pop("api_key", "")))
        keys.append(item)
    return {"keys": keys}


@router.post("/api/provider-key-pool", dependencies=[Depends(verify_admin)])
async def create_provider_key_pool_item(request: Request):
    from core.security import encrypt
    body = await request.json()
    provider = _require_text(body.get("provider"), "provider").lower()
    label = _require_text(body.get("label"), "label")
    api_key = encrypt(_require_text(body.get("api_key"), "api_key"))
    priority = int(body.get("priority", 100))
    is_active = bool(body.get("is_active", True))

    row = await db_manager.fetchrow(
        """
        INSERT INTO router_provider_key_pool (provider, label, api_key, priority, is_active)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, provider, label, priority, is_active, last_error, last_error_at, created_at
        """,
        provider,
        label,
        api_key,
        priority,
        is_active,
    )
    return dict(row)


@router.put("/api/provider-key-pool/{key_id}", dependencies=[Depends(verify_admin)])
async def update_provider_key_pool_item(key_id: str, request: Request):
    from core.security import encrypt
    body = await request.json()
    existing = await db_manager.fetchrow(
        "SELECT provider, label, api_key, priority, is_active FROM router_provider_key_pool WHERE id = $1",
        key_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Provider key not found")

    provider = _require_text(body.get("provider", existing["provider"]), "provider").lower()
    label = _require_text(body.get("label", existing["label"]), "label")
    new_key = body.get("api_key", None)
    api_key = existing["api_key"] if new_key in (None, "") else encrypt(_require_text(new_key, "api_key"))
    priority = int(body.get("priority", existing["priority"]))
    is_active = bool(body.get("is_active", existing["is_active"]))

    row = await db_manager.fetchrow(
        """
        UPDATE router_provider_key_pool
        SET provider = $2, label = $3, api_key = $4, priority = $5,
            is_active = $6, updated_at = NOW()
        WHERE id = $1
        RETURNING id, provider, label, priority, is_active, last_error, last_error_at, created_at
        """,
        key_id,
        provider,
        label,
        api_key,
        priority,
        is_active,
    )
    return dict(row)


@router.delete("/api/provider-key-pool/{key_id}", dependencies=[Depends(verify_admin)])
async def delete_provider_key_pool_item(key_id: str):
    result = await db_manager.execute("DELETE FROM router_provider_key_pool WHERE id = $1", key_id)
    return {"status": "success", "result": result}


# ---------------------------------------------------------------------------
#  Model Registry
# ---------------------------------------------------------------------------

@router.get("/api/models", dependencies=[Depends(verify_admin)])
async def list_models():
    rows = await db_manager.fetch(
        """
        SELECT m.id, m.name, m.provider, m.capability, m.temperature, m.is_active, m.created_at, m.thinking_level, m.system_prompt,
               m.default_config,
               p.input_price, p.output_price, p.think_price
        FROM router_models m
        LEFT JOIN router_model_pricing p ON m.name = p.model_name
        ORDER BY m.capability ASC, m.provider ASC, m.name ASC
        """
    )
    models = []
    for row in rows:
        item = dict(row)
        item["temperature"] = float(item["temperature"]) if item["temperature"] is not None else None
        item["input_price"] = float(item["input_price"]) if item["input_price"] is not None else 0.0
        item["output_price"] = float(item["output_price"]) if item["output_price"] is not None else 0.0
        item["think_price"] = float(item["think_price"]) if item["think_price"] is not None else 0.0
        item["default_config"] = _parse_default_config(item.get("default_config"))
        models.append(item)
    return {"models": models}


@router.post("/api/models", dependencies=[Depends(verify_admin)])
async def create_model(request: Request):
    body = await request.json()
    name = _require_text(body.get("name"), "name")
    provider = _require_text(body.get("provider"), "provider").lower()
    capability = _require_text(body.get("capability", "chat"), "capability")
    temperature = body.get("temperature", None)
    if capability in ("chat", "tts"):
        temperature = float(temperature) if temperature not in (None, "") else None
    else:
        temperature = None
    is_active = bool(body.get("is_active", True))
    input_price = float(body.get("input_price", 0.0) if body.get("input_price") not in (None, "") else 0.0)
    output_price = float(body.get("output_price", 0.0) if body.get("output_price") not in (None, "") else 0.0)
    think_price = float(body.get("think_price", 0.0) if body.get("think_price") not in (None, "") else 0.0)
    thinking_level = body.get("thinking_level")
    thinking_level = str(thinking_level).strip() if thinking_level not in (None, "") else None
    system_prompt = body.get("system_prompt")
    system_prompt = str(system_prompt).strip() if system_prompt not in (None, "") else None
    default_config = _parse_default_config(body.get("default_config"))
    import json as _json
    default_config_json = _json.dumps(default_config)

    row = await db_manager.fetchrow(
        """
        INSERT INTO router_models (name, provider, capability, temperature, is_active, thinking_level, system_prompt, default_config)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        RETURNING id, name, provider, capability, temperature, is_active, thinking_level, system_prompt, default_config, created_at
        """,
        name,
        provider,
        capability,
        temperature,
        is_active,
        thinking_level,
        system_prompt,
        default_config_json,
    )
    await db_manager.upsert_pricing(name, input_price, output_price, think_price)

    # Refresh pricing cache dynamically
    if hasattr(request.app.state, "pricing_cache"):
        request.app.state.pricing_cache[name] = {
            "input": input_price,
            "output": output_price,
            "think": think_price
        }

    item = dict(row)
    item["temperature"] = float(item["temperature"]) if item["temperature"] is not None else None
    item["input_price"] = input_price
    item["output_price"] = output_price
    item["think_price"] = think_price
    item["default_config"] = _parse_default_config(item.get("default_config"))
    return item


@router.put("/api/models/{model_id}", dependencies=[Depends(verify_admin)])
async def update_model(model_id: str, request: Request):
    body = await request.json()
    existing = await db_manager.fetchrow(
        "SELECT name, provider, capability, temperature, is_active, thinking_level, system_prompt, default_config FROM router_models WHERE id = $1",
        model_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    name = _require_text(body.get("name", existing["name"]), "name")
    provider = _require_text(body.get("provider", existing["provider"]), "provider").lower()
    capability = _require_text(body.get("capability", existing["capability"]), "capability")
    temperature = body.get("temperature", existing["temperature"])
    if capability in ("chat", "tts"):
        temperature = float(temperature) if temperature not in (None, "") else None
    else:
        temperature = None
    is_active = bool(body.get("is_active", existing["is_active"]))
    input_price = float(body.get("input_price", 0.0) if body.get("input_price") not in (None, "") else 0.0)
    output_price = float(body.get("output_price", 0.0) if body.get("output_price") not in (None, "") else 0.0)
    think_price = float(body.get("think_price", 0.0) if body.get("think_price") not in (None, "") else 0.0)
    
    new_thinking = body.get("thinking_level", existing["thinking_level"])
    thinking_level = str(new_thinking).strip() if new_thinking not in (None, "") else None
    new_system_prompt = body.get("system_prompt", existing["system_prompt"])
    system_prompt = str(new_system_prompt).strip() if new_system_prompt not in (None, "") else None
    default_config = _parse_default_config(body.get("default_config", existing["default_config"]))
    import json as _json
    default_config_json = _json.dumps(default_config)

    row = await db_manager.fetchrow(
        """
        UPDATE router_models
        SET name = $2, provider = $3, capability = $4, temperature = $5,
            is_active = $6, thinking_level = $7, system_prompt = $8, default_config = $9::jsonb, updated_at = NOW()
        WHERE id = $1
        RETURNING id, name, provider, capability, temperature, is_active, thinking_level, system_prompt, default_config, created_at
        """,
        model_id,
        name,
        provider,
        capability,
        temperature,
        is_active,
        thinking_level,
        system_prompt,
        default_config_json,
    )
    await db_manager.upsert_pricing(name, input_price, output_price, think_price)

    # Refresh pricing cache dynamically
    if hasattr(request.app.state, "pricing_cache"):
        request.app.state.pricing_cache[name] = {
            "input": input_price,
            "output": output_price,
            "think": think_price
        }

    item = dict(row)
    item["temperature"] = float(item["temperature"]) if item["temperature"] is not None else None
    item["input_price"] = input_price
    item["output_price"] = output_price
    item["think_price"] = think_price
    item["default_config"] = _parse_default_config(item.get("default_config"))
    return item


@router.delete("/api/models/{model_id}", dependencies=[Depends(verify_admin)])
async def delete_model(model_id: str):
    result = await db_manager.execute("DELETE FROM router_models WHERE id = $1", model_id)
    return {"status": "success", "result": result}


# ---------------------------------------------------------------------------
#  Model Groups
# ---------------------------------------------------------------------------

@router.get("/api/model-groups", dependencies=[Depends(verify_admin)])
async def list_model_groups():
    groups = [dict(r) for r in await db_manager.fetch(
        """
        SELECT id, name, description, capability, is_active, created_at
        FROM router_model_groups
        ORDER BY capability ASC, name ASC
        """
    )]
    for group in groups:
        rows = await db_manager.fetch(
            """
            SELECT i.id, i.model_id, i.priority, i.thinking_level, i.system_prompt, i.temperature, m.name, m.provider, m.capability
            FROM router_model_group_items i
            JOIN router_models m ON m.id = i.model_id
            WHERE i.group_id = $1
            ORDER BY i.priority ASC, i.created_at ASC
            """,
            group["id"],
        )
        items = []
        for r in rows:
            d = dict(r)
            d["temperature"] = float(d["temperature"]) if d.get("temperature") is not None else None
            items.append(d)
        group["items"] = items
    return {"groups": groups}


@router.post("/api/model-groups", dependencies=[Depends(verify_admin)])
async def create_model_group(request: Request):
    body = await request.json()
    name = _require_text(body.get("name"), "name")
    description = (body.get("description") or "").strip()
    capability = _require_text(body.get("capability", "chat"), "capability")
    is_active = bool(body.get("is_active", True))

    row = await db_manager.fetchrow(
        """
        INSERT INTO router_model_groups (name, description, capability, is_active)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, description, capability, is_active, created_at
        """,
        name,
        description,
        capability,
        is_active,
    )
    data = dict(row)
    data["items"] = []
    return data


@router.put("/api/model-groups/{group_id}", dependencies=[Depends(verify_admin)])
async def update_model_group(group_id: str, request: Request):
    body = await request.json()
    existing = await db_manager.fetchrow(
        "SELECT name, description, capability, is_active FROM router_model_groups WHERE id = $1",
        group_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Group not found")

    name = _require_text(body.get("name", existing["name"]), "name")
    description = (body.get("description", existing["description"]) or "").strip()
    capability = _require_text(body.get("capability", existing["capability"]), "capability")
    is_active = bool(body.get("is_active", existing["is_active"]))

    row = await db_manager.fetchrow(
        """
        UPDATE router_model_groups
        SET name = $2, description = $3, capability = $4, is_active = $5, updated_at = NOW()
        WHERE id = $1
        RETURNING id, name, description, capability, is_active, created_at
        """,
        group_id,
        name,
        description,
        capability,
        is_active,
    )
    return dict(row)


@router.delete("/api/model-groups/{group_id}", dependencies=[Depends(verify_admin)])
async def delete_model_group(group_id: str):
    result = await db_manager.execute("DELETE FROM router_model_groups WHERE id = $1", group_id)
    return {"status": "success", "result": result}


@router.post("/api/model-groups/{group_id}/items", dependencies=[Depends(verify_admin)])
async def add_model_group_item(group_id: str, request: Request):
    body = await request.json()
    model_id = _require_text(body.get("model_id"), "model_id")
    priority = int(body.get("priority", 100))
    thinking_level = body.get("thinking_level")
    thinking_level = str(thinking_level).strip() if thinking_level not in (None, "") else None
    system_prompt = body.get("system_prompt")
    system_prompt = str(system_prompt).strip() if system_prompt not in (None, "") else None
    temperature = body.get("temperature")
    temperature = float(temperature) if temperature not in (None, "") else None

    group = await db_manager.fetchrow("SELECT capability FROM router_model_groups WHERE id = $1", group_id)
    model = await db_manager.fetchrow("SELECT capability FROM router_models WHERE id = $1", model_id)
    if not group or not model:
        raise HTTPException(status_code=404, detail="Group or model not found")
    if group["capability"] != model["capability"]:
        raise HTTPException(status_code=400, detail="Model capability must match group capability")

    row = await db_manager.fetchrow(
        """
        INSERT INTO router_model_group_items (group_id, model_id, priority, thinking_level, system_prompt, temperature)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, group_id, model_id, priority, thinking_level, system_prompt, temperature, created_at
        """,
        group_id,
        model_id,
        priority,
        thinking_level,
        system_prompt,
        temperature,
    )
    item = dict(row)
    item["temperature"] = float(item["temperature"]) if item.get("temperature") is not None else None
    return item


@router.put("/api/model-groups/{group_id}/items/{item_id}", dependencies=[Depends(verify_admin)])
async def update_model_group_item(group_id: str, item_id: str, request: Request):
    body = await request.json()
    priority = int(body.get("priority", 100))
    
    existing = await db_manager.fetchrow("SELECT thinking_level, system_prompt, temperature FROM router_model_group_items WHERE id = $1 AND group_id = $2", item_id, group_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Group item not found")

    new_thinking = body.get("thinking_level", existing["thinking_level"])
    thinking_level = str(new_thinking).strip() if new_thinking not in (None, "") else None
    new_system_prompt = body.get("system_prompt", existing["system_prompt"])
    system_prompt = str(new_system_prompt).strip() if new_system_prompt not in (None, "") else None
    new_temperature = body.get("temperature", existing["temperature"])
    temperature = float(new_temperature) if new_temperature not in (None, "") else None

    row = await db_manager.fetchrow(
        """
        UPDATE router_model_group_items
        SET priority = $3, thinking_level = $4, system_prompt = $5, temperature = $6
        WHERE id = $1 AND group_id = $2
        RETURNING id, group_id, model_id, priority, thinking_level, system_prompt, temperature, created_at
        """,
        item_id,
        group_id,
        priority,
        thinking_level,
        system_prompt,
        temperature,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Group item not found")
    item = dict(row)
    item["temperature"] = float(item["temperature"]) if item.get("temperature") is not None else None
    return item


@router.delete("/api/model-groups/{group_id}/items/{item_id}", dependencies=[Depends(verify_admin)])
async def delete_model_group_item(group_id: str, item_id: str):
    result = await db_manager.execute(
        "DELETE FROM router_model_group_items WHERE id = $1 AND group_id = $2",
        item_id,
        group_id,
    )
    return {"status": "success", "result": result}


# ---------------------------------------------------------------------------
#  UI (Fallback for SPA Routing)
# ---------------------------------------------------------------------------

@router.get("", include_in_schema=False)
@router.head("", include_in_schema=False)
@router.get("/", include_in_schema=False)
@router.head("/", include_in_schema=False)
@router.get("/{path:path}", include_in_schema=False)
@router.head("/{path:path}", include_in_schema=False)
async def get_admin_ui(path: str = ""):
    """SPA Client-Side Router for Next.js - returns HTML and RSC payloads."""
    # Exclude API routes
    if path.startswith("api/") or path == "api":
        raise HTTPException(status_code=404, detail="Not Found")
        
    import os
    from fastapi.responses import RedirectResponse
    
    # Dev mode: Next.js dev server'a (3001) otomatik yönlendir
    if os.environ.get("UVICORN_RELOAD") == "1":
        # path boşsa direkt 3001/dashboard, doluysa 3001/dashboard/path
        target_url = f"http://127.0.0.1:3001/dashboard/{path}" if path else "http://127.0.0.1:3001/dashboard"
        return RedirectResponse(url=target_url)

    from core.config import DASHBOARD_OUT_DIR
    out_dir = DASHBOARD_OUT_DIR
    
    # 1. Clean up the path (remove leading slashes if any)
    safe_path = path.lstrip("/")
    target_path = os.path.join(out_dir, safe_path) if safe_path else out_dir
    
    # 2. Check if the exact requested file exists (e.g. favicon.ico, settings.txt, __next._index.txt)
    if safe_path and os.path.isfile(target_path):
        return FileResponse(target_path)
        
    # 3. Check if an HTML file exists for the requested path (e.g. /keys -> keys.html)
    if safe_path and not safe_path.endswith(".html") and not safe_path.endswith(".txt"):
        html_path = f"{target_path}.html"
        if os.path.isfile(html_path):
            return FileResponse(html_path, media_type="text/html")
            
        # 4. Check if there's an index.html inside a directory (e.g. /keys/ -> keys/index.html)
        index_in_dir = os.path.join(target_path, "index.html")
        if os.path.isdir(target_path) and os.path.isfile(index_in_dir):
            return FileResponse(index_in_dir, media_type="text/html")

    # 5. Final Fallback to root index.html (SPA fallback)
    root_index = os.path.join(out_dir, "index.html")
    if os.path.exists(root_index):
        return FileResponse(root_index, media_type="text/html")
        
    # Fallback to old dashboard index.html if out doesn't exist
    old_index = os.path.join(_DASHBOARD_DIR, "index.html")
    if os.path.exists(old_index):
        return FileResponse(old_index, media_type="text/html")
        
    return Response(
        content=(
            "Admin UI not found. Please build the Next.js project. "
            "Dev mode: use http://127.0.0.1:3001/dashboard for the UI."
        ),
        status_code=404,
    )

