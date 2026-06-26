import os
import sys
import time
import subprocess
import urllib.request
import zipfile
from pathlib import Path

# Initialize Terminal Encoding/ANSI Support
if sys.platform == "win32":
    os.system("chcp 65001 >nul")
    os.environ["PYTHONUTF8"] = "1"
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

# Terminal Colors
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

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.i18n import t
from bin.pg_integrity import generate_manifest, verify_manifest

DEFAULT_TIMEOUT = 10.0
TOOLS_DIR = ROOT / "tools"
PG_BIN    = TOOLS_DIR / "pgsql" / "bin"
DASHBOARD = ROOT / "dashboard"

def find_postgres_binaries():
    import shutil
    # 1. Check if they are in the PATH
    initdb_path = shutil.which("initdb")
    pg_ctl_path = shutil.which("pg_ctl")
    psql_path = shutil.which("psql")
    
    if initdb_path and pg_ctl_path and psql_path:
        return Path(initdb_path), Path(pg_ctl_path), Path(psql_path)
        
    # 2. Check standard Homebrew locations on Apple Silicon / Intel Mac
    brew_candidates = [
        Path("/opt/homebrew/opt/postgresql@16/bin"),
        Path("/opt/homebrew/opt/postgresql@15/bin"),
        Path("/opt/homebrew/opt/postgresql@14/bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/local/opt/postgresql@16/bin"),
        Path("/usr/local/bin"),
    ]
    for base in brew_candidates:
        i = base / "initdb"
        c = base / "pg_ctl"
        p = base / "psql"
        if i.is_file() and c.is_file() and p.is_file():
            return i, c, p
            
    # 3. Check PostgresApp locations
    app_versions = ["16", "15", "14", "13"]
    for v in app_versions:
        base = Path(f"/Applications/Postgres.app/Contents/Versions/{v}/bin")
        i = base / "initdb"
        c = base / "pg_ctl"
        p = base / "psql"
        if i.is_file() and c.is_file() and p.is_file():
            return i, c, p
            
    return None

if sys.platform == "win32":
    INITDB  = PG_BIN / "initdb.exe"
    PG_CTL  = PG_BIN / "pg_ctl.exe"
    PSQL    = PG_BIN / "psql.exe"
else:
    pg_bins = find_postgres_binaries()
    if pg_bins:
        INITDB, PG_CTL, PSQL = pg_bins
    else:
        INITDB  = Path("initdb")
        PG_CTL  = Path("pg_ctl")
        PSQL    = Path("psql")

PG_DOWNLOAD_URL = (
    "https://get.enterprisedb.com/postgresql/"
    "postgresql-16.3-1-windows-x64-binaries.zip"
)
PG_ZIP = TOOLS_DIR / "postgresql.zip"

LOCK_FILE_HANDLE = None

def acquire_lock(lock_name: str) -> bool:
    global LOCK_FILE_HANDLE
    lock_path = ROOT / lock_name
    
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

def release_lock(lock_name: str) -> None:
    global LOCK_FILE_HANDLE
    if LOCK_FILE_HANDLE:
        try:
            LOCK_FILE_HANDLE.close()
            (ROOT / lock_name).unlink(missing_ok=True)
        except Exception:
            pass
        finally:
            LOCK_FILE_HANDLE = None

def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        stdout = "" if kwargs.get("text") or kwargs.get("universal_newlines") else b""
        return subprocess.CompletedProcess(cmd, 1, stdout=stdout, stderr=stdout)
    except FileNotFoundError:
        stdout = "" if kwargs.get("text") or kwargs.get("universal_newlines") else b""
        return subprocess.CompletedProcess(cmd, 127, stdout=stdout, stderr=stdout)

def run_silent(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    if "timeout" not in kwargs:
        kwargs["timeout"] = DEFAULT_TIMEOUT
    return run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)

def psql(query_args: list, pg_user: str, pg_port: int) -> subprocess.CompletedProcess:
    base = [str(PSQL), "-U", pg_user, "-p", str(pg_port), "-d", "postgres"]
    return run_silent(base + query_args)

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

def kill_port(port: int) -> bool:
    import shutil
    import time
    killed_any = False
    
    if shutil.which("docker"):
        try:
            cmd = ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.ID}}"]
            res = run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                container_ids = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                if container_ids:
                    for cid in container_ids:
                        dim(t("docker_cleaning_port", port=port, cid=cid))
                        run_silent(["docker", "stop", cid], timeout=DEFAULT_TIMEOUT)
                        killed_any = True
                    time.sleep(1.5)
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            result = run(
                ["netstat", "-aon"],
                capture_output=True, text=True, timeout=DEFAULT_TIMEOUT
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
    else:
        try:
            res = run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                pids = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                for pid in pids:
                    if pid.isdigit():
                        run_silent(["kill", "-9", pid])
                        dim(t("port_killed", port=port, pid=pid))
                        killed_any = True
        except Exception:
            pass

    if killed_any:
        time.sleep(2.0)
    return killed_any

def kill_portable_postgres(data_dir: Path, label: str) -> bool:
    pid_file = data_dir / "postmaster.pid"

    if data_dir.exists() and PG_CTL.exists():
        run_silent([str(PG_CTL), "-D", str(data_dir), "-t", "5", "-m", "fast", "stop"])

    killed_any = False
    if pid_file.exists():
        try:
            lines = pid_file.read_text().splitlines()
            if lines and lines[0].isdigit():
                pid = lines[0]
                check = run_silent(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"])
                if check.returncode == 0:
                    run_silent(["taskkill", "/f", "/t", "/pid", pid])
                    dim(t("old_pg_killed", pid=pid, name=label))
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
        except Exception:
            pass
    return killed_any

def kill_all_postgres() -> bool:
    import sys
    import time
    killed_any = False
    if sys.platform == "win32":
        try:
            result = run(
                ["tasklist", "/fi", "imagename eq postgres.exe"],
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT
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
            res = run(["pgrep", "-f", "postgres"], capture_output=True, text=True)
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
                    try:
                        res = run(["pgrep", "-P", pid], capture_output=True, text=True, timeout=5)
                    except Exception:
                        res = subprocess.CompletedProcess(["pgrep"], 1, stdout="", stderr="")
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

def free_ports(ports: list[int], pg_data: Path, pg_label: str) -> None:
    ports_str = ", ".join(map(str, ports))
    info(t("cleaning_ports", ports=ports_str))
    kill_portable_postgres(pg_data, pg_label)
    for port in ports:
        kill_port(port)

def download_postgres() -> None:
    if (TOOLS_DIR / "pgsql.ready").is_file():
        return

    if sys.platform != "win32":
        pg_bins = find_postgres_binaries()
        if pg_bins:
            TOOLS_DIR.mkdir(parents=True, exist_ok=True)
            (TOOLS_DIR / "pgsql.ready").touch()
            ok(t("pg_ready") + " (System PostgreSQL)")
            return
        else:
            if sys.platform == "darwin":
                import shutil
                if shutil.which("brew"):
                    info("PostgreSQL not found. Installing automatically via Homebrew...")
                    res = run(["brew", "install", "postgresql@16"])
                    if res.returncode == 0:
                        run(["brew", "link", "postgresql@16", "--force"])
                        pg_bins = find_postgres_binaries()
                        if pg_bins:
                            TOOLS_DIR.mkdir(parents=True, exist_ok=True)
                            (TOOLS_DIR / "pgsql.ready").touch()
                            ok(t("pg_ready") + " (Homebrew PostgreSQL)")
                            return
            err("PostgreSQL binaries (initdb, pg_ctl, psql) not found!")
            err("Please install PostgreSQL (e.g. using: brew install postgresql@16) and make sure it is in your PATH.")
            sys.exit(1)

    import shutil
    shutil.rmtree(TOOLS_DIR / "pgsql", ignore_errors=True)
    (TOOLS_DIR / "pgsql.manifest").unlink(missing_ok=True)

    print()
    info(t("pg_not_found_downloading"))
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    
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
            if pct % 10 == 0 and pct != _download_progress.last_pct:
                _download_progress.last_pct = pct
                print(f"    [{bar}] {pct:3d}%  {mb:5.1f} MB", flush=True)

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

def init_database(pg_data: Path, pg_user: str, _repair_attempted: bool = False) -> None:
    if pg_data.exists():
        return

    info(t("db_dir_creating"))
    result = run([
        str(INITDB),
        "-D", str(pg_data),
        "-U", pg_user,
        "--auth=trust",
        "--locale=C",
        "-E", "UTF8",
    ], capture_output=True, text=True)

    if not pg_data.exists() or result.returncode != 0:
        err(t("initdb_failed"))
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        
        if not _repair_attempted:
            warn(t("pg_checking_integrity"))
            if not verify_manifest(TOOLS_DIR):
                err(t("pg_corrupted_rebuilding"))
                import shutil
                shutil.rmtree(TOOLS_DIR / "pgsql", ignore_errors=True)
                (TOOLS_DIR / "pgsql.manifest").unlink(missing_ok=True)
                (TOOLS_DIR / "pgsql.ready").unlink(missing_ok=True)
                download_postgres()
                init_database(pg_data, pg_user, _repair_attempted=True)
                return

        sys.exit(1)

    ok(t("db_dir_ready"))

def start_postgres(pg_data: Path, pg_port: int, pg_log: Path, label: str) -> None:
    info(t("starting_pg"))

    def _cleanup_stale_locks() -> None:
        for file_name in ["postmaster.pid", "postmaster.opts"]:
            try:
                (pg_data / file_name).unlink(missing_ok=True)
            except Exception:
                pass

    for attempt in range(1, 4):
        _cleanup_stale_locks()

        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                if pg_log.exists():
                    pg_log.unlink()
                break
            except OSError:
                time.sleep(0.4)
        else:
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            pg_log_alt = pg_data / f"pg_{ts}.log"
            warn(t("pg_log_lock_warning", name=pg_log_alt.name))
            result = run([
                str(PG_CTL),
                "-D", str(pg_data),
                "-l", str(pg_log_alt),
                "-o", f"-p {pg_port} -F",
                "start",
            ])
            if result.returncode == 0:
                return
            time.sleep(2.0)
            kill_portable_postgres(pg_data, label)
            continue

        try:
            pg_log.parent.mkdir(parents=True, exist_ok=True)
            pg_log.touch()
        except Exception:
            pass

        result = run([
            str(PG_CTL),
            "-D", str(pg_data),
            "-l", str(pg_log),
            "-o", f"-p {pg_port} -F",
            "start",
        ])
        if result.returncode == 0:
            return

        time.sleep(2.0)
        kill_portable_postgres(pg_data, label)

def print_pg_log_errors(pg_log: Path) -> None:
    if pg_log.exists():
        try:
            log_content = pg_log.read_text(encoding="utf-8", errors="replace")
            print(f"\n{RED}=== PostgreSQL Log (pg.log) ==={RESET}")
            lines = log_content.splitlines()[-20:]
            for line in lines:
                print(f"  {line}")
            print(f"{RED}================================{RESET}\n")
        except Exception as e:
            dim(f"Could not read pg.log: {e}")

def wait_for_postgres(pg_data: Path, pg_port: int, pg_log: Path, pg_user: str, label: str, timeout: float = DEFAULT_TIMEOUT) -> None:
    info(t("waiting_for_pg"))
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            import socket
            with socket.create_connection(("127.0.0.1", pg_port), timeout=1.0):
                res = psql(["-c", "SELECT 1"], pg_user, pg_port)
                if res.returncode == 0:
                    ok(t("pg_accepting_conns"))
                    return
        except Exception:
            pass
        time.sleep(0.5)
    err(t("pg_timeout_warning"))
    print_pg_log_errors(pg_log)
    
    warn(t("pg_failed_checking_integrity"))
    if not verify_manifest(TOOLS_DIR):
        err(t("pg_corrupted_rebuilding"))
        import shutil
        stop_postgres(pg_data)
        shutil.rmtree(TOOLS_DIR / "pgsql", ignore_errors=True)
        (TOOLS_DIR / "pgsql.manifest").unlink(missing_ok=True)
        (TOOLS_DIR / "pgsql.ready").unlink(missing_ok=True)
        download_postgres()
        start_postgres(pg_data, pg_port, pg_log, label)
        _wait_for_postgres_once(pg_port, pg_user, pg_log, timeout)
        return
        
    sys.exit(1)

def _wait_for_postgres_once(pg_port: int, pg_user: str, pg_log: Path, timeout: float) -> None:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            import socket
            with socket.create_connection(("127.0.0.1", pg_port), timeout=1.0):
                res = psql(["-c", "SELECT 1"], pg_user, pg_port)
                if res.returncode == 0:
                    ok(t("pg_accepting_conns"))
                    return
        except Exception:
            pass
        time.sleep(0.5)
    err(t("pg_timeout_warning"))
    print_pg_log_errors(pg_log)
    sys.exit(1)

def stop_postgres(pg_data: Path) -> None:
    run_silent([str(PG_CTL), "-D", str(pg_data), "-t", "5", "stop"])

def setup_db_and_user(pg_user: str, pg_pass: str, pg_port: int, pg_db: str) -> None:
    info(t("configuring_db_user"))

    psql(["-c", f"ALTER USER {pg_user} WITH PASSWORD '{pg_pass}'"], pg_user, pg_port)

    check_sql = (
        f"SELECT 'CREATE DATABASE {pg_db}' "
        f"WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{pg_db}')"
    )
    select_proc = subprocess.Popen(
        [str(PSQL), "-U", pg_user, "-p", str(pg_port), "-d", "postgres",
         "-t", "--no-psqlrc", "-c", check_sql],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    exec_proc = subprocess.Popen(
        [str(PSQL), "-U", pg_user, "-p", str(pg_port), "-d", "postgres"],
        stdin=select_proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    select_proc.stdout.close()
    exec_proc.wait()

    ok(t("db_ready", db=pg_db))

def set_env(router_port: str, pg_port: int, pg_db: str, pg_user: str, pg_pass: str, uvicorn_reload: str) -> None:
    os.environ["POSTGRES_HOST"]           = "127.0.0.1"
    os.environ["POSTGRES_PORT"]           = str(pg_port)
    os.environ["POSTGRES_DB"]             = pg_db
    os.environ["POSTGRES_USER"]           = pg_user
    os.environ["POSTGRES_PASSWORD"]       = pg_pass
    os.environ["BACKEND_URL"]             = f"http://127.0.0.1:{router_port}"
    os.environ["NEXT_PUBLIC_ROUTER_PORT"] = router_port
    os.environ["UVICORN_RELOAD"]          = uvicorn_reload
    os.environ["ROUTER_PORT"]             = router_port
    os.environ["ROUTER_HOST"]             = "0.0.0.0"
    os.environ["ORION_NO_BANNER"]         = "1"
