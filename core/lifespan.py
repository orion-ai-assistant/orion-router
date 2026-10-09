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
import sys
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import db_manager
from dynamic_router import DynamicLLMRouter
from core.config import ROUTER_PORT
from core.model_catalog import load_model_catalog, unit_pricing
from core.http_client import close_http_clients
from providers.gemini.client import close_gemini_clients

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


def print_active_services_banner(
    router_port: str | None,
    dashboard_port: str | None = None,
) -> None:
    # Terminal Colors (ANSI)
    BLUE   = "\033[94m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    UNDERLINE = "\033[4m"
    YELLOW = "\033[93m"
    BOLD   = "\033[1m"
    GRAY   = "\033[90m"
    RESET  = "\033[0m"

    port = router_port or str(__import__('core.config', fromlist=['TLS_PORT']).TLS_PORT)
    is_docker = os.path.exists("/.dockerenv")

    # Try to resolve IP
    local_ip = os.getenv("LOCAL_IP") or os.getenv("HOST_IP")
    if not local_ip:
        if is_docker:
            local_ip = "192.168.x.x"  # Monospaced safe placeholder
        else:
            local_ip = get_local_ip()

    from core import config
    dashboard_url = f"http://localhost:{config.LOCAL_HTTP_PORT}/dashboard"
    local_url = f"https://{local_ip}:{port}/dashboard"

    try:
        from bin.i18n import t
        local_net_label = t("banner_other_devices_https")
        local_pc_label = t("banner_this_pc_http")
        cmds_hint = t("banner_commands_hint")
    except Exception:
        local_net_label = "Other devices (HTTPS)"
        local_pc_label = "This PC (HTTP)"
        cmds_hint = "Commands: orionrouter start | stop | logs | help"

    border_line = f"{GRAY}────────────────────────────────────────────────{RESET}"
    title_colored = f"{BLUE}{BOLD}ORION ROUTER{RESET}"
    dash_colored  = f"{BLUE}➜{RESET}  {BOLD}{local_pc_label}:{RESET}   {CYAN}{UNDERLINE}{dashboard_url}{RESET}"
    ip_colored    = f"{BLUE}➜{RESET}  {BOLD}{local_net_label}:{RESET}    {CYAN}{UNDERLINE}{local_url}{RESET}"

    # Print the banner block with clean newlines to separate from surrounding logs
    print()
    print(border_line)
    print(title_colored)
    print()
    print(dash_colored)
    print(ip_colored)
    print(border_line)
    print(f"{GRAY}{cmds_hint}{RESET}")
    print()


def _restart_postgres() -> None:
    """Restarts the portable PostgreSQL instance if it is in use and pg_ctl exists."""
    try:
        from bin.common import PG_CTL
        pg_ctl = PG_CTL
    except Exception:
        import shutil
        pg_ctl_path = shutil.which("pg_ctl")
        pg_ctl = Path(pg_ctl_path) if pg_ctl_path else None

    if not pg_ctl or not pg_ctl.exists():
        logger.warning("PostgreSQL pg_ctl not found. Cannot restart database automatically.")
        return

    postgres_port = os.getenv("POSTGRES_PORT")
    if postgres_port == "5444":
        data_dir = Path(__file__).parent.parent / ".pgdata-dev"
    elif postgres_port == "5433":
        data_dir = Path(__file__).parent.parent / ".pgdata-prod"
    else:
        logger.warning(f"Unknown POSTGRES_PORT ({postgres_port}), skipping auto-restart.")
        return

    if not data_dir.exists():
        logger.warning(f"Data directory {data_dir} does not exist. Skipping auto-restart.")
        return

    logger.info(f"Attempting to auto-restart PostgreSQL database ({data_dir.name})...")
    
    # 1. Stop PG
    try:
        subprocess.run(
            [str(pg_ctl), "-D", str(data_dir), "stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )
    except Exception as e:
        logger.debug(f"Error stopping postgres during restart: {e}")

    # 2. Remove stale pid
    pid_file = data_dir / "postmaster.pid"
    if pid_file.exists():
        try:
            pid_file.unlink(missing_ok=True)
            logger.info(f"Removed stale postmaster.pid from {data_dir.name}")
        except Exception as e:
            logger.warning(f"Failed to remove stale postmaster.pid: {e}")

    # 3. Start PG
    try:
        subprocess.run(
            [
                str(pg_ctl),
                "-D", str(data_dir),
                "-l", str(data_dir / "pg.log"),
                "-o", f"-p {postgres_port} -F",
                "start",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )
        logger.info("PostgreSQL restart command executed successfully.")
    except Exception as e:
        logger.error(f"Failed to start postgres during restart: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    #  STARTUP                                                             #
    # ------------------------------------------------------------------ #
    logger.info("Starting up Orion Custom Service Router")
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

    asyncio.create_task(_warmup_provider_voices())

    if os.getenv("ORION_NO_BANNER") != "1":
        if sys.platform == "win32":
            os.system("")

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
    advertiser.start()
    try:
        yield
    finally:
        await advertiser.close()
        await local_http_listener.close()

    # ------------------------------------------------------------------ #
    #  SHUTDOWN                                                            #
    # ------------------------------------------------------------------ #
    logger.info("Shutting down Orion Custom Service Router")
    await close_gemini_clients()
    await close_http_clients()
    await db_manager.close_db()
