"""
core/lifespan.py
----------------
FastAPI uygulama yaşam döngüsü (startup / shutdown).
Veritabanını başlatır, JSON seed dosyalarını DB'ye senkronize eder
ve uygulama state'ini (pricing cache, model info cache, dynamic router) hazırlar.
"""
import asyncio
import logging
import os
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from database import db_manager
from dynamic_router import DynamicLLMRouter
from core.config import ROUTER_PORT
from core.model_catalog import load_model_catalog, unit_pricing
from core.http_client import close_http_clients
from providers.gemini.client import close_gemini_clients
from core.banner import print_active_services_banner

logger = logging.getLogger("service-router")


def _restart_postgres() -> None:
    # API workers must never stop/restart a shared DB while other work is active.
    raise RuntimeError('Database unavailable; recover through the verified native supervisor')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    #  STARTUP                                                             #
    # ------------------------------------------------------------------ #
    logger.info("Starting up Orion Custom Service Router")
    from core.launch_timing import process_age, report, timed
    report('backend.process', process_age())
    from core.windows_asyncio import install_reset_cleanup
    install_reset_cleanup()
    from core.tts_archive import check_runtime

    async def check_encoder():
        # Diagnostics only (logged, and reported by the TTS archive status); archiving never waits for it, so
        # it runs beside the start instead of before /health (ffmpeg and ffprobe took ~2 s on Windows).
        with timed('backend.ffmpeg'):
            try:
                logger.info("TTS archive encoder: %s", await asyncio.to_thread(check_runtime))
            except Exception as exc:
                logger.error("TTS audio archiving unavailable: %s", exc)

    encoder_task = asyncio.create_task(check_encoder())
    from core import config
    from core.mdns import router_id
    from core.tls_identity import load_identity
    app.state.tls_identity = load_identity(config.TLS_DIRECTORY, router_id(config.MDNS_ID_FILE))
    logger.info("Router TLS identity id=%s SPKI SHA-256=%s", app.state.tls_identity.id, app.state.tls_identity.fp)
    try:
        from core.local_installation import refresh_managed_installation
        refresh_managed_installation(config._ROOT, app.state.tls_identity, config.MDNS_ID_FILE, config.TLS_PORT)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning('Local Router registration unavailable (%s); TLS identity retained', type(exc).__name__)

    # PostgreSQL tam hazır olmadan önce FastAPI başlayabilir; retry ile bekle
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            await db_manager.init_db()
            break
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"DB bağlantısı {max_retries}. denemede de başarısız oldu. Program durduruluyor. Hata: {e}")
                raise
            
            logger.warning(
                f"DB bağlantısı başarısız (deneme {attempt}/{max_retries}). "
                f"Veritabanı yeniden başlatılıyor... Hata: {e}"
            )
            try:
                _restart_postgres()
            except Exception as restart_err:
                logger.error(f"PostgreSQL otomatik yeniden başlatma sırasında hata oluştu: {restart_err}")

    # --- Fiyatlandırmayı seed et ---
    try:
        for model in load_model_catalog()["models"]:
            pricing = unit_pricing(model)
            if pricing is None:
                continue
            await db_manager.upsert_pricing(
                model["name"],
                pricing.get("input"),
                pricing.get("output"),
                pricing.get("think"),
            )
        logger.info("Synced model pricing from models.json to DB.")
    except Exception as exc:
        logger.error("Error seeding pricing: %s", exc)


    # --- Cache'i yükle ---
    from core.dependencies import prewarm_vkey_cache
    await prewarm_vkey_cache()
    
    app.state.pricing_cache = await db_manager.get_all_pricing()

    # Provider API key'lerini DB'den yükle (runtime'da güncellenebilir)
    raw_keys = await db_manager.get_config("provider_api_keys")
    app.state.provider_keys = raw_keys if isinstance(raw_keys, dict) else {}

    app.state.dynamic_router = DynamicLLMRouter(app.state)

    # Gemini ve diğer TTS sağlayıcıların seslerini arka planda 1 kere çekip hafızaya al
    async def _warmup_provider_voices():
        try:
            gemini_provider = app.state.dynamic_router.tts_providers.get("gemini")
            if gemini_provider and hasattr(gemini_provider, "fetch_remote_voices"):
                from core.security import decrypt
                row = await db_manager.fetchrow(
                    "SELECT api_key FROM router_provider_key_pool WHERE provider='gemini' AND is_active=true ORDER BY priority ASC LIMIT 1"
                )
                key = None
                if row and row.get("api_key"):
                    try:
                        key = decrypt(row["api_key"])
                    except Exception:
                        key = row["api_key"]
                if not key:
                    raw_keys = await db_manager.get_config("provider_api_keys") or {}
                    key = raw_keys.get("gemini")
                if key:
                    await gemini_provider.fetch_remote_voices(api_key=key)
        except Exception as exc:
            logger.debug("Background voices warmup skipped: %s", exc)

    # A quarantined update candidate may be admitted in place, so optional
    # startup work waits for admission instead of checking it only once.
    from core.update_gate import admitted, wait_for_admission
    warmup_task = asyncio.create_task(admitted(_warmup_provider_voices()))

    if os.getenv("ORION_NO_BANNER") != "1":
        from core.console import enable_ansi
        enable_ansi()

        async def _show_banner_after_startup():
            # Uvicorn'un 'Application startup complete.' logunu basması için
            # çok kısa (50ms), bloklamayan bir arka plan beklemesi yaparız.
            await asyncio.sleep(0.05)
            print_active_services_banner(str(config.TLS_PORT))

        asyncio.create_task(_show_banner_after_startup())

    from core.mdns import Advertiser
    from core.tls_server import LocalHTTPListener
    local_http_listener = LocalHTTPListener(app)
    await local_http_listener.start()
    app.state.local_http_listener = local_http_listener
    advertiser = Advertiser()
    app.state.mdns_advertiser = advertiser

    async def start_discovery():
        await wait_for_admission()
        advertiser.start()

    discovery_task = asyncio.create_task(start_discovery())
    report('backend.started', process_age())
    try:
        yield
    finally:
        for task in (discovery_task, warmup_task, encoder_task):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await advertiser.close()
        await local_http_listener.close()

    # ------------------------------------------------------------------ #
    #  SHUTDOWN                                                            #
    # ------------------------------------------------------------------ #
    logger.info("Shutting down Orion Custom Service Router")
    from core.tts_archive import close_archives
    await close_archives()
    await close_gemini_clients()
    await close_http_clients()
    await db_manager.close_db()
