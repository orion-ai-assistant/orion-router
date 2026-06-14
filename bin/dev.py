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
    os.system("")
    os.environ["PYTHONUTF8"] = "1"

    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
            line_buffering=True
        )

        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
            line_buffering=True
        )
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
from bin.i18n import t
from core.lifespan import print_active_services_banner
from bin.pg_integrity import generate_manifest, verify_manifest
from bin.npm_integrity import npm_needs_install, record_npm_install
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
                        dim(t("docker_cleaning_port", port=port, cid=cid))
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
                    dim(t("port_killed", port=port, pid=pid))
                    killed_any = True
    except Exception:
        pass

    if killed_any:
        time.sleep(2.0)

def kill_portable_postgres() -> None:
    """Sadece bu ortama ait (PG_DATA) postgres sureclerini temizler."""
    pid_file = PG_DATA / "postmaster.pid"

    if PG_DATA.exists() and PG_CTL.exists():
        run_silent([str(PG_CTL), "-D", str(PG_DATA), "-t", "5", "-m", "fast", "stop"])

    killed_any = False
    if pid_file.exists():
        try:
            lines = pid_file.read_text().splitlines()
            if lines and lines[0].isdigit():
                pid = lines[0]
                check = run_silent(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"])
                if check.returncode == 0:
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(t("old_pg_killed", pid=pid, name="dev"))
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
    info(t("cleaning_ports", ports=f"{UI_PORT}, {router_port}, {PG_PORT}"))
    kill_portable_postgres()
    for port in [UI_PORT, int(router_port), PG_PORT]:
        kill_port(port)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — PostgreSQL Portable
# ─────────────────────────────────────────────────────────────────────────────

def _download_progress(block_num: int, block_size: int, total: int) -> None:
    if not hasattr(_download_progress, "last_pct"):
        _download_progress.last_pct = -1

    done = min(block_num * block_size, total)
    if total <= 0: return
    pct  = int(done * 100 / total)
    mb   = done / 1_048_576
    bar  = "█" * (pct // 5) + "░" * (20 - pct // 5)

    if sys.stdout.isatty():
        print(f"\r    [{bar}] {pct:3d}%  {mb:5.1f} MB", end="", flush=True)
    else:
        # Log dosyasina yaziliyorsa asiri log sismesini engellemek icin her %10'da bir yazdir
        if pct % 10 == 0 and pct != _download_progress.last_pct:
            _download_progress.last_pct = pct
            print(f"    [{bar}] {pct:3d}%  {mb:5.1f} MB", flush=True)

def download_postgres() -> None:
    if verify_manifest(TOOLS_DIR):
        return

    print()
    info(t("pg_not_found_downloading"))
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(PG_DOWNLOAD_URL, PG_ZIP, _download_progress)
    print()
    ok(t("download_complete"))

    info(t("extracting_archive"))
    with zipfile.ZipFile(PG_ZIP, "r") as zf:
        namelist = zf.namelist()
        total_files = len(namelist)
        last_pct = -1
        for i, member in enumerate(namelist, 1):
            zf.extract(member, TOOLS_DIR)
            pct = int(i * 100 / total_files)
            if pct != last_pct:
                last_pct = pct
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                if sys.stdout.isatty():
                    print(f"\r    [{bar}] {pct:3d}%  ({i}/{total_files} files)", end="", flush=True)
                else:
                    if pct % 10 == 0:
                        print(f"    [{bar}] {pct:3d}%  ({i}/{total_files} files)", flush=True)
        if sys.stdout.isatty():
            print()
    PG_ZIP.unlink(missing_ok=True)
    generate_manifest(TOOLS_DIR, "postgresql-16.3-1-windows-x64-binaries")
    ok(t("pg_ready"))

def init_database() -> None:
    if PG_DATA.exists():
        return

    info(t("db_dir_creating"))
    result = run([
        str(INITDB),
        "-D", str(PG_DATA),
        "-U", PG_USER,
        "--auth=trust",
        "--locale=C",
        "-E", "UTF8",
    ], capture_output=True, text=True)

    if not PG_DATA.exists() or result.returncode != 0:
        err(t("initdb_failed"))
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        sys.exit(1)

    ok(t("db_dir_ready"))

def start_postgres() -> None:
    info(t("starting_pg"))

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
            warn(t("pg_log_lock_warning", name=PG_LOG_ALT.name))
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

def print_pg_log_errors() -> None:
    if PG_LOG.exists():
        try:
            log_content = PG_LOG.read_text(encoding="utf-8", errors="replace")
            print(f"\n{RED}=== PostgreSQL Log (pg.log) ==={RESET}")
            lines = log_content.splitlines()[-20:]
            for line in lines:
                print(f"  {line}")
            print(f"{RED}================================{RESET}\n")
        except Exception as e:
            dim(f"Could not read pg.log: {e}")

def wait_for_postgres(timeout: float = 15.0) -> None:
    info(t("waiting_for_pg"))
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            import socket
            with socket.create_connection(("127.0.0.1", PG_PORT), timeout=1.0):
                res = psql("-c", "SELECT 1")
                if res.returncode == 0:
                    ok(t("pg_accepting_conns"))
                    return
        except Exception:
            pass
        time.sleep(0.5)
    err(t("pg_timeout_warning"))
    print_pg_log_errors()
    sys.exit(1)

def stop_postgres() -> None:
    run_silent([str(PG_CTL), "-D", str(PG_DATA), "-t", "5", "stop"])

def setup_db_and_user() -> None:
    info(t("configuring_db_user"))

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

    ok(t("db_ready", db=PG_DB))


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
    if npm_needs_install(DASHBOARD):
        dim("Installing dashboard dependencies...")
        result_npm = run(["npm", "install"], cwd=DASHBOARD, shell=True)
        if result_npm.returncode != 0:
            err("Failed to install dashboard dependencies")
            sys.exit(1)
        record_npm_install(DASHBOARD)

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
    print(f"\n{RED}✘  {t('shutdown_received')}{RESET}", flush=True)

    for name, proc in procs:
        try:
            run_silent(["taskkill", "/f", "/t", "/pid", str(proc.pid)])
            dim(t("service_closed", name=name, pid=proc.pid))
        except Exception:
            pass

    info(t("stopping_pg_label", label="PostgreSQL"))
    stop_postgres()
    ok(t("all_services_shutdown"))


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def banner() -> None:
    line = "═" * 55
    print(f"\n{CYAN}{BOLD}╔{line}╗{RESET}")
    print(f"{CYAN}{BOLD}║{t('dev_title'):^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def main() -> None:
    if not acquire_lock():
        err(t("err_lock_fail"))
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
                print_active_services_banner(port, dashboard_port=str(UI_PORT))
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
                warn(t("service_crashed_multi", names=', '.join(dead_names)))
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)
        release_lock()


if __name__ == "__main__":
    main()
