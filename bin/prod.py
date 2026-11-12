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
    download_postgres, init_database, stop_postgres,
    set_env
)

from core.banner import print_active_services_banner
from core.tls_local import open_health
from bin.dashboard_build import ensure_dashboard
from bin.i18n import t
from core.launch_timing import process_age, report, timed

# ─────────────────────────────────────────────────────────────────────────────
# Prod-Specific Paths & Constants
# ─────────────────────────────────────────────────────────────────────────────
from core.runtime_layout import data_root
PG_DATA   = data_root(ROOT) / ".pgdata-prod"
PG_LOG    = PG_DATA / "pg.log"

PG_PORT   = int(read_env("POSTGRES_PORT", ""))
PG_USER   = "router_user"  # The cluster's superuser (initdb): only for setup and readiness.
PG_APP_USER = "router_app"  # The Router's own logins: owns orion_router, no superuser.
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


class CrashBackoff:
    """main.py ended without being asked to: started again after 1, 2, 4 ... up to 60 s and never given up (the
    supervisor used to stop, leaving the Router down until someone started it). A run of STABLE seconds starts
    the delays over."""
    STABLE = 600
    MAX_DELAY = 60

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.failures = 0
        self.started = clock()

    def crashed(self) -> float:
        if self.clock() - self.started >= self.STABLE:
            self.failures = 0
        delay = min(2 ** self.failures, self.MAX_DELAY)
        self.failures += 1
        return delay

    def started_now(self) -> None:
        self.started = self.clock()


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

        # core.config is already imported (core.tls_local): .env exists and is merged with .env.example.
        router_port = read_env("ORION_ROUTER_TLS_PORT", "9443")
        from bin.common import database, database_passwords
        from core import postgres_auth
        passwords = database_passwords()
        admin, app = (PG_USER, passwords['admin']), (PG_APP_USER, passwords['app'])
        pg = database(PG_DATA, PG_PORT, PG_USER, password=passwords['admin'])

        from core.process_lifecycle import assert_port_free
        if 'backend' not in runtime.children:
            assert_port_free(router_port)
        print()

        download_postgres()
        init_database(PG_DATA, PG_USER)
        # This supervisor owns its database (core/native_postgres.py): a server whose owner has ended is
        # restarted as ours, never reused ownerless, and it ends with this supervisor at the latest.
        runtime.database = pg
        postgres_auth.prepare(pg, admin, app, PG_DB)
        with timed('router.postgres.start'):
            pg.ensure()
        started_postgres = True
        with timed('router.postgres.setup'):
            # Creates the database on the first start; from then on only password logins from this PC.
            try:
                protected = postgres_auth.secure(pg, admin, app, PG_DB)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                warn(f'PostgreSQL password setup failed: {error}')
                protected = False
            if not protected:
                warn('PostgreSQL still accepts logins without a password from this PC')
        print()

        ensure_dashboard(force=force_build)
        print()

        set_env(router_port, PG_PORT, PG_DB, PG_APP_USER, passwords["app"], "0")
        with timed('router.backend'):
            procs.extend(launch(router_port, runtime))

            from core.process_lifecycle import wait_health
            from core import config
            wait_health(procs[0][1], router_port, certificate=config.TLS_DIRECTORY / 'certificate.pem',
                        identity=config.MDNS_ID_FILE.read_text().strip())
        runtime.ready()
        report('router.ready', process_age())

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

        backoff = CrashBackoff()
        while not runtime.requested():
            try:
                runtime.refresh_children()
            except Exception as exc:  # A look that fails this second must not stop a serving Router.
                warn(f"Child records not refreshed: {exc}")
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
                    backoff.started_now()
                    continue
                warn(t("service_crashed_single"))
                delay = backoff.crashed()
                info(f"Router service is started again in {delay:.0f} s")
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline and not runtime.requested():
                    time.sleep(.5)
                if runtime.requested():
                    break
                try:
                    procs = launch(router_port, runtime)
                    backoff.started_now()
                except Exception as exc:  # Its port or old process still held: the next round tries again.
                    warn(f"Router service could not start again: {exc}")
                continue
            time.sleep(1)
    except RuntimeError as exc:
        err(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs, started_postgres, runtime)


def main(force_build=False):
    report('router.process', process_age())
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
