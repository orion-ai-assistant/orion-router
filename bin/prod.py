#!/usr/bin/env python3
"""
prod.py — Orion Router | Production Environment (Native Windows)
================================================================
PostgreSQL (portable) + FastAPI (static Dashboard dahil, tek port)

Docker gerekmez. Next.js once build edilir, ardından FastAPI
dashboard/out klasorunden statik dosyalari sunarak calisir.

Kullanim:
    python prod.py
"""

import os
import sys
import time
import subprocess
import urllib.request
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import shared helpers and definitions from common.py
from bin.common import (
    ROOT, DASHBOARD, PG_BIN, DEFAULT_TIMEOUT,
    RESET, BOLD, CYAN, GREEN, YELLOW, RED, GRAY,
    ok, info, warn, err, dim,
    acquire_lock, release_lock, run, run_silent, psql, read_env,
    kill_port, kill_portable_postgres, free_ports,
    download_postgres, init_database, start_postgres, wait_for_postgres, stop_postgres,
    setup_db_and_user, set_env
)

from core.lifespan import print_active_services_banner
from bin.npm_integrity import npm_needs_install, record_npm_install
from bin.i18n import t

# ─────────────────────────────────────────────────────────────────────────────
# Prod-Specific Paths & Constants
# ─────────────────────────────────────────────────────────────────────────────
PG_DATA   = ROOT / ".pgdata-prod"
PG_LOG    = PG_DATA / "pg.log"

PG_PORT   = 5433
PG_USER   = "router_user"
PG_PASS   = "router_pass"
PG_DB     = "orion_router"


# ─────────────────────────────────────────────────────────────────────────────
# Prod-Specific Setup, Launch, & Shutdown
# ─────────────────────────────────────────────────────────────────────────────

def build_dashboard(router_port: str) -> None:
    info(t("db_build_dashboard"))
    
    if npm_needs_install(DASHBOARD):
        dim(t("npm_installing_deps"))
        result_npm = run(["npm", "install"], cwd=DASHBOARD, shell=True)
        if result_npm.returncode != 0:
            err(t("npm_install_failed"))
            sys.exit(1)
        record_npm_install(DASHBOARD)

    env = {**os.environ, "NEXT_PUBLIC_ROUTER_PORT": router_port}
    result = run(
        ["npm", "run", "build"],
        cwd=DASHBOARD,
        shell=True,
        env=env,
    )
    if result.returncode != 0:
        err(t("err_dashboard_build_failed"))
        sys.exit(1)
    ok(t("dashboard_build_complete"))


def launch(router_port: str) -> list[tuple[str, subprocess.Popen]]:
    procs = []

    backend = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
    )
    procs.append(("FastAPI", backend))

    return procs


def shutdown(procs: list) -> None:
    print(f"\n{RED}✘  {t('shutdown_received')}{RESET}", flush=True)
    for name, proc in procs:
        try:
            run_silent(["taskkill", "/f", "/t", "/pid", str(proc.pid)])
            dim(t("service_closed", name=name, pid=proc.pid))
        except Exception:
            pass
    info(t("stopping_pg_label", label="PostgreSQL"))
    stop_postgres(PG_DATA)
    ok(t("all_services_shutdown"))


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def banner() -> None:
    line = "═" * 55
    print(f"\n{CYAN}{BOLD}╔{line}╗{RESET}")
    print(f"{CYAN}{BOLD}║{t('prod_title'):^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def main() -> None:
    if not acquire_lock(".orion.prod.lock"):
        err(t("err_lock_fail"))
        sys.exit(1)

    banner()

    run_silent([sys.executable, "-c", "import core.config"], cwd=ROOT)
    router_port = read_env("ROUTER_PORT", "20128")

    free_ports([int(router_port), PG_PORT], PG_DATA, "prod")
    print()

    download_postgres()
    init_database(PG_DATA, PG_USER)
    start_postgres(PG_DATA, PG_PORT, PG_LOG, "prod")
    wait_for_postgres(PG_DATA, PG_PORT, PG_LOG, PG_USER, "prod")
    setup_db_and_user(PG_USER, PG_PASS, PG_PORT, PG_DB)
    print()

    build_dashboard(router_port)
    print()

    set_env(router_port, PG_PORT, PG_DB, PG_USER, PG_PASS, "0")
    procs = launch(router_port)

    # ── Print Banner when server is ready ───────
    def wait_for_server_and_print_banner(port: str) -> None:
        url = f"http://127.0.0.1:{port}/health"
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status == 200:
                        time.sleep(2.0)
                        print_active_services_banner(port)
                        return
            except Exception:
                pass
            time.sleep(0.5)

    banner_thread = threading.Thread(target=wait_for_server_and_print_banner, args=[router_port])
    banner_thread.daemon = True
    banner_thread.start()

    try:
        while True:
            alive = [p for _, p in procs if p.poll() is None]
            if not alive:
                warn(t("service_crashed_single"))
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)
        release_lock(".orion.prod.lock")


if __name__ == "__main__":
    main()
