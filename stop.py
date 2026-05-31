#!/usr/bin/env python3
"""
stop.py — Orion Router | Acil Durdurma
=======================================
Arka planda calismayi surduren PostgreSQL sunucularini ve
ilgili portlardaki surecleri temizler.

Kullanim:
    python stop.py
"""

import os
import sys
import subprocess
from pathlib import Path

if sys.platform == "win32":
    os.system("")

RESET = "\033[0m"; BOLD = "\033[1m"; CYAN = "\033[96m"
GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"; GRAY = "\033[90m"

def _p(s, m, c=RESET): print(f"{c}{s}  {m}{RESET}", flush=True)
def ok(m):   _p("✔", m, GREEN)
def info(m): _p("→", m, CYAN)
def warn(m): _p("⚠", m, YELLOW)
def dim(m):  _p(" ", m, GRAY)

ROOT    = Path(__file__).parent.resolve()
PG_BIN  = ROOT / "tools" / "pgsql" / "bin"
PG_CTL  = PG_BIN / "pg_ctl.exe"

DEV_DATA  = ROOT / ".pgdata-dev"
PROD_DATA = ROOT / ".pgdata-prod"

PORTS = [3001, 20128, 20129, 5433, 5444]


def run_silent(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def stop_pg(data_dir: Path, label: str):
    if data_dir.exists() and PG_CTL.exists():
        info(f"{label} PostgreSQL durduruluyor...")
        run_silent([str(PG_CTL), "-D", str(data_dir), "stop"])
        ok(f"{label} PostgreSQL durduruldu")

def kill_port(port: int):
    try:
        result = subprocess.run(["netstat", "-aon"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid != "0":
                    run_silent(["taskkill", "/f", "/pid", pid])
                    dim(f"    Port {port} → PID {pid} kapatildi")
    except Exception:
        pass

def main():
    line = "═" * 55
    print(f"\n{RED}{BOLD}╔{line}╗{RESET}")
    print(f"{RED}{BOLD}║{'Orion Router — Acil Durdurma':^55}║{RESET}")
    print(f"{RED}{BOLD}╚{line}╝{RESET}\n")

    stop_pg(DEV_DATA, "Dev")
    stop_pg(PROD_DATA, "Prod")

    info(f"Portlar temizleniyor: {', '.join(map(str, PORTS))}...")
    for port in PORTS:
        kill_port(port)

    print()
    ok("Tum servisler ve portlar temizlendi.")

if __name__ == "__main__":
    main()
