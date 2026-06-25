"""
core/dependencies.py
--------------------
FastAPI Depends fonksiyonları. Route'larda doğrudan inject edilir.

Tek merkezi auth gate: authenticate_request()
  - Admin secret → system modu
  - sk-orion-... → virtual key doğrulaması (kısa süreli in-memory cache ile)
  - Diğer → 401 Unauthorized
"""
import hashlib
import logging
import time

from fastapi import Request, HTTPException, Header
from database import db_manager
from core import config

logger = logging.getLogger("service-router.deps")

# ---------------------------------------------------------------------------
#  Virtual Key In-Memory Cache
#  Her istek için DB sorgusu yapmak yerine kısa süreli (TTL saniye) cache.
#  key_hash → {"id": ..., "name": ..., "is_active": ..., "budget": ...,
#               "used_amount": ..., "_ts": monotonic_timestamp}
# ---------------------------------------------------------------------------
_VKEY_CACHE_TTL = float('inf')  # Sınırsız (Dashboard'dan güncellenene kadar RAM'de kalır)
_vkey_cache: dict = {}

def invalidate_vkey_cache(key_hash: str | None = None) -> None:
    """Virtual key cache'ini temizle. key_hash=None ise tüm cache'i temizler."""
    if key_hash is None:
        _vkey_cache.clear()
    else:
        _vkey_cache.pop(key_hash, None)

async def prewarm_vkey_cache() -> None:
    """Sunucu başlarken tüm aktif sanal anahtarları DB'den çekip RAM'e yükler."""
    from database import db_manager
    import time
    try:
        rows = await db_manager.fetch(
            "SELECT id, name, is_active, budget, used_amount, api_key_hash FROM router_virtual_keys WHERE is_active = true"
        )
        for r in rows:
            r_dict = dict(r)
            khash = r_dict.pop("api_key_hash")
            _vkey_cache[khash] = r_dict | {"_ts": time.monotonic()}
        import logging
        logging.getLogger("service-router.auth").info(f"Pre-warmed {len(rows)} virtual keys into RAM.")
    except Exception as e:
        import logging
        logging.getLogger("service-router.auth").error(f"Failed to pre-warm virtual keys: {e}")


async def authenticate_request(request: Request) -> dict:
    """Tek merkezi auth gate. Her istek buradan geçer.

    Authorization: Bearer <token> başlığından token'ı alır ve şu kontrolleri yapar:
      1. Token == ADMIN_SECRET → {"source": "system", "key_id": None}
      2. Token sk-orion-... ile başlıyorsa → DB'den virtual key doğrula (TTL cache'li)
      3. Hiçbiri değilse → 401

    Returns:
        {"source": "system", "key_id": None}                          → Admin/System
        {"source": "virtual_key", "key_id": <id>, "name": <name>}    → Virtual key user
    Raises:
        HTTPException 401: Key yok veya tanınmıyor
        HTTPException 403: Key inactive
        HTTPException 402: Bütçe aşıldıysa
    """
    # --- Token'ı çıkar ---
    token = None

    # Önce Authorization header'ına bak
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    # Alternatif olarak x-orion-api-key header'ına bak
    if not token:
        token = request.headers.get("x-orion-api-key")

    if not token:
        raise HTTPException(status_code=401, detail="API key is required. Send via Authorization: Bearer <key>")

    # --- 1. Virtual Key kontrolü ---
    if token.startswith("sk-orion-"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()

        # Cache kontrolü
        row = None
        cached = _vkey_cache.get(key_hash)
        if cached is not None:
            if time.monotonic() - cached["_ts"] < _VKEY_CACHE_TTL:
                row = cached
                logger.debug("Virtual key served from cache (hash prefix: %s...)", key_hash[:8])
            else:
                # TTL doldu, cache'den temizle ve yeniden sorgula
                del _vkey_cache[key_hash]

        if row is None:
            try:
                row = await db_manager.fetchrow(
                    "SELECT id, name, is_active, budget, used_amount FROM router_virtual_keys WHERE api_key_hash = $1",
                    key_hash,
                )
            except Exception as e:
                logger.error(f"DB error during key verification: {e}")
                raise HTTPException(status_code=500, detail="Internal error during authentication")

            if row:
                _vkey_cache[key_hash] = dict(row) | {"_ts": time.monotonic()}

        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="API key is inactive")
        if row["budget"] > 0 and row["used_amount"] >= row["budget"]:
            raise HTTPException(status_code=402, detail="API key budget exceeded")

        return {"source": "virtual_key", "key_id": row["id"], "name": row["name"]}

    # --- 2. Admin Secret kontrolü ---
    hashed_db = await db_manager.get_config("admin_secret_hash")
    if hashed_db:
        from core.security import verify_secret
        if verify_secret(token, hashed_db):
            return {"source": "system", "key_id": None}
    else:
        if token == config.ADMIN_SECRET:
            return {"source": "system", "key_id": None}

    # --- 3. Tanınmayan token ---
    raise HTTPException(status_code=401, detail="Invalid API key")


import urllib.parse

async def verify_admin(x_admin_key: str = Header(default=None)):
    """Dependency: Admin yetkisi kontrolü."""
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="Unauthorized admin access")
    
    x_admin_key = urllib.parse.unquote(x_admin_key)
    
    hashed_db = await db_manager.get_config("admin_secret_hash")
    if hashed_db:
        from core.security import verify_secret
        if not verify_secret(x_admin_key, hashed_db):
            raise HTTPException(status_code=401, detail="Unauthorized admin access")
    else:
        if x_admin_key != config.ADMIN_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized admin access")
    return True
