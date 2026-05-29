"""
core/lifespan.py
----------------
FastAPI uygulama yaşam döngüsü (startup / shutdown).
Veritabanını başlatır, JSON seed dosyalarını DB'ye senkronize eder
ve uygulama state'ini (pricing cache, model info cache, dynamic router) hazırlar.
"""
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import db_manager
from dynamic_router import DynamicLLMRouter
from core.config import MODEL_PRICING_PATH, MODEL_INFO_PATH, ROUTER_PORT

logger = logging.getLogger("service-router")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    #  STARTUP                                                             #
    # ------------------------------------------------------------------ #
    logger.info("Starting up Orion Custom Service Router")
    print("\n" + "="*60)
    print("🚀 Orion Router başarıyla başlatıldı!")
    print(f"👉 Yönetim Paneli: http://localhost:{ROUTER_PORT}/dashboard")
    print("="*60 + "\n")
    await db_manager.init_db()

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
