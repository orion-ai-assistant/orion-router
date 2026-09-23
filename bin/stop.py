#!/usr/bin/env python3
"""
stop.py — Orion Router | Graceful Shutdown
==========================================
Tüm Orion Router servislerini önce nazikçe, gerekirse zorla durdurur.

Strateji:
  1. Router süreci (orion.pid) → SIGTERM, 3s bekle → SIGKILL fallback
    2. PostgreSQL Dev (.pgdata-dev, port POSTGRES_DEV_PORT) → pg_ctl stop -m fast → force fallback
    3. PostgreSQL Prod (.pgdata-prod, port POSTGRES_PORT) → pg_ctl stop -m fast → force fallback
  Adım 1–3 PARALEL çalışır.

  Son kontrol: İlgili portlar hâlâ açıksa zorla temizle.

Kullanim:
    python stop.py
    python stop.py --quiet
"""

import sys
import socket
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.common import (
    ROOT, PG_CTL, DEFAULT_TIMEOUT,
    RESET, BOLD, CYAN, GREEN, YELLOW, RED, GRAY,
    ok, info, warn, err, dim,
    run, run_silent, read_env, _windows_listening_pids, _windows_orphan_postgres_children,
)
from bin.i18n import t
import os

DEV_DATA  = ROOT / ".pgdata-dev"
DEV_PORT  = int(read_env("POSTGRES_DEV_PORT", ""))

PROD_DATA = ROOT / ".pgdata-prod"
PROD_PORT = int(read_env("POSTGRES_PORT", ""))

ROUTER_PORT = int(os.environ.get("ROUTER_PORT") or read_env("ROUTER_PORT", "20128"))
ROUTER_DEV_PORT = int(os.environ.get("ROUTER_DEV_PORT") or read_env("ROUTER_DEV_PORT", "20129"))
UI_PORT = 3001  # Next.js dev server varsayılan portu

ROUTER_PORTS = [ROUTER_PORT, ROUTER_DEV_PORT, UI_PORT]  # prod/dev router ve next.js portları

QUIET_MODE = "--quiet" in sys.argv
GRACEFUL_TIMEOUT = 5  # saniye


# ─────────────────────────────────────────────────────────────────────────────
# Port Check
# ─────────────────────────────────────────────────────────────────────────────

def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Graceful PostgreSQL Stop (önce pg_ctl, sonra force)
# ─────────────────────────────────────────────────────────────────────────────

def _stop_postgres_graceful(data_dir: Path, port: int, label: str) -> bool:
    """pg_ctl -m fast ile graceful kapat. Kapanmazsa force-kill fallback."""
    if not data_dir.exists():
        return True

    if not is_port_open(port):
        if not QUIET_MODE:
            dim(f"PostgreSQL ({label}) zaten çalışmıyor.")
        return True

    if not QUIET_MODE:
        info(t("stopping_pg_label", label=label))

    if PG_CTL.exists():
        result = run(
            [str(PG_CTL), "-D", str(data_dir), "-t", str(GRACEFUL_TIMEOUT), "-m", "fast", "stop"],
            capture_output=True, text=True, timeout=GRACEFUL_TIMEOUT + 3
        )
        if result.returncode == 0 and not is_port_open(port):
            if not QUIET_MODE:
                ok(t("stopped_pg_label", label=label))
            return True

    # Graceful başarısız → force fallback
    if not QUIET_MODE:
        warn(f"PostgreSQL ({label}) graceful kapanmadı, zorla durduruluyor...")

    return _force_kill_postgres_port(port, data_dir, label)


def _force_kill_postgres_port(port: int, data_dir: Path, label: str) -> bool:
    """Porta bağlı postgres sürecini zorla öldür ve sonucu doğrula."""
    killed = False
    if sys.platform == "win32":
        try:
            listener_pids = _windows_listening_pids(port)
            for pid in listener_pids:
                result = run_silent(["taskkill", "/f", "/t", "/pid", pid])
                killed = result.returncode == 0 or killed
                if result.returncode != 0:
                    for child_pid in _windows_orphan_postgres_children(pid):
                        child_result = run_silent(["taskkill", "/f", "/t", "/pid", child_pid])
                        killed = child_result.returncode == 0 or killed
            if not listener_pids:
                # PID dosyasından dene
                pid_file = data_dir / "postmaster.pid"
                if pid_file.exists():
                    lines = pid_file.read_text().splitlines()
                    if lines and lines[0].isdigit():
                        result = run_silent(["taskkill", "/f", "/t", "/pid", lines[0]])
                        killed = result.returncode == 0
        except Exception:
            pass
    else:
        try:
            res = run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for pid in res.stdout.splitlines():
                    if pid.strip().isdigit():
                        result = run_silent(["kill", "-9", pid.strip()])
                        killed = result.returncode == 0 or killed
        except Exception:
            pass

    if killed:
        time.sleep(1.0)

    if is_port_open(port):
        if not QUIET_MODE:
            warn(f"PostgreSQL ({label}) port {port} kapatılamadı.")
        return False

    if killed and not QUIET_MODE:
        dim(f"  PostgreSQL ({label}) port {port} zorla temizlendi.")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Graceful Router Stop (orion.pid → SIGTERM → SIGKILL)
# ─────────────────────────────────────────────────────────────────────────────

def _stop_router_graceful() -> None:
    """Router sürecini (orion.pid) graceful durdur, gerekirse zorla öldür."""
    pid_file = ROOT / ".orion.pid"

    if not pid_file.exists():
        if not QUIET_MODE:
            dim("Router PID dosyası bulunamadı, muhtemelen zaten durmuş.")
        return

    try:
        lines = pid_file.read_text().splitlines()
        if not lines or not lines[0].isdigit():
            pid_file.unlink(missing_ok=True)
            return

        pid = int(lines[0])

        if not QUIET_MODE:
            info(f"Orion Router süreci durduruluyor (PID: {pid})...")

        if sys.platform == "win32":
            # Windows: TASKKILL /T child-process'leri de kapatır
            result = run_silent(["taskkill", "/t", "/pid", str(pid)])
            time.sleep(1.5)

            # Hâlâ çalışıyor mu?
            check = run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=DEFAULT_TIMEOUT
            )
            if str(pid) in check.stdout:
                run_silent(["taskkill", "/f", "/t", "/pid", str(pid)])
                if not QUIET_MODE:
                    warn(f"  Router PID {pid} zorla öldürüldü.")
            else:
                if not QUIET_MODE:
                    ok("Orion Router graceful olarak durduruldu.")
        else:
            import os, signal as _signal
            try:
                os.kill(pid, _signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

            # GRACEFUL_TIMEOUT kadar bekle
            deadline = time.time() + GRACEFUL_TIMEOUT
            while time.time() < deadline:
                try:
                    os.kill(pid, 0)
                    time.sleep(0.3)
                except ProcessLookupError:
                    break

            try:
                os.kill(pid, 0)
                os.kill(pid, _signal.SIGKILL)
                if not QUIET_MODE:
                    warn(f"  Router PID {pid} zorla öldürüldü.")
            except ProcessLookupError:
                if not QUIET_MODE:
                    ok("Orion Router graceful olarak durduruldu.")

    except Exception as e:
        if not QUIET_MODE:
            warn(f"Router durdurulurken hata: {e}")
    finally:
        pid_file.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Son Kontrol: Router portları hâlâ açıksa temizle
# ─────────────────────────────────────────────────────────────────────────────

def _cleanup_leftover_router_ports() -> None:
    for port in ROUTER_PORTS:
        if not is_port_open(port):
            continue
        if not QUIET_MODE:
            warn(f"Router portu {port} hâlâ açık, temizleniyor...")
        if sys.platform == "win32":
            try:
                result = run(
                    ["netstat", "-aon"], capture_output=True, text=True, timeout=DEFAULT_TIMEOUT
                )
                for line in result.stdout.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        pid = line.split()[-1]
                        if pid.isdigit() and pid != "0":
                            run_silent(["taskkill", "/f", "/t", "/pid", pid])
                            dim(f"  Port {port} (PID {pid}) temizlendi.")
            except Exception:
                pass
        else:
            try:
                res = run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True, timeout=5)
                for pid in res.stdout.splitlines():
                    if pid.strip().isdigit():
                        run_silent(["kill", "-9", pid.strip()])
                        dim(f"  Port {port} (PID {pid.strip()}) temizlendi.")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not QUIET_MODE:
        line = "═" * 55
        print(f"\n{RED}{BOLD}╔{line}╗{RESET}")
        print(f"{RED}{BOLD}║{t('stop_title'):^55}║{RESET}")
        print(f"{RED}{BOLD}╚{line}╝{RESET}\n")

    # Tüm kapatma görevlerini paralel thread'lerde çalıştır
    threads = [
        threading.Thread(target=_stop_router_graceful, name="stop-router"),
        threading.Thread(target=_stop_postgres_graceful, args=(DEV_DATA, DEV_PORT, "Dev"), name="stop-pg-dev"),
        threading.Thread(target=_stop_postgres_graceful, args=(PROD_DATA, PROD_PORT, "Prod"), name="stop-pg-prod"),
    ]

    for t_obj in threads:
        t_obj.start()

    for t_obj in threads:
        t_obj.join()

    # Son güvenlik taraması: router portları
    _cleanup_leftover_router_ports()

    if not QUIET_MODE:
        print()

    busy_ports = [port for port in [DEV_PORT, PROD_PORT, *ROUTER_PORTS] if is_port_open(port)]
    if busy_ports:
        details = []
        for port in busy_ports:
            pids = _windows_listening_pids(port)
            details.append(f"{port} (PID {', '.join(pids)})" if pids else str(port))
        err(t("port_cleanup_failed", ports=", ".join(details)))
        if sys.platform == "win32":
            warn(t("port_cleanup_admin_hint"))
        raise SystemExit(1)

    if not QUIET_MODE:
        ok(t("all_services_cleared"))


if __name__ == "__main__":
    main()
