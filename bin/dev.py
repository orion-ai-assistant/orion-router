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
    ROOT, DASHBOARD, DEFAULT_TIMEOUT,
    RESET, BOLD, CYAN, GREEN, YELLOW, RED, GRAY,
    ok, info, warn, err, dim,
    acquire_lock, release_lock, run, run_silent, psql, read_env,
    kill_port, kill_portable_postgres, free_ports, postgres_is_ready,
    download_postgres, init_database, start_postgres, wait_for_postgres, stop_postgres,
    setup_db_and_user, set_env
)

from core.lifespan import print_active_services_banner
from core.tls_local import open_health
from bin.npm_integrity import npm_needs_install, record_npm_install
from bin.i18n import t

# ─────────────────────────────────────────────────────────────────────────────
# Dev-Specific Paths & Constants
# ─────────────────────────────────────────────────────────────────────────────
PG_DATA   = ROOT / ".pgdata-dev"
PG_LOG    = PG_DATA / "pg.log"

PG_PORT   = int(read_env("POSTGRES_DEV_PORT", ""))
PG_USER   = "router_user_dev"
PG_PASS   = "router_pass_dev"
PG_DB     = "orion_router_dev"
UI_PORT   = int(read_env("UI_PORT", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Dev-Specific Launch & Shutdown
# ─────────────────────────────────────────────────────────────────────────────

def launch(router_port: str, runtime) -> list[tuple[str, subprocess.Popen]]:
    procs = []

    # FastAPI backend
    dev_env = {**dict(sys.modules['os'].environ), "UVICORN_RELOAD": "1"}
    backend = runtime.launch('backend',
        [sys.executable, str(ROOT / "main.py")], python=True,
        cwd=ROOT,
        env=dev_env,
        stdin=subprocess.DEVNULL
    )
    procs.append(("FastAPI", backend))

    # Wait for FastAPI backend to be ready before launching Next.js dev server
    # to prevent ECONNREFUSED error on startup proxying
    info(t("waiting_for_backend"))
    backend_url = f"https://127.0.0.1:{router_port}/health"
    start_time = time.time()
    while time.time() - start_time < 30:
        if backend.poll() is not None:
            break
        try:
            with open_health(backend_url, timeout=1.0) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        time.sleep(0.5)

    # Next.js frontend
    if npm_needs_install(DASHBOARD):
        dim(t("npm_installing_deps"))
        result_npm = run("npm install", cwd=DASHBOARD, shell=True)
        if result_npm.returncode != 0:
            err(t("npm_install_failed"))
            sys.exit(1)
        record_npm_install(DASHBOARD)

    node = __import__('shutil').which('node')
    if not node:
        raise RuntimeError('Node runtime missing')
    frontend = runtime.launch('frontend', [node, str(DASHBOARD / 'node_modules/next/dist/bin/next'),
        'dev', '-p', str(UI_PORT), '-H', '127.0.0.1', '--experimental-https',
        '--experimental-https-key', sys.modules['os'].environ['ORION_TLS_KEY'],
        '--experimental-https-cert', sys.modules['os'].environ['ORION_TLS_CERT']], cwd=DASHBOARD, node=True)
    procs.append(("Next.js", frontend))

    return procs


def shutdown(procs, stop_pg, runtime):
    runtime.stop_children()
    # Database is stopped by Runtime only after every child exit is verified.


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def banner() -> None:
    line = "═" * 55
    print(f"\n{CYAN}{BOLD}╔{line}╗{RESET}")
    print(f"{CYAN}{BOLD}║{t('dev_title'):^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def _main(runtime) -> None:
    procs = []
    started_postgres = False
    try:
        banner()

        run_silent([sys.executable, "-c", "import core.config"], cwd=ROOT)
        router_port = read_env("ORION_ROUTER_TLS_DEV_PORT", "9444")
        from bin.common import database
        pg = database(PG_DATA, PG_PORT, PG_USER)
        reuse_postgres = bool(pg.owner())
        if reuse_postgres and not pg.ready():
            raise RuntimeError('Existing database not ready')

        from core.process_lifecycle import assert_port_free
        if 'backend' not in runtime.children:
            assert_port_free(router_port)
        if not reuse_postgres:
            assert_port_free(PG_PORT)
        print()

        download_postgres()
        init_database(PG_DATA, PG_USER)
        if reuse_postgres:
            ok(t("pg_reusing_existing"))
        else:
            start_postgres(PG_DATA, PG_PORT, PG_LOG, "dev")
            started_postgres = True
            wait_for_postgres(PG_DATA, PG_PORT, PG_LOG, PG_USER, "dev")
        runtime.database = pg
        setup_db_and_user(PG_USER, PG_PASS, PG_PORT, PG_DB)
        print()

        set_env(router_port, PG_PORT, PG_DB, PG_USER, PG_PASS, "1")
        procs.extend(launch(router_port, runtime))

        from core.process_lifecycle import wait_health
        from core import config
        wait_health(procs[0][1], router_port, certificate=config.TLS_DIRECTORY / 'certificate.pem',
                    identity=config.MDNS_ID_FILE.read_text().strip())
        wait_health(procs[1][1], UI_PORT, certificate=config.TLS_DIRECTORY / 'certificate.pem',
                    path='/dashboard', json_response=False, timeout=60)
        runtime.ready()

        def wait_for_server_and_print_banner(port: str) -> None:
            backend_url = f"https://127.0.0.1:{port}/health"
            backend_ready = False
            frontend_ready = False
            start_time = time.time()
            while time.time() - start_time < 30:
                if not backend_ready:
                    try:
                        with open_health(backend_url, timeout=1.0) as resp:
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

        while not runtime.requested():
            runtime.refresh_children()
            alive = [p for _, p in procs if p.poll() is None]
            if len(alive) < len(procs):
                dead_names = [name for name, p in procs if p.poll() is not None]
                warn(t("service_crashed_multi", names=', '.join(dead_names)))
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs, started_postgres, runtime)



def main():
    from core.process_lifecycle import Runtime
    with Runtime(ROOT, 'router-dev') as runtime:
        return _main(runtime)


if __name__ == "__main__":
    main()
