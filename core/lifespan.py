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
import os
import sys
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import db_manager
from dynamic_router import DynamicLLMRouter
from core.config import MODEL_PRICING_PATH, ROUTER_PORT

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
    YELLOW = "\033[93m"
    BOLD   = "\033[1m"
    GRAY   = "\033[90m"
    RESET  = "\033[0m"

    port = router_port or "20128"
    is_docker = os.path.exists("/.dockerenv")

    # Try to resolve IP
    local_ip = os.getenv("LOCAL_IP") or os.getenv("HOST_IP")
    if not local_ip:
        if is_docker:
            local_ip = "192.168.x.x"  # Monospaced safe placeholder
        else:
            local_ip = get_local_ip()

    public_port = dashboard_port or port
    dashboard_url = f"http://127.0.0.1:{public_port}"
    local_url = f"http://{local_ip}:{public_port}"

    try:
        from bin.i18n import t
        local_net_label = t("banner_local_network")
        cmds_hint = t("banner_commands_hint")
    except Exception:
        local_net_label = "Local Network"
        cmds_hint = "Commands: orionrouter start | stop | logs | help"

    border_line = f"{GRAY}────────────────────────────────────────────────{RESET}"
    title_colored = f"{BLUE}{BOLD}ORION ROUTER{RESET}"
    dash_colored  = f"{BLUE}➜{RESET}  {BOLD}Dashboard:{RESET}   {CYAN}{dashboard_url}{RESET}"
    ip_colored    = f"{BLUE}➜{RESET}  {BOLD}{local_net_label}:{RESET}    {CYAN}{local_url}{RESET}"

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
    if sys.platform != "win32":
        return

    root = Path(__file__).parent.parent.resolve()
    pg_bin = root / "tools" / "pgsql" / "bin"
    pg_ctl = pg_bin / "pg_ctl.exe"

    if not pg_ctl.exists():
        logger.warning("Portable pg_ctl.exe not found. Cannot restart database automatically.")
        return

    postgres_port = os.getenv("POSTGRES_PORT")
    if postgres_port == "5444":
        data_dir = root / ".pgdata-dev"
    elif postgres_port == "5433":
        data_dir = root / ".pgdata-prod"
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


    # --- Cache'i yükle ---
    from core.dependencies import prewarm_vkey_cache
    await prewarm_vkey_cache()
    
    app.state.pricing_cache = await db_manager.get_all_pricing()

    # Provider API key'lerini DB'den yükle (runtime'da güncellenebilir)
    raw_keys = await db_manager.get_config("provider_api_keys")
    app.state.provider_keys = raw_keys if isinstance(raw_keys, dict) else {}

    app.state.dynamic_router = DynamicLLMRouter(app.state)

    if os.getenv("ORION_NO_BANNER") != "1":
        if sys.platform == "win32":
            os.system("")

        async def _show_banner_after_startup():
            # Uvicorn'un 'Application startup complete.' logunu basması için
            # çok kısa (50ms), bloklamayan bir arka plan beklemesi yaparız.
            await asyncio.sleep(0.05)
            print_active_services_banner(ROUTER_PORT)

        asyncio.create_task(_show_banner_after_startup())

    yield

    # ------------------------------------------------------------------ #
    #  SHUTDOWN                                                            #
    # ------------------------------------------------------------------ #
    logger.info("Shutting down Orion Custom Service Router")
    await db_manager.close_db()
