#!/usr/bin/env python3
"""
dev.py — Orion Router | Development Environment
================================================
PostgreSQL (portable) + FastAPI (hot-reload) + Next.js (hot-reload)

Kullanim:
    python dev.py
"""

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
# Dev-Specific Paths & Constants
# ─────────────────────────────────────────────────────────────────────────────
PG_DATA   = ROOT / ".pgdata-dev"
PG_LOG    = PG_DATA / "pg.log"

PG_PORT   = 5444
PG_USER   = "router_user_dev"
PG_PASS   = "router_pass_dev"
PG_DB     = "orion_router_dev"
UI_PORT   = 3001


# ─────────────────────────────────────────────────────────────────────────────
# Dev-Specific Launch & Shutdown
# ─────────────────────────────────────────────────────────────────────────────

def launch(router_port: str) -> list[tuple[str, subprocess.Popen]]:
    procs = []

    # FastAPI backend
    backend = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
    )
    procs.append(("FastAPI", backend))

    # Next.js frontend
    if npm_needs_install(DASHBOARD):
        dim(t("npm_installing_deps"))
        result_npm = run(["npm", "install"], cwd=DASHBOARD, shell=True)
        if result_npm.returncode != 0:
            err(t("npm_install_failed"))
            sys.exit(1)
        record_npm_install(DASHBOARD)

    frontend = subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(UI_PORT), "-H", "0.0.0.0"],
        cwd=DASHBOARD,
        shell=True,
    )
    procs.append(("Next.js", frontend))

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
    print(f"{CYAN}{BOLD}║{t('dev_title'):^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def main() -> None:
    if not acquire_lock(".orion.dev.lock"):
        err(t("err_lock_fail"))
        sys.exit(1)

    banner()

    run_silent([sys.executable, "-c", "import core.config"], cwd=ROOT)
    router_port = read_env("ROUTER_DEV_PORT", "20129")

    free_ports([UI_PORT, int(router_port), PG_PORT], PG_DATA, "dev")
    print()

    download_postgres()
    init_database(PG_DATA, PG_USER)
    start_postgres(PG_DATA, PG_PORT, PG_LOG, "dev")
    wait_for_postgres(PG_DATA, PG_PORT, PG_LOG, PG_USER, "dev")
    setup_db_and_user(PG_USER, PG_PASS, PG_PORT, PG_DB)
    print()

    set_env(router_port, PG_PORT, PG_DB, PG_USER, PG_PASS, "1")
    procs = launch(router_port)

    def wait_for_server_and_print_banner(port: str) -> None:
        backend_url = f"http://127.0.0.1:{port}/health"
        backend_ready = False
        frontend_ready = False
        start_time = time.time()
        while time.time() - start_time < 30:
            if not backend_ready:
                try:
                    with urllib.request.urlopen(backend_url, timeout=1.0) as resp:
                        if resp.status == 200:
                            backend_ready = True
                except Exception:
                    pass

            if not frontend_ready:
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", UI_PORT), timeout=1.0):
                        frontend_ready = True
                except Exception:
                    pass

            if backend_ready and frontend_ready:
                time.sleep(2.5)
                print_active_services_banner(port, dashboard_port=str(UI_PORT))
                return
            time.sleep(0.5)

    banner_thread = threading.Thread(target=wait_for_server_and_print_banner, args=[router_port])
    banner_thread.daemon = True
    banner_thread.start()

    try:
        while True:
            alive = [p for _, p in procs if p.poll() is None]
            if len(alive) < len(procs):
                dead_names = [name for name, p in procs if p.poll() is not None]
                warn(t("service_crashed_multi", names=', '.join(dead_names)))
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)
        release_lock(".orion.dev.lock")


if __name__ == "__main__":
    main()
