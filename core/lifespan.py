"""
core/lifespan.py
----------------
FastAPI uygulama yaşam döngüsü (startup / shutdown).
Veritabanını başlatır, JSON seed dosyalarını DB'ye senkronize eder
ve uygulama state'ini (pricing cache, model info cache, dynamic router) hazırlar.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import db_manager
from dynamic_router import DynamicLLMRouter
from core.config import MODEL_PRICING_PATH, MODEL_INFO_PATH, ROUTER_PORT

logger = logging.getLogger("service-router")


def get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    #  STARTUP                                                             #
    # ------------------------------------------------------------------ #
    logger.info("Starting up Orion Custom Service Router")

    import os
    env_mode = "Dev" if os.environ.get("UVICORN_RELOAD") == "1" else "Prod"
    local_ip = get_local_ip()
    
    print("\n" + "═" * 55)
    print(f"║{'Orion Router — Bütün Servisler Aktif':^53}║")
    print("╠" + "═" * 53 + "╣")
    
    if env_mode == "Dev":
        print(f"║  Dashboard       http://localhost:3001")
        print(f"║  Yerel Ağ (Tel)  http://{local_ip}:3001")
    else:
        print(f"║  Dashboard       http://localhost:{ROUTER_PORT}")
        print(f"║  Yerel Ağ (Tel)  http://{local_ip}:{ROUTER_PORT}")
        
    print("╠" + "═" * 53 + "╣")
    print(f"║{'Durdurmak icin CTRL+C':^53}║")
    print("╚" + "═" * 55 + "╝\n")

    # PostgreSQL tam hazır olmadan önce FastAPI başlayabilir; retry ile bekle
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            await db_manager.init_db()
            break
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"DB başlatılamadı ({max_retries} deneme sonrası): {e}")
                raise
            wait = min(attempt * 0.8, 5)
            logger.warning(f"DB bağlantısı başarısız (deneme {attempt}/{max_retries}), {wait:.1f}s bekleniyor... ({e})")
            await asyncio.sleep(wait)

    # --- Fiyatlandırmayı seed et ---
    if MODEL_PRICING_PATH.exists():
        try:
            with open(MODEL_PRICING_PATH, "r", encoding="utf-8") as f:
                pricing_data = json.load(f)
            # JSON'da olan fiyatları DB'ye kopyalayıp güncelliyoruz (ON CONFLICT DO UPDATE).
            # DB'de olan ama JSON'da olmayan diğer fiyat kayıtları silinmeden korunur.
            for m_name, p_data in pricing_data.items():
                await db_manager.upsert_pricing(
                    m_name,
                    p_data.get("input", 0),
                    p_data.get("output", 0),
                    p_data.get("think", 0),
                )
            logger.info("Synced model pricing from JSON to DB (existing keys updated, others preserved).")
        except Exception as e:
            logger.error(f"Error seeding pricing: {e}")

    # --- Model bilgisini seed et ---
    if MODEL_INFO_PATH.exists():
        try:
            with open(MODEL_INFO_PATH, "r", encoding="utf-8") as f:
                info_data = json.load(f)

            # JSON dosyasındaki verilerin tam yetkili olmasını (DB'yi tamamen ezmesini) istiyoruz.
            # Böylece JSON'da yapılan tüm silme/güncelleme/ekleme işlemleri anında aktif olur.
            await db_manager.upsert_config("model_info", json.dumps(info_data))
            logger.info("Synced model_info from JSON to DB (JSON is source of truth).")
        except Exception as e:
            logger.error(f"Error seeding model_info: {e}")

    # --- Cache'i yükle ---
    app.state.pricing_cache = await db_manager.get_all_pricing()
    app.state.model_info_cache = await db_manager.get_config("model_info") or {"families": []}

    # Provider API key'lerini DB'den yükle (runtime'da güncellenebilir)
    raw_keys = await db_manager.get_config("provider_api_keys")
    app.state.provider_keys = raw_keys if isinstance(raw_keys, dict) else {}

    app.state.dynamic_router = DynamicLLMRouter(app.state)

    yield

    # ------------------------------------------------------------------ #
    #  SHUTDOWN                                                            #
    # ------------------------------------------------------------------ #
    logger.info("Shutting down Orion Custom Service Router")
    await db_manager.close_db()
