import os
import json
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
from core.runtime_layout import data_root
from bin.pg_integrity import generate_manifest, verify_manifest

DEFAULT_TIMEOUT = 10.0
TOOLS_DIR = ROOT / "tools"
PG_BIN    = TOOLS_DIR / "pgsql" / "bin"
DASHBOARD = ROOT / "dashboard"
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Orion" / "cache"

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

from core.windows_postgres import ARCHIVE_NAME, ARCHIVE_URL, VERSION, provision_runtime, verify_unicode_runtime

PG_DOWNLOAD_URL = ARCHIVE_URL
PG_ZIP = CACHE_DIR / ARCHIVE_NAME

LOCK_FILE_HANDLE = None


def acquire_lock(lock_name: str) -> bool:
    from core.process_lifecycle import InstanceLock, LifecycleError
    global LOCK_FILE_HANDLE
    try:
        # Compatibility API for external callers; never truncate/delete old locks.
        LOCK_FILE_HANDLE = InstanceLock(ROOT / '.orion-lifecycle' / lock_name, 'instance', timeout=0)
        LOCK_FILE_HANDLE.__enter__()
        return True
    except LifecycleError:
        LOCK_FILE_HANDLE = None
        return False


def release_lock(lock_name: str) -> None:
    global LOCK_FILE_HANDLE
    if LOCK_FILE_HANDLE:
        LOCK_FILE_HANDLE.__exit__()
        LOCK_FILE_HANDLE = None


def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    if kwargs.get('text') or kwargs.get('universal_newlines'):
        kwargs.setdefault('errors', 'replace')  # Native Windows tools may emit the OEM codepage.
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

def postgres_is_ready(pg_data: Path, pg_port: int, pg_user: str) -> bool:
    """Check that the listener belongs to this data directory and answers queries."""
    if not PSQL.exists() or not is_port_open(pg_port):
        return False

    env = {**os.environ, "PGCONNECT_TIMEOUT": "2"}
    result = run(
        [str(PSQL), "-h", "127.0.0.1", "-U", pg_user, "-p", str(pg_port),
         "-d", "postgres", "-w", "-At", "-c", "SHOW data_directory"],
        timeout=3,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False

    try:
        actual_dir = Path(result.stdout.strip()).resolve()
        return os.path.normcase(str(actual_dir)) == os.path.normcase(str(pg_data.resolve()))
    except OSError:
        return False

def read_env(key: str, default: str) -> str:
    env_file = data_root(ROOT) / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    return default

def is_port_open(port: int) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def _windows_listening_pids(port: int) -> list[str]:
    """Return unique Windows PIDs listening on the exact local port."""
    if sys.platform != "win32":
        return []

    try:
        result = run(
            ["netstat", "-aon"],
            capture_output=True, text=True, timeout=DEFAULT_TIMEOUT
        )
    except Exception:
        return []

    pids = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
            continue
        if parts[1].rsplit(":", 1)[-1] != str(port):
            continue
        pid = parts[-1]
        if pid.isdigit() and pid != "0":
            pids.add(pid)
    return sorted(pids, key=int)

def _windows_orphan_postgres_children(parent_pid: str) -> list[str]:
    """Find only Orion PostgreSQL children whose vanished parent owned the port."""
    if sys.platform != "win32" or not parent_pid.isdigit():
        return []

    command = (
        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId = {parent_pid}' | "
        "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    )
    result = run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        records = json.loads(result.stdout)
    except (ValueError, TypeError):
        return []
    if isinstance(records, dict):
        records = [records]

    expected_exe = os.path.normcase(os.path.normpath(str(PG_BIN / "postgres.exe")))
    children = []
    for record in records:
        pid = str(record.get("ProcessId", ""))
        command_line = record.get("CommandLine") or ""
        exe = record.get("ExecutablePath") or ""
        if not exe and command_line.startswith('"'):
            exe = command_line.split('"', 2)[1]
        if (pid.isdigit() and "--fork" in command_line
                and os.path.normcase(os.path.normpath(exe)) == expected_exe):
            children.append(pid)
    return children

def kill_port(port: int, *args, **kwargs) -> bool:
    from core.process_lifecycle import assert_port_free
    assert_port_free(port)
    return False


def kill_portable_postgres(data_dir: Path, label: str, port=None) -> bool:
    # Retained API no longer kills by PID/port. Explicit stop has DB ordering.
    from core.process_lifecycle import LifecycleError
    raise LifecycleError('Implicit PostgreSQL cleanup disabled; use explicit owned stop')


_ORION_PG_PORTS = [int(read_env('POSTGRES_PORT', '5432')), int(read_env('POSTGRES_DEV_PORT', '5433'))]


def kill_postgres_on_ports(ports=None) -> bool:
    from core.process_lifecycle import assert_port_free
    for port in ports or _ORION_PG_PORTS:
        assert_port_free(port)
    return False


def kill_all_postgres() -> bool:
    return kill_postgres_on_ports()


def kill_orion_pid() -> bool:
    from core.process_lifecycle import LifecycleError
    raise LifecycleError('PID-only shutdown disabled; use cli.py stop')


def free_ports(ports: list[int], pg_data: Path, pg_label: str) -> None:
    from core.process_lifecycle import assert_port_free
    for port in ports:
        assert_port_free(port)


def download_postgres() -> None:
    if (TOOLS_DIR / "pgsql.ready").is_file():
        if sys.platform == 'win32' and not str(PG_BIN).isascii():
            verify_unicode_runtime(PG_BIN.parent)
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

    # An existing runtime is repair evidence, never an extraction target.
    if (TOOLS_DIR / 'pgsql').exists():
        raise ValueError('PostgreSQL runtime exists without ready marker; explicit repair required')

    print()
    info(t("pg_not_found_downloading"))
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    if not PG_ZIP.exists():
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

        urllib.request.urlretrieve(PG_DOWNLOAD_URL, str(PG_ZIP), _download_progress)
        print()
        ok(t("download_complete"))
    else:
        info("Portable PostgreSQL zip found in cache.")

    info(t("extracting_archive"))
    provision_runtime(PG_ZIP, TOOLS_DIR / 'pgsql')
    generate_manifest(TOOLS_DIR, 'postgresql-' + VERSION + '-windows-x64-binaries')
    (TOOLS_DIR / "pgsql.ready").touch()
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
    ], capture_output=True, text=True,
       encoding='utf-8' if (PG_BIN.parent / '.orion-postgres-runtime.json').is_file() else None)

    if not pg_data.exists() or result.returncode != 0:
        err(t("initdb_failed"))
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        
        # Failed initialization retains runtime/data for explicit repair.
        # Do not delete binaries and retry an unknown existing installation.
        sys.exit(1)

    ok(t("db_dir_ready"))

def database(pg_data, pg_port=None, pg_user=None, pg_db='postgres'):
    from core.native_postgres import Postgres
    dev = Path(pg_data).name.endswith('dev')
    return Postgres(PG_CTL, pg_data,
        pg_port or int(read_env('POSTGRES_DEV_PORT' if dev else 'POSTGRES_PORT', '5432')),
        pg_user or ('router_user_dev' if dev else 'router_user'), pg_db,
        'router_pass_dev' if dev else 'router_pass')


def start_postgres(pg_data: Path, pg_port: int, pg_log: Path, label: str) -> None:
    database(pg_data, pg_port).ensure()


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

def wait_for_postgres(pg_data, pg_port, pg_log, pg_user, label, timeout=DEFAULT_TIMEOUT):
    from core.process_lifecycle import LifecycleError
    if not database(pg_data, pg_port, pg_user).ready():
        raise LifecycleError('PostgreSQL readiness failed')


def stop_postgres(pg_data: Path) -> None:
    database(pg_data).stop()


def setup_db_and_user(pg_user: str, pg_pass: str, pg_port: int, pg_db: str) -> None:
    from core.process_lifecycle import LifecycleError
    import re
    if not all(re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', value) for value in (pg_user, pg_db)):
        raise LifecycleError('Invalid database identifier')
    # SQL input carries the password through stdin, never process argv/logs.
    escaped = pg_pass.replace("'", "''")
    env = dict(os.environ, PGPASSWORD=pg_pass, PGCONNECT_TIMEOUT='3', PGCLIENTENCODING='UTF8')
    command = [str(PSQL), '-h', '127.0.0.1', '-U', pg_user, '-p', str(pg_port),
               '-d', 'postgres', '-w', '-v', 'ON_ERROR_STOP=1', '-At']
    sql = f"ALTER USER {pg_user} WITH PASSWORD '{escaped}';"
    result = run(command, input=sql, text=True, encoding='utf-8', capture_output=True, env=env, timeout=5)
    if result.returncode:
        raise LifecycleError('Database role setup failed')
    exists = run(command + ['-c', f"SELECT 1 FROM pg_database WHERE datname = '{pg_db}'"],
                 capture_output=True, text=True, encoding='utf-8', env=env, timeout=5)
    if exists.returncode:
        raise LifecycleError('Database schema check failed')
    if exists.stdout.strip() != '1':
        created = run(command, input=f'CREATE DATABASE {pg_db} OWNER {pg_user};',
                      capture_output=True, text=True, encoding='utf-8', env=env, timeout=5)
        if created.returncode:
            raise LifecycleError('Database creation failed')


def set_env(router_port: str, pg_port: int, pg_db: str, pg_user: str, pg_pass: str, uvicorn_reload: str) -> None:
    os.environ["POSTGRES_HOST"]           = "127.0.0.1"
    os.environ["POSTGRES_PORT"]           = str(pg_port)
    os.environ["POSTGRES_DB"]             = pg_db
    os.environ["POSTGRES_USER"]           = pg_user
    os.environ["POSTGRES_PASSWORD"]       = pg_pass
    os.environ["BACKEND_URL"]             = f"https://127.0.0.1:{router_port}"
    os.environ["NEXT_PUBLIC_ROUTER_PORT"] = router_port
    os.environ["UVICORN_RELOAD"]          = uvicorn_reload
    os.environ["ROUTER_PORT"]             = router_port
    os.environ["ORION_ROUTER_TLS_PORT"]   = router_port
    os.environ["ROUTER_HOST"]             = "0.0.0.0"
    os.environ["ORION_NO_BANNER"]         = "1"
    from core import config
    from core.mdns import router_id
    from core.tls_identity import load_identity
    identity = load_identity(config.TLS_DIRECTORY, router_id(config.MDNS_ID_FILE))
    os.environ["NODE_EXTRA_CA_CERTS"] = str(identity.certificate_path)
    os.environ["ORION_TLS_CERT"] = str(identity.certificate_path)
    os.environ["ORION_TLS_KEY"] = str(identity.key_path)
