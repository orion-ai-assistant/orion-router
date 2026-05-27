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

router = APIRouter(prefix="/admin", tags=["Admin"])

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


# ---------------------------------------------------------------------------
#  UI
# ---------------------------------------------------------------------------

@router.get("")
@router.get("/")
async def get_admin_ui():
    """Admin arayüzünün ana sayfasını (index.html) döner."""
    admin_ui_path = os.path.join(_DASHBOARD_DIR, "index.html")
    if not os.path.exists(admin_ui_path):
        return Response(
            content="Admin UI not found. Please create dashboard/index.html",
            status_code=404,
        )
    return FileResponse(admin_ui_path, media_type="text/html")


@router.get("/{page}")
async def get_admin_page(page: str):
    """Admin arayüzündeki diğer sayfaları (örn. keys, models) döner."""
    page_name = page.replace(".html", "")
    valid_pages = {"keys", "logs", "key-pool", "models", "groups", "playground", "model-info", "settings"}
    
    if page_name in valid_pages:
        page_path = os.path.join(_DASHBOARD_DIR, f"{page_name}.html")
        if os.path.exists(page_path):
            return FileResponse(page_path, media_type="text/html")
            
    # Eğer geçerli bir sayfa değilse ana sayfaya yönlendir ya da index.html döner
    index_path = os.path.join(_DASHBOARD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return Response(content="Admin UI not found.", status_code=404)


@router.get("/api/settings/is-default-password")
async def check_is_default_password():
    from core import config
    return {"is_default": config.ADMIN_SECRET == "orion-admin"}


@router.put("/api/settings/admin-secret", dependencies=[Depends(verify_admin)])
async def update_admin_secret(request: Request):
    try:
        body = await request.json()
        new_secret = (body.get("admin_secret") or "").strip()
        if not new_secret:
            raise HTTPException(status_code=400, detail="Admin secret cannot be empty")
        
        # Update in memory
        from core import config
        config.ADMIN_SECRET = new_secret
        
        # Update in .env file
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        lines = []
        secret_found = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        
        for i, line in enumerate(lines):
            if line.strip().startswith("ADMIN_SECRET="):
                lines[i] = f'ADMIN_SECRET="{new_secret}"\n'
                secret_found = True
                break
        
        if not secret_found:
            lines.append(f'\nADMIN_SECRET="{new_secret}"\n')
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
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
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/keys/{key_id}", dependencies=[Depends(verify_admin)])
async def delete_admin_key(key_id: str):
    """Sanal API anahtarını siler."""
    try:
        result = await db_manager.execute(
            "DELETE FROM router_virtual_keys WHERE id = $1",
            key_id,
        )
        return {"status": "success", "result": result}
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


@router.get("/api/stats", dependencies=[Depends(verify_admin)])
async def get_admin_stats():
    """Toplam maliyet, token ve anahtar sayısını döner."""
    try:
        total_cost_row = await db_manager.fetchrow(
            "SELECT SUM(cost) as total FROM router_request_logs"
        )
        total_tokens_row = await db_manager.fetchrow(
            "SELECT SUM(tokens_used) as total FROM router_request_logs"
        )
        total_keys = await db_manager.fetchval(
            "SELECT COUNT(*) FROM router_virtual_keys"
        )
        return {
            "total_cost": total_cost_row["total"] or 0,
            "total_tokens": total_tokens_row["total"] or 0,
            "total_keys": total_keys or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  Provider Keys
# ---------------------------------------------------------------------------

@router.get("/api/provider-keys", dependencies=[Depends(verify_admin)])
async def get_provider_keys():
    """Provider API key'lerini maskeli şekilde döner."""
    try:
        raw_keys = await db_manager.get_config("provider_api_keys") or {}
        
        # Dinamik olarak config içindeki *_API_KEY değişkenlerini bul ve ekle
        from core import config
        for attr in dir(config):
            if attr.endswith("_API_KEY"):
                provider = attr.replace("_API_KEY", "").lower()
                env_val = getattr(config, attr)
                # Eğer veritabanında bu sağlayıcının key'i yoksa ve env'de varsa onu kullan
                if not raw_keys.get(provider) and env_val:
                    raw_keys[provider] = env_val
                # Eğer sağlayıcı veritabanında hiç yoksa (env boş bile olsa) UI'da görünmesi için ekle
                elif provider not in raw_keys:
                    raw_keys[provider] = env_val or ""

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
        
        # Mevcut keyleri al
        current_keys = await db_manager.get_config("provider_api_keys") or {}
        
        # Mevcut durumu dinamik olarak env ile birleştir (maskeyi doğru çözmek için gerekli)
        from core import config
        for attr in dir(config):
            if attr.endswith("_API_KEY"):
                provider = attr.replace("_API_KEY", "").lower()
                env_val = getattr(config, attr)
                if not current_keys.get(provider) and env_val:
                    current_keys[provider] = env_val
        
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
        for provider_name, provider_inst in router_instance.tts_providers.items():
            if hasattr(provider_inst, "get_voices"):
                voices_by_provider[provider_name] = provider_inst.get_voices()
            else:
                voices_by_provider[provider_name] = []
        return {"voices": voices_by_provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  Provider Key Pool
# ---------------------------------------------------------------------------

@router.get("/api/provider-key-pool", dependencies=[Depends(verify_admin)])
async def list_provider_key_pool():
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
        item["masked_key"] = _mask_key(item.pop("api_key", ""))
        keys.append(item)
    return {"keys": keys}


@router.post("/api/provider-key-pool", dependencies=[Depends(verify_admin)])
async def create_provider_key_pool_item(request: Request):
    body = await request.json()
    provider = _require_text(body.get("provider"), "provider").lower()
    label = _require_text(body.get("label"), "label")
    api_key = _require_text(body.get("api_key"), "api_key")
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
    api_key = existing["api_key"] if new_key in (None, "") else _require_text(new_key, "api_key")
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
        SELECT id, name, provider, capability, temperature, is_active, created_at
        FROM router_models
        ORDER BY capability ASC, provider ASC, name ASC
        """
    )
    models = []
    for row in rows:
        item = dict(row)
        item["temperature"] = float(item["temperature"]) if item["temperature"] is not None else None
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

    row = await db_manager.fetchrow(
        """
        INSERT INTO router_models (name, provider, capability, temperature, is_active)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, name, provider, capability, temperature, is_active, created_at
        """,
        name,
        provider,
        capability,
        temperature,
        is_active,
    )
    item = dict(row)
    item["temperature"] = float(item["temperature"]) if item["temperature"] is not None else None
    return item


@router.put("/api/models/{model_id}", dependencies=[Depends(verify_admin)])
async def update_model(model_id: str, request: Request):
    body = await request.json()
    existing = await db_manager.fetchrow(
        "SELECT name, provider, capability, temperature, is_active FROM router_models WHERE id = $1",
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

    row = await db_manager.fetchrow(
        """
        UPDATE router_models
        SET name = $2, provider = $3, capability = $4, temperature = $5,
            is_active = $6, updated_at = NOW()
        WHERE id = $1
        RETURNING id, name, provider, capability, temperature, is_active, created_at
        """,
        model_id,
        name,
        provider,
        capability,
        temperature,
        is_active,
    )
    item = dict(row)
    item["temperature"] = float(item["temperature"]) if item["temperature"] is not None else None
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
            SELECT i.id, i.model_id, i.priority, m.name, m.provider, m.capability
            FROM router_model_group_items i
            JOIN router_models m ON m.id = i.model_id
            WHERE i.group_id = $1
            ORDER BY i.priority ASC, i.created_at ASC
            """,
            group["id"],
        )
        group["items"] = [dict(r) for r in rows]
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

    group = await db_manager.fetchrow("SELECT capability FROM router_model_groups WHERE id = $1", group_id)
    model = await db_manager.fetchrow("SELECT capability FROM router_models WHERE id = $1", model_id)
    if not group or not model:
        raise HTTPException(status_code=404, detail="Group or model not found")
    if group["capability"] != model["capability"]:
        raise HTTPException(status_code=400, detail="Model capability must match group capability")

    row = await db_manager.fetchrow(
        """
        INSERT INTO router_model_group_items (group_id, model_id, priority)
        VALUES ($1, $2, $3)
        RETURNING id, group_id, model_id, priority, created_at
        """,
        group_id,
        model_id,
        priority,
    )
    return dict(row)


@router.put("/api/model-groups/{group_id}/items/{item_id}", dependencies=[Depends(verify_admin)])
async def update_model_group_item(group_id: str, item_id: str, request: Request):
    body = await request.json()
    priority = int(body.get("priority", 100))
    row = await db_manager.fetchrow(
        """
        UPDATE router_model_group_items
        SET priority = $3
        WHERE id = $1 AND group_id = $2
        RETURNING id, group_id, model_id, priority, created_at
        """,
        item_id,
        group_id,
        priority,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Group item not found")
    return dict(row)


@router.delete("/api/model-groups/{group_id}/items/{item_id}", dependencies=[Depends(verify_admin)])
async def delete_model_group_item(group_id: str, item_id: str):
    result = await db_manager.execute(
        "DELETE FROM router_model_group_items WHERE id = $1 AND group_id = $2",
        item_id,
        group_id,
    )
    return {"status": "success", "result": result}
