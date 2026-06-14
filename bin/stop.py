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

QUIET_MODE = "--quiet" in sys.argv

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

def stop_pg(data_dir: Path, label: str) -> bool:
    if data_dir.exists() and PG_CTL.exists():
        if not QUIET_MODE: info(t("stopping_pg_label", label=label))
        run_silent([str(PG_CTL), "-D", str(data_dir), "stop"])
        if QUIET_MODE: ok(t("stopped_pg_label", label=label))
        else: ok(t("stopped_pg_label", label=label))
        return True
    return False

def kill_port(port: int) -> bool:
    import shutil
    import time
    killed_any = False
    
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
                        killed_any = True
                    time.sleep(1.5) # Portun temizlenmesi icin kisa bir sure bekle
        except Exception:
            pass

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
        
    return killed_any

def kill_portable_postgres() -> bool:
    import time
    killed_any_process = False
    cleaned_files = False
    
    for data_dir in [DEV_DATA, PROD_DATA]:
        pid_file = data_dir / "postmaster.pid"

        if pid_file.exists():
            try:
                lines = pid_file.read_text().splitlines()
                if lines and lines[0].isdigit():
                    pid = lines[0]
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(t("old_pg_killed", pid=pid, name=data_dir.name))
                    killed_any_process = True
            except Exception:
                pass

        for file_name in ["postmaster.pid", "postmaster.opts"]:
            try:
                target_file = data_dir / file_name
                if target_file.exists():
                    target_file.unlink(missing_ok=True)
                    dim(t("stale_file_deleted", file=file_name, name=data_dir.name))
                    cleaned_files = True
            except Exception:
                pass

    if killed_any_process:
        time.sleep(2.0)
    elif cleaned_files:
        time.sleep(1.0)
        
    return killed_any_process or cleaned_files

def kill_all_postgres() -> bool:
    import sys
    import time
    killed_any = False
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
                killed_any = True
                time.sleep(2.0)
        except Exception:
            pass
    else:
        try:
            res = subprocess.run(["pgrep", "-f", "postgres"], capture_output=True, text=True)
            if res.stdout.strip():
                run_silent(["pkill", "-f", "postgres"])
                dim(t("all_pg_killed"))
                killed_any = True
                time.sleep(2.0)
        except Exception:
            pass
    return killed_any

def kill_orion_pid() -> bool:
    import time
    killed_any = False
    pid_file = ROOT / ".orion.pid"
    if pid_file.exists():
        try:
            lines = pid_file.read_text().splitlines()
            if lines and lines[0].isdigit():
                pid = lines[0]
                if sys.platform == "win32":
                    check = run_silent(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"])
                    if check.returncode == 0:
                        run_silent(["taskkill", "/f", "/t", "/pid", pid])
                        dim(t("old_pg_killed", pid=pid, name="orion router"))
                        killed_any = True
                else:
                    res = subprocess.run(["pgrep", "-P", pid], capture_output=True, text=True)
                    if res.returncode == 0:
                        run_silent(["pkill", "-P", pid])
                    run_silent(["kill", "-9", pid])
                    dim(t("old_pg_killed", pid=pid, name="orion router"))
                    killed_any = True
        except Exception:
            pass
        finally:
            try:
                pid_file.unlink(missing_ok=True)
                dim(t("stale_file_deleted", file=".orion.pid", name="router"))
                killed_any = True
            except Exception:
                pass
    return killed_any

def main():
    if not QUIET_MODE:
        line = "═" * 55
        print(f"\n{RED}{BOLD}╔{line}╗{RESET}")
        print(f"{RED}{BOLD}║{t('stop_title'):^55}║{RESET}")
        print(f"{RED}{BOLD}╚{line}╝{RESET}\n")

    actions_taken = False

    if kill_orion_pid(): actions_taken = True
    if stop_pg(DEV_DATA, "Dev"): actions_taken = True
    if stop_pg(PROD_DATA, "Prod"): actions_taken = True

    if not QUIET_MODE:
        info(t("cleaning_ports", ports=', '.join(map(str, PORTS))))
        
    for port in PORTS:
        if kill_port(port): actions_taken = True
    
    if kill_portable_postgres(): actions_taken = True
    if kill_all_postgres(): actions_taken = True

    if not QUIET_MODE:
        print()
        ok(t("all_services_cleared"))
    elif actions_taken:
        # Sadece sessiz moddaysak ve gercekten bir seyler yapildiysa ekstra bosluk atalim
        pass

if __name__ == "__main__":
    main()


