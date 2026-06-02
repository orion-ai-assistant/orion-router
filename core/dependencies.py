"""
core/dependencies.py
--------------------
FastAPI Depends fonksiyonları. Route'larda doğrudan inject edilir.

Tek merkezi auth gate: authenticate_request()
  - Admin secret → system modu
  - sk-orion-... → virtual key doğrulaması
  - Diğer → 401 Unauthorized
"""
import hashlib
import logging

from fastapi import Request, HTTPException, Header
from database import db_manager
from core import config

logger = logging.getLogger("service-router.deps")


async def authenticate_request(request: Request) -> dict:
    """Tek merkezi auth gate. Her istek buradan geçer.

    Authorization: Bearer <token> başlığından token'ı alır ve şu kontrolleri yapar:
      1. Token == ADMIN_SECRET → {"source": "system", "key_id": None}
      2. Token sk-orion-... ile başlıyorsa → DB'den virtual key doğrula
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
        try:
            row = await db_manager.fetchrow(
                "SELECT id, name, is_active, budget, used_amount FROM router_virtual_keys WHERE api_key_hash = $1",
                key_hash,
            )
        except Exception as e:
            logger.error(f"DB error during key verification: {e}")
            raise HTTPException(status_code=500, detail="Internal error during authentication")

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



    # --- 3. Tanınmayan token: pass-through olarak işaretle ---
    # Playground'dan direkt provider key gönderiliyorsa bunu upstream'e iletmek için işaretle
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
