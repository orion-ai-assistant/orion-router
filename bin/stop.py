#!/usr/bin/env python3
"""
stop.py — Orion Router | Acil Durdurma
=======================================
Arka planda calismayi surduren PostgreSQL sunucularini ve
ilgili portlardaki surecleri temizler.

Kullanim:
    python stop.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import shared helpers and definitions from common.py
from bin.common import (
    ROOT, PG_CTL, DEFAULT_TIMEOUT,
    RESET, BOLD, CYAN, GREEN, YELLOW, RED, GRAY,
    ok, info, warn, err, dim,
    run_silent, stop_postgres, kill_port, kill_portable_postgres, kill_all_postgres, kill_orion_pid
)

from bin.i18n import t

DEV_DATA  = ROOT / ".pgdata-dev"
PROD_DATA = ROOT / ".pgdata-prod"

PORTS = [3001, 20128, 20129, 5433, 5444]
QUIET_MODE = "--quiet" in sys.argv


def stop_pg(data_dir: Path, label: str) -> bool:
    if data_dir.exists() and PG_CTL.exists():
        if not QUIET_MODE:
            info(t("stopping_pg_label", label=label))
        stop_postgres(data_dir)
        ok(t("stopped_pg_label", label=label))
        return True
    return False


def kill_portable_postgres_all() -> bool:
    killed_any = False
    if kill_portable_postgres(DEV_DATA, "dev"):
        killed_any = True
    if kill_portable_postgres(PROD_DATA, "prod"):
        killed_any = True
    return killed_any


def main():
    if not QUIET_MODE:
        line = "═" * 55
        print(f"\n{RED}{BOLD}╔{line}╗{RESET}")
        print(f"{RED}{BOLD}║{t('stop_title'):^55}║{RESET}")
        print(f"{RED}{BOLD}╚{line}╝{RESET}\n")

    actions_taken = False

    if kill_orion_pid():
        actions_taken = True
    if stop_pg(DEV_DATA, "Dev"):
        actions_taken = True
    if stop_pg(PROD_DATA, "Prod"):
        actions_taken = True

    if not QUIET_MODE:
        info(t("cleaning_ports", ports=', '.join(map(str, PORTS))))
        
    for port in PORTS:
        if kill_port(port):
            actions_taken = True
    
    if kill_portable_postgres_all():
        actions_taken = True
    if kill_all_postgres():
        actions_taken = True

    if not QUIET_MODE:
        print()
        ok(t("all_services_cleared"))


if __name__ == "__main__":
    main()
