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

import argparse
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
from bin.dashboard_build import ensure_dashboard
from bin.i18n import t

# ─────────────────────────────────────────────────────────────────────────────
# Prod-Specific Paths & Constants
# ─────────────────────────────────────────────────────────────────────────────
from core.runtime_layout import data_root
PG_DATA   = data_root(ROOT) / ".pgdata-prod"
PG_LOG    = PG_DATA / "pg.log"

PG_PORT   = int(read_env("POSTGRES_PORT", ""))
PG_USER   = "router_user"
PG_PASS   = "router_pass"
PG_DB     = "orion_router"


# ─────────────────────────────────────────────────────────────────────────────
# Prod-Specific Setup, Launch, & Shutdown
# ─────────────────────────────────────────────────────────────────────────────

def launch(router_port: str, runtime) -> list[tuple[str, subprocess.Popen]]:
    procs = []

    backend = runtime.launch('backend',
        [sys.executable, str(ROOT / "main.py")], python=True,
        cwd=ROOT,
        stdin=subprocess.DEVNULL
    )
    procs.append(("FastAPI", backend))

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
    print(f"{CYAN}{BOLD}║{t('prod_title'):^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def _main(runtime, force_build: bool = False) -> None:
    procs = []
    started_postgres = False
    try:
        banner()

        run_silent([sys.executable, "-c", "import core.config"], cwd=ROOT)
        router_port = read_env("ORION_ROUTER_TLS_PORT", "9443")
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
            start_postgres(PG_DATA, PG_PORT, PG_LOG, "prod")
            started_postgres = True
            wait_for_postgres(PG_DATA, PG_PORT, PG_LOG, PG_USER, "prod")
        runtime.database = pg
        setup_db_and_user(PG_USER, PG_PASS, PG_PORT, PG_DB)
        print()

        ensure_dashboard(force=force_build)
        print()

        set_env(router_port, PG_PORT, PG_DB, PG_USER, PG_PASS, "0")
        procs.extend(launch(router_port, runtime))

        from core.process_lifecycle import wait_health
        from core import config
        wait_health(procs[0][1], router_port, certificate=config.TLS_DIRECTORY / 'certificate.pem',
                    identity=config.MDNS_ID_FILE.read_text().strip())
        runtime.ready()

        # ── Print Banner when server is ready ───────
        def wait_for_server_and_print_banner(port: str) -> None:
            url = f"https://127.0.0.1:{port}/health"
            start_time = time.time()
            while time.time() - start_time < DEFAULT_TIMEOUT:
                try:
                    with open_health(url, timeout=1.0) as resp:
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

        while not runtime.requested():
            runtime.refresh_children()
            alive = [p for _, p in procs if p.poll() is None]
            if not alive:
                restart_flag = ROOT / ".restart_requested"
                if restart_flag.exists():
                    try:
                        restart_flag.unlink()
                    except Exception:
                        pass
                    info(f"{CYAN}{BOLD}✔  Güncelleme sonrası servis yeniden başlatılıyor...{RESET}")
                    time.sleep(0.5)
                    procs = launch(router_port, runtime)
                    continue
                warn(t("service_crashed_single"))
                break
            time.sleep(1)
    except RuntimeError as exc:
        err(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs, started_postgres, runtime)


def main(force_build=False):
    from core.update_gate import require_start_admission
    require_start_admission(ROOT)
    from core.process_lifecycle import Runtime
    with Runtime(ROOT, 'router-prod') as runtime:
        return _main(runtime, force_build)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", "--force-build", dest="force_build",
                        action="store_true", help="Force a dashboard rebuild")
    main(force_build=parser.parse_args().force_build)
