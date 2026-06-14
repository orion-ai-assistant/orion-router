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
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

RESET = "\033[0m"; BOLD = "\033[1m"; CYAN = "\033[96m"
GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"; GRAY = "\033[90m"

def _p(s, m, c=RESET): print(f"{c}{s}  {m}{RESET}", flush=True)
def ok(m):   _p("✔", m, GREEN)
def info(m): _p("→", m, CYAN)
def warn(m): _p("⚠", m, YELLOW)
def dim(m):  _p(" ", m, GRAY)

ROOT    = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bin.i18n import t
PG_BIN  = ROOT / "tools" / "pgsql" / "bin"
PG_CTL  = PG_BIN / "pg_ctl.exe"

DEV_DATA  = ROOT / ".pgdata-dev"
PROD_DATA = ROOT / ".pgdata-prod"

PORTS = [3001, 20128, 20129, 5433, 5444]


def run_silent(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def stop_pg(data_dir: Path, label: str):
    if data_dir.exists() and PG_CTL.exists():
        info(t("stopping_pg_label", label=label))
        run_silent([str(PG_CTL), "-D", str(data_dir), "stop"])
        ok(t("stopped_pg_label", label=label))

def kill_port(port: int):
    import shutil
    import time
    if shutil.which("docker"):
        try:
            # Docker uzerinde bu portu yayinlayan bir konteyner var mi bak
            cmd = ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.ID}}"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                container_ids = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                if container_ids:
                    for cid in container_ids:
                        dim(t("docker_cleaning_port", port=port, cid=cid))
                        subprocess.run(["docker", "stop", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                    time.sleep(1.5) # Portun temizlenmesi icin kisa bir sure bekle
        except Exception:
            pass

    killed_any = False
    try:
        result = subprocess.run(["netstat", "-aon"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid != "0":
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(t("port_killed", port=port, pid=pid))
                    killed_any = True
    except Exception:
        pass

    if killed_any:
        time.sleep(2.0)

def kill_portable_postgres():
    import time
    for data_dir in [DEV_DATA, PROD_DATA]:
        pid_file = data_dir / "postmaster.pid"
        killed_any = False

        if pid_file.exists():
            try:
                lines = pid_file.read_text().splitlines()
                if lines and lines[0].isdigit():
                    pid = lines[0]
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(t("old_pg_killed", pid=pid, name=data_dir.name))
                    killed_any = True
            except Exception:
                pass

        if killed_any:
            time.sleep(2.0)
        else:
            time.sleep(1.0)

        for file_name in ["postmaster.pid", "postmaster.opts"]:
            try:
                (data_dir / file_name).unlink(missing_ok=True)
                dim(t("stale_file_deleted", file=file_name, name=data_dir.name))
            except Exception:
                pass

def kill_all_postgres() -> None:
    import sys
    import time
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/fi", "imagename eq postgres.exe"],
                capture_output=True,
                text=True,
            )
            if "postgres.exe" in result.stdout.lower():
                run_silent(["taskkill", "/f", "/t", "/im", "postgres.exe"])
                dim(t("all_pg_killed"))
                time.sleep(2.0)
        except Exception:
            pass
    else:
        try:
            run_silent(["pkill", "-f", "postgres"])
            dim(t("all_pg_killed"))
            time.sleep(2.0)
        except Exception:
            pass

def main():
    line = "═" * 55
    print(f"\n{RED}{BOLD}╔{line}╗{RESET}")
    print(f"{RED}{BOLD}║{t('stop_title'):^55}║{RESET}")
    print(f"{RED}{BOLD}╚{line}╝{RESET}\n")

    stop_pg(DEV_DATA, "Dev")
    stop_pg(PROD_DATA, "Prod")

    info(t("cleaning_ports", ports=', '.join(map(str, PORTS))))
    for port in PORTS:
        kill_port(port)
    
    kill_portable_postgres()
    kill_all_postgres()

    print()
    ok(t("all_services_cleared"))

if __name__ == "__main__":
    main()
