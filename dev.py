#!/usr/bin/env python3
"""
dev.py — Orion Router | Development Environment
================================================
PostgreSQL (portable) + FastAPI (hot-reload) + Next.js (hot-reload)

Kullanim:
    python dev.py
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
# Terminal Colors (ANSI — Windows 10+ destekler)
# ─────────────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("")  # enable ANSI escape codes on Windows

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
PG_DATA   = ROOT / ".pgdata-dev"
PG_LOG    = PG_DATA / "pg.log"
DASHBOARD = ROOT / "dashboard"

PG_PORT   = 5444
PG_USER   = "router_user_dev"
PG_PASS   = "router_pass_dev"
PG_DB     = "orion_router_dev"
UI_PORT   = 3001

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
    """Run a psql command against the dev database server."""
    base = [str(PSQL), "-U", PG_USER, "-p", str(PG_PORT), "-d", "postgres"]
    return run_silent(base + list(args))

def read_env(key: str, default: str) -> str:
    """Read a key from the .env file (ignores commented lines)."""
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
    """Kill any process listening on the given port."""
    try:
        result = run(
            ["netstat", "-aon"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid != "0":
                    run_silent(["taskkill", "/f", "/pid", pid])
                    dim(f"    Port {port} → PID {pid} kapatildi")
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
    info(f"Portlar temizleniyor: {UI_PORT}, {router_port}, {PG_PORT}...")
    for port in [UI_PORT, int(router_port), PG_PORT]:
        kill_port(port)


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
    print()  # newline after progress bar
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
        "-o", f"-p {PG_PORT}",
        "start",
    ])

def stop_postgres() -> None:
    run_silent([str(PG_CTL), "-D", str(PG_DATA), "stop"])

def setup_db_and_user() -> None:
    info("Veritabani ve kullanici yapilandiriliyor...")

    # Set password
    psql("-c", f"ALTER USER {PG_USER} WITH PASSWORD '{PG_PASS}'")

    # Create database only if it doesn't exist (pipe trick — reliable in Python)
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
# Step 4 — npm install
# ─────────────────────────────────────────────────────────────────────────────

def ensure_node_modules() -> None:
    if not (DASHBOARD / "node_modules").exists():
        warn("node_modules bulunamadi — npm install yapiliyor (sadece bir kez)...")
        run(["npm", "install"], cwd=DASHBOARD, shell=True)
        ok("node_modules hazir")


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
    os.environ["UVICORN_RELOAD"]          = "1"
    os.environ["ROUTER_PORT"]             = router_port


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Launch Services
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
    frontend = subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(UI_PORT)],
        cwd=DASHBOARD,
        shell=True,
    )
    procs.append(("Next.js", frontend))

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
    print(f"{CYAN}{BOLD}║{'Orion Router — Development Environment':^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")




def main() -> None:
    banner()

    # ── Checks ──────────────────────────────────
    info("Sistem kontrolleri yapiliyor...")
    check_npm()
    check_python_deps()
    print()

    # ── Read config ─────────────────────────────
    # Trigger .env auto-copy if missing
    run_silent([sys.executable, "-c", "import core.config"])
    router_port = read_env("ROUTER_DEV_PORT", "20129")

    # ── Free ports ──────────────────────────────
    free_ports(router_port)
    print()

    # ── PostgreSQL ──────────────────────────────
    download_postgres()
    init_database()
    start_postgres()
    setup_db_and_user()
    print()

    # ── Node.js ─────────────────────────────────
    ensure_node_modules()
    print()

    # ── Launch ──────────────────────────────────
    set_env(router_port)
    procs = launch(router_port)

    # ── Wait ────────────────────────────────────
    try:
        while True:
            alive = [p for _, p in procs if p.poll() is None]
            if not alive:
                warn("Tum servisler beklenmedik sekilde kapandi.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)


if __name__ == "__main__":
    main()
