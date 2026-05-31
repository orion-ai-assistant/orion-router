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
import shutil
import time
import subprocess
import urllib.request
import zipfile
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Terminal Colors
# ─────────────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("")

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
GRAY   = "\033[90m"


def _p(symbol: str, msg: str, color: str = RESET) -> None:
    print(f"{color}{symbol}  {msg}{RESET}", flush=True)

def ok(msg: str)   -> None: _p("✔", msg, GREEN)
def info(msg: str) -> None: _p("→", msg, CYAN)
def warn(msg: str) -> None: _p("⚠", msg, YELLOW)
def err(msg: str)  -> None: _p("✘", msg, RED)
def dim(msg: str)  -> None: _p(" ", msg, GRAY)


# ─────────────────────────────────────────────────────────────────────────────
# Paths & Constants
# ─────────────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.resolve()
TOOLS_DIR = ROOT / "tools"
PG_BIN    = TOOLS_DIR / "pgsql" / "bin"
PG_DATA   = ROOT / ".pgdata-prod"
PG_LOG    = PG_DATA / "pg.log"
DASHBOARD = ROOT / "dashboard"

PG_PORT   = 5433
PG_USER   = "router_user"
PG_PASS   = "router_pass"
PG_DB     = "orion_router"

INITDB  = PG_BIN / "initdb.exe"
PG_CTL  = PG_BIN / "pg_ctl.exe"
PSQL    = PG_BIN / "psql.exe"

PG_DOWNLOAD_URL = (
    "https://get.enterprisedb.com/postgresql/"
    "postgresql-16.3-1-windows-x64-binaries.zip"
)
PG_ZIP = TOOLS_DIR / "postgresql.zip"


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)

def run_silent(cmd: list) -> subprocess.CompletedProcess:
    return run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def psql(*args) -> subprocess.CompletedProcess:
    base = [str(PSQL), "-U", PG_USER, "-p", str(PG_PORT), "-d", "postgres"]
    return run_silent(base + list(args))

def read_env(key: str, default: str) -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    return default

def kill_port(port: int) -> None:
    try:
        result = run(["netstat", "-aon"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid != "0":
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(f"    Port {port} → PID {pid} kapatildi")
    except Exception:
        pass

def kill_portable_postgres() -> None:
    """Kill all postgres.exe processes running from the portable tools directory."""
    if sys.platform != "win32":
        return
    try:
        target_path = str(PG_BIN / "postgres.exe")
        escaped_path = target_path.replace("'", "''")
        cmd = [
            "powershell",
            "-Command",
            f"Get-Process -Name postgres -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.Path -eq '{escaped_path}' }} | "
            f"Stop-Process -Force"
        ]
        run_silent(cmd)
    except Exception:
        pass

    # Clean up stale postmaster.pid
    pid_file = PG_DATA / "postmaster.pid"
    if pid_file.exists():
        try:
            pid_file.unlink(missing_ok=True)
            dim("    Stale postmaster.pid silindi")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Prerequisite Checks
# ─────────────────────────────────────────────────────────────────────────────

def check_npm() -> None:
    if not shutil.which("npm"):
        err("npm bulunamadi! https://nodejs.org adresinden Node.js kur.")
        sys.exit(1)
    ok("Node.js / npm mevcut")

def check_python_deps() -> None:
    try:
        import fastapi, uvicorn, asyncpg  # noqa: F401
        ok("Python bagimliliklari mevcut")
    except ImportError:
        warn("Python bagimliliklari eksik — yukleniyor...")
        run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=ROOT)
        try:
            import fastapi, uvicorn, asyncpg  # noqa: F401
            ok("Python bagimliliklari yuklendi")
        except ImportError:
            err("Python bagimliliklari yuklenemedi!")
            sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Free Ports
# ─────────────────────────────────────────────────────────────────────────────

def free_ports(router_port: str) -> None:
    info(f"Portlar temizleniyor: {router_port}, {PG_PORT}...")
    for port in [int(router_port), PG_PORT]:
        kill_port(port)
    kill_portable_postgres()


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — PostgreSQL Portable
# ─────────────────────────────────────────────────────────────────────────────

def _download_progress(block_num: int, block_size: int, total: int) -> None:
    done = min(block_num * block_size, total)
    pct  = int(done * 100 / total)
    bar  = "█" * (pct // 5) + "░" * (20 - pct // 5)
    mb   = done / 1_048_576
    print(f"\r    [{bar}] {pct:3d}%  {mb:5.1f} MB", end="", flush=True)

def download_postgres() -> None:
    if PG_BIN.exists():
        return
    print()
    info("PostgreSQL Portable bulunamadi — indiriliyor")
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(PG_DOWNLOAD_URL, PG_ZIP, _download_progress)
    print()
    ok("Indirme tamamlandi")
    info("Arsiv cikariliyor...")
    with zipfile.ZipFile(PG_ZIP, "r") as zf:
        zf.extractall(TOOLS_DIR)
    PG_ZIP.unlink(missing_ok=True)
    ok("PostgreSQL hazir")

def init_database() -> None:
    if PG_DATA.exists():
        return
    info("Veritabani dizini olusturuluyor (ilk kurulum)...")
    result = run([
        str(INITDB),
        "-D", str(PG_DATA),
        "-U", PG_USER,
        "--auth=trust",
        "--locale=C",
        "-E", "UTF8",
    ], capture_output=True, text=True)

    if not PG_DATA.exists() or result.returncode != 0:
        err("initdb basarisiz!")
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        sys.exit(1)
    ok("Veritabani dizini hazir")

def start_postgres() -> None:
    info("PostgreSQL baslatiliyor...")
    run([
        str(PG_CTL),
        "-D", str(PG_DATA),
        "-l", str(PG_LOG),
        "-o", f"-p {PG_PORT} -F",
        "start",
    ])

def wait_for_postgres(timeout: float = 15.0) -> None:
    info("PostgreSQL'in hazir olmasi bekleniyor...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            import socket
            with socket.create_connection(("127.0.0.1", PG_PORT), timeout=1.0):
                res = psql("-c", "SELECT 1")
                if res.returncode == 0:
                    ok("PostgreSQL hazir ve baglantilari kabul ediyor.")
                    return
        except Exception:
            pass
        time.sleep(0.5)
    warn("PostgreSQL hazir olma zaman asimina ugradi, yine de devam ediliyor...")

def stop_postgres() -> None:
    run_silent([str(PG_CTL), "-D", str(PG_DATA), "stop"])

def setup_db_and_user() -> None:
    info("Veritabani ve kullanici yapilandiriliyor...")
    psql("-c", f"ALTER USER {PG_USER} WITH PASSWORD '{PG_PASS}'")

    check_sql = (
        f"SELECT 'CREATE DATABASE {PG_DB}' "
        f"WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{PG_DB}')"
    )
    select_proc = subprocess.Popen(
        [str(PSQL), "-U", PG_USER, "-p", str(PG_PORT), "-d", "postgres",
         "-t", "--no-psqlrc", "-c", check_sql],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    exec_proc = subprocess.Popen(
        [str(PSQL), "-U", PG_USER, "-p", str(PG_PORT), "-d", "postgres"],
        stdin=select_proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    select_proc.stdout.close()
    exec_proc.wait()
    ok(f"Veritabani hazir ({PG_DB})")


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Dashboard Build (Next.js → static)
# ─────────────────────────────────────────────────────────────────────────────

def build_dashboard(router_port: str) -> None:
    if not (DASHBOARD / "node_modules").exists():
        warn("node_modules bulunamadi — npm install yapiliyor...")
        run(["npm", "install"], cwd=DASHBOARD, shell=True)

    info("Dashboard production build yapiliyor (npm run build)...")
    env = {**os.environ, "NEXT_PUBLIC_ROUTER_PORT": router_port}
    result = run(
        ["npm", "run", "build"],
        cwd=DASHBOARD,
        shell=True,
        env=env,
    )
    if result.returncode != 0:
        err("Dashboard build basarisiz!")
        sys.exit(1)
    ok("Dashboard build tamamlandi")


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Environment Variables
# ─────────────────────────────────────────────────────────────────────────────

def set_env(router_port: str) -> None:
    os.environ["POSTGRES_HOST"]           = "127.0.0.1"
    os.environ["POSTGRES_PORT"]           = str(PG_PORT)
    os.environ["POSTGRES_DB"]             = PG_DB
    os.environ["POSTGRES_USER"]           = PG_USER
    os.environ["POSTGRES_PASSWORD"]       = PG_PASS
    os.environ["BACKEND_URL"]             = f"http://127.0.0.1:{router_port}"
    os.environ["NEXT_PUBLIC_ROUTER_PORT"] = router_port
    os.environ["UVICORN_RELOAD"]          = "0"
    os.environ["ROUTER_PORT"]             = router_port
    os.environ["ROUTER_HOST"]             = "0.0.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Launch FastAPI (Dashboard statik olarak FastAPI uzerinden servis edilir)
# ─────────────────────────────────────────────────────────────────────────────

def launch(router_port: str) -> list[tuple[str, subprocess.Popen]]:
    procs = []

    backend = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
    )
    procs.append(("FastAPI", backend))

    return procs


# ─────────────────────────────────────────────────────────────────────────────
# Shutdown
# ─────────────────────────────────────────────────────────────────────────────

def shutdown(procs: list) -> None:
    print(f"\n{RED}✘  Durdurma sinyali alindi — kapatiliyor...{RESET}", flush=True)
    for name, proc in procs:
        try:
            run_silent(["taskkill", "/f", "/t", "/pid", str(proc.pid)])
            dim(f"    {name} kapatildi (PID {proc.pid})")
        except Exception:
            pass
    info("PostgreSQL durduruluyor...")
    stop_postgres()
    ok("Tum servisler kapatildi.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def banner() -> None:
    line = "═" * 55
    print(f"\n{CYAN}{BOLD}╔{line}╗{RESET}")
    print(f"{CYAN}{BOLD}║{'Orion Router — Production Environment':^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")




def main() -> None:
    banner()

    info("Sistem kontrolleri yapiliyor...")
    check_npm()
    check_python_deps()
    print()

    run_silent([sys.executable, "-c", "import core.config"])
    router_port = read_env("ROUTER_PORT", "20128")

    free_ports(router_port)
    print()

    download_postgres()
    init_database()
    start_postgres()
    wait_for_postgres()
    setup_db_and_user()
    print()

    build_dashboard(router_port)
    print()

    set_env(router_port)
    procs = launch(router_port)

    try:
        while True:
            alive = [p for _, p in procs if p.poll() is None]
            if not alive:
                warn("Servis beklenmedik sekilde kapandi.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)


if __name__ == "__main__":
    main()
