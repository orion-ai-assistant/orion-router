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
import time
import subprocess
import urllib.request
import zipfile
import threading
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Terminal Colors (ANSI — Windows 10+ destekler)
# ─────────────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("")  # enable ANSI escape codes on Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

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
ROOT      = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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
LOCK_FILE_HANDLE = None

def acquire_lock() -> bool:
    global LOCK_FILE_HANDLE
    lock_path = ROOT / ".orion.dev.lock"
    
    try:
        LOCK_FILE_HANDLE = open(lock_path, "w")
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(LOCK_FILE_HANDLE.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(LOCK_FILE_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
        LOCK_FILE_HANDLE.write(str(os.getpid()))
        LOCK_FILE_HANDLE.flush()
        return True
    except (OSError, IOError):
        if LOCK_FILE_HANDLE:
            try:
                LOCK_FILE_HANDLE.close()
            except Exception:
                pass
            LOCK_FILE_HANDLE = None
        return False

def release_lock() -> None:
    global LOCK_FILE_HANDLE
    if LOCK_FILE_HANDLE:
        try:
            LOCK_FILE_HANDLE.close()
            (ROOT / ".orion.dev.lock").unlink(missing_ok=True)
        except Exception:
            pass
        finally:
            LOCK_FILE_HANDLE = None


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)

def run_silent(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    return run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)

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
    import shutil
    import time
    if shutil.which("docker"):
        try:
            cmd = ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.ID}}"]
            res = run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                container_ids = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                if container_ids:
                    for cid in container_ids:
                        dim(f"    Port {port} Docker tarafindan kullaniliyor. Konteyner ({cid}) durduruluyor...")
                        run_silent(["docker", "stop", cid], timeout=15)
                    time.sleep(1.5)
        except Exception:
            pass

    killed_any = False
    try:
        result = run(
            ["netstat", "-aon"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid != "0":
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(f"    Port {port} → PID {pid} kapatildi")
                    killed_any = True
    except Exception:
        pass

    if killed_any:
        time.sleep(2.0)

def kill_portable_postgres() -> None:
    """Sadece bu ortama ait (PG_DATA) postgres sureclerini temizler."""
    pid_file = PG_DATA / "postmaster.pid"

    if PG_DATA.exists() and PG_CTL.exists():
        run_silent([str(PG_CTL), "-D", str(PG_DATA), "-m", "fast", "stop"])

    killed_any = False
    if pid_file.exists():
        try:
            lines = pid_file.read_text().splitlines()
            if lines and lines[0].isdigit():
                pid = lines[0]
                check = run_silent(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"])
                if check.returncode == 0:
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(f"    Eski PostgreSQL sureci (PID {pid}) zorla kapatildi")
                    killed_any = True
        except Exception:
            pass

    if killed_any:
        time.sleep(2.0)
    else:
        time.sleep(1.0)

    for file_name in ["postmaster.pid", "postmaster.opts"]:
        try:
            (PG_DATA / file_name).unlink(missing_ok=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Free Ports
# ─────────────────────────────────────────────────────────────────────────────

def free_ports(router_port: str) -> None:
    info(f"Portlar temizleniyor: {UI_PORT}, {router_port}, {PG_PORT}...")
    kill_portable_postgres()
    for port in [UI_PORT, int(router_port), PG_PORT]:
        kill_port(port)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — PostgreSQL Portable
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

    def _cleanup_stale_locks() -> None:
        for file_name in ["postmaster.pid", "postmaster.opts"]:
            try:
                (PG_DATA / file_name).unlink(missing_ok=True)
            except Exception:
                pass

    for attempt in range(1, 4):
        _cleanup_stale_locks()

        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                if PG_LOG.exists():
                    PG_LOG.unlink()
                break
            except OSError:
                time.sleep(0.4)
        else:
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            PG_LOG_ALT = PG_DATA / f"pg_{ts}.log"
            warn(f"    pg.log serbest birakilamadi, alternatif kullaniliyor: {PG_LOG_ALT.name}")
            result = run([
                str(PG_CTL),
                "-D", str(PG_DATA),
                "-l", str(PG_LOG_ALT),
                "-o", f"-p {PG_PORT} -F",
                "start",
            ])
            if result.returncode == 0:
                return
            time.sleep(2.0)
            kill_portable_postgres()
            continue

        try:
            PG_LOG.parent.mkdir(parents=True, exist_ok=True)
            PG_LOG.touch()
        except Exception:
            pass

        result = run([
            str(PG_CTL),
            "-D", str(PG_DATA),
            "-l", str(PG_LOG),
            "-o", f"-p {PG_PORT} -F",
            "start",
        ])
        if result.returncode == 0:
            return

        time.sleep(2.0)
        kill_portable_postgres()

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
# Step 3 — Environment Variables
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
    os.environ["ROUTER_HOST"]             = "0.0.0.0"
    os.environ["ORION_NO_BANNER"]         = "1"


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Launch Services
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
        ["npm", "run", "dev", "--", "-p", str(UI_PORT), "-H", "0.0.0.0"],
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

def print_active_services_banner(router_port: str) -> None:
    import socket
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    BLUE = "\033[94m"

    local_ip = get_local_ip()
    dashboard_url = f"http://localhost:{UI_PORT}"
    local_url = f"http://{local_ip}:{UI_PORT}"
    border_line = f"{GRAY}────────────────────────────────────────────────{RESET}"
    title_colored = f"{BLUE}{BOLD}ORION ROUTER{RESET}"
    dash_colored  = f"{BLUE}➜{RESET}  {BOLD}Dashboard:{RESET}   {CYAN}{dashboard_url}{RESET}"
    ip_colored    = f"{BLUE}➜{RESET}  {BOLD}Yerel Ağ:{RESET}    {CYAN}{local_url}{RESET}"
    
    print()
    print(border_line)
    print(title_colored)
    print()
    print(dash_colored)
    print(ip_colored)
    print(border_line)
    print(f"{GRAY}Durdurmak için CTRL+C tuşlarına basın{RESET}")
    print()


def main() -> None:
    if not acquire_lock():
        err("Hata: Baska bir Orion Router instancesi calisiyor (Portlar kullanimda olabilir).")
        sys.exit(1)

    banner()

    run_silent([sys.executable, "-c", "import core.config"], cwd=ROOT)
    router_port = read_env("ROUTER_DEV_PORT", "20129")

    free_ports(router_port)
    print()

    download_postgres()
    init_database()
    start_postgres()
    wait_for_postgres()
    setup_db_and_user()
    print()

    set_env(router_port)
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
                print_active_services_banner(port)
                return
            time.sleep(0.5)

    t = threading.Thread(target=wait_for_server_and_print_banner, args=[router_port])
    t.daemon = True
    t.start()

    try:
        while True:
            alive = [p for _, p in procs if p.poll() is None]
            if len(alive) < len(procs):
                dead_names = [name for name, p in procs if p.poll() is not None]
                warn(f"Servislerden biri beklenmedik sekilde kapandi: {', '.join(dead_names)}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)
        release_lock()


if __name__ == "__main__":
    main()