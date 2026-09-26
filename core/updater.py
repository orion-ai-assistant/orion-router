"""
core/updater.py
---------------
Orion Router için sürüm denetimi ve otomatik güncelleme yöneticisi.
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional

from core.config import APP_VERSION, GITHUB_REPO

logger = logging.getLogger("service-router.updater")

ROOT = Path(__file__).parent.parent.resolve()
DASHBOARD_DIR = ROOT / "dashboard"

_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0
}
CACHE_TTL = 300  # 5 dakika önbellek

_UPDATE_LOCK = threading.Lock()
_UPDATE_STATE: Dict[str, Any] = {
    "is_updating": False,
    "step": "idle",
    "progress": 0,
    "logs": [],
    "error": None,
    "success": False,
    "started_at": 0,
    "finished_at": 0
}


def _parse_semver(v: str) -> tuple:
    """v0.1.2 veya 0.1.2 şeklindeki sürüm dizgesini karşılaştırılabilir tuple'a dönüştürür."""
    clean = v.strip().lstrip("vV")
    parts = []
    for part in clean.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _is_git_repository() -> bool:
    return (ROOT / ".git").exists()


def check_for_updates(force: bool = False) -> Dict[str, Any]:
    """
    Uzak GitHub reposundaki pyproject.toml dosyasından yeni sürüm olup olmadığını denetler.
    """
    global _CACHE
    now = time.time()
    if not force and _CACHE["data"] and (now - _CACHE["timestamp"] < CACHE_TTL):
        return _CACHE["data"]

    current_ver = APP_VERSION
    latest_ver = current_ver
    release_notes = ""
    release_url = f"https://github.com/{GITHUB_REPO}"
    has_update = False

    # Doğrudan GitHub main dalındaki pyproject.toml dosyasından version kontrolü
    headers = {"User-Agent": "OrionRouter-Updater"}
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/pyproject.toml"
    try:
        req = urllib.request.Request(raw_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                content = resp.read().decode("utf-8")
                for line in content.splitlines():
                    if line.strip().startswith("version"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            parsed = parts[1].strip().strip('"').strip("'")
                            latest_ver = parsed
                            if _parse_semver(parsed) > _parse_semver(current_ver):
                                has_update = True
                            break
    except Exception as e:
        logger.debug(f"GitHub pyproject.toml check failed: {e}")

    result = {
        "current_version": current_ver,
        "latest_version": latest_ver,
        "update_available": has_update,
        "behind_commits": 0,
        "release_notes": release_notes,
        "release_url": release_url,
        "is_git_repo": _is_git_repository(),
        "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    }

    _CACHE["data"] = result
    _CACHE["timestamp"] = now
    return result


def get_update_status() -> Dict[str, Any]:
    with _UPDATE_LOCK:
        return dict(_UPDATE_STATE)


def _append_log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    with _UPDATE_LOCK:
        _UPDATE_STATE["logs"].append(formatted)
    logger.info(f"[Updater] {msg}")


def _set_step(step: str, progress: int):
    with _UPDATE_LOCK:
        _UPDATE_STATE["step"] = step
        _UPDATE_STATE["progress"] = progress


def _run_cmd(cmd, cwd=ROOT, env=None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    _append_log(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        shell=isinstance(cmd, str),
        capture_output=True,
        text=True,
        env=full_env
    )
    if proc.stdout:
        for line in proc.stdout.strip().splitlines():
            if line.strip():
                _append_log(line)
    if proc.stderr:
        for line in proc.stderr.strip().splitlines():
            if line.strip() and not "npm warn" in line.lower():
                _append_log(f"[stderr] {line}")
    return proc


def _perform_update_worker():
    global _UPDATE_STATE
    try:
        _append_log("Güncelleme süreci başlatıldı.")
        
        # 1. Adım: Git Kodlarını Çekme
        _set_step("git_pull", 15)
        _append_log("[1/4] GitHub üzerinden en son kodlar alınıyor...")
        if _is_git_repository():
            fetch_res = _run_cmd("git fetch origin main")
            if fetch_res.returncode != 0:
                raise RuntimeError(f"git fetch failed: {fetch_res.stderr}")

            # Değişiklikleri entegre et
            pull_res = _run_cmd("git pull --ff-only origin main")
            if pull_res.returncode != 0:
                _append_log("ff-only başarısız, reset denetleniyor...")
                reset_res = _run_cmd("git reset --hard origin/main")
                if reset_res.returncode != 0:
                    raise RuntimeError(f"git reset failed: {reset_res.stderr}")
            _append_log("Kodlar başarıyla güncellendi.")
        else:
            _append_log("Git reposu bulunamadı, mevcut dosyalar korunuyor.")

        # 2. Adım: Python Bağımlılıkları
        _set_step("dependencies", 40)
        _append_log("[2/4] Python paketleri denetleniyor...")
        req_file = ROOT / "requirements.txt"
        if req_file.exists():
            pip_res = _run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"])
            if pip_res.returncode != 0:
                _append_log("Uyarı: pip install bazı uyarılar verdi, devam ediliyor.")
        _append_log("Python bağımlılıkları tamamlandı.")

        # 3. Adım: Dashboard Bağımlılıkları & Build
        _set_step("build_dashboard", 70)
        _append_log("[3/4] Dashboard Next.js derlemesi başlatılıyor...")
        
        # npm paket kontrolü
        from bin.npm_integrity import npm_needs_install, record_npm_install
        if npm_needs_install(DASHBOARD_DIR):
            _append_log("Yeni npm paketleri tespit edildi, npm install çalıştırılıyor...")
            npm_i_res = _run_cmd("npm install", cwd=DASHBOARD_DIR)
            if npm_i_res.returncode == 0:
                record_npm_install(DASHBOARD_DIR)
            else:
                _append_log("npm install uyarısı alındı, build işlemine devam ediliyor.")

        # npm run build
        router_port = os.getenv("ROUTER_PORT", "20128")
        build_env = {"NEXT_PUBLIC_ROUTER_PORT": router_port}
        build_res = _run_cmd("npm run build", cwd=DASHBOARD_DIR, env=build_env)
        if build_res.returncode != 0:
            raise RuntimeError(f"Dashboard build failed: {build_res.stderr}")
        _append_log("Dashboard başarıyla derlendi.")

        # 4. Adım: Tamamlanma ve Yeniden Başlatma Sinyali
        _set_step("restarting", 95)
        _append_log("[4/4] Güncelleme tamamlandı! Servis yeniden başlatılıyor...")
        
        # Yeniden başlatma dosyasını oluştur (prod.py supervisor bunu algılayacak)
        restart_flag = ROOT / ".restart_requested"
        restart_flag.write_text(str(int(time.time())), encoding="utf-8")

        with _UPDATE_LOCK:
            _UPDATE_STATE["success"] = True
            _UPDATE_STATE["step"] = "completed"
            _UPDATE_STATE["progress"] = 100
            _UPDATE_STATE["finished_at"] = time.time()
            _UPDATE_STATE["is_updating"] = False

        _append_log("✔ Güncelleme başarıyla bitti! Arayüz kısa süre içinde yenilenecek.")

        # Arka planda 2 saniye sonra FastAPI sürecini kapat (prod.py anında tekrar ayağa kaldıracak)
        def _delayed_exit():
            time.sleep(2.5)
            logger.info("Restart sinyali gereği FastAPI kapatılıyor...")
            # Sadece Python sürecinden 0 ile çık; prod.py superviser'ı postgres'i kapatmadan main.py'yi tekrar başlatacak
            os._exit(0)

        threading.Thread(target=_delayed_exit, daemon=True).start()

    except Exception as e:
        logger.error(f"Update error: {e}", exc_info=True)
        _append_log(f"✘ HATA: {str(e)}")
        with _UPDATE_LOCK:
            _UPDATE_STATE["error"] = str(e)
            _UPDATE_STATE["step"] = "failed"
            _UPDATE_STATE["is_updating"] = False
            _UPDATE_STATE["finished_at"] = time.time()


def start_update() -> Dict[str, Any]:
    """Güncelleme işlemini başlatır."""
    global _UPDATE_STATE
    with _UPDATE_LOCK:
        if _UPDATE_STATE["is_updating"]:
            return {"status": "already_running", "message": "Güncelleme zaten devam ediyor."}

        _UPDATE_STATE = {
            "is_updating": True,
            "step": "started",
            "progress": 5,
            "logs": [],
            "error": None,
            "success": False,
            "started_at": time.time(),
            "finished_at": 0
        }

    thread = threading.Thread(target=_perform_update_worker, daemon=True)
    thread.start()
    return {"status": "started", "message": "Güncelleme başlatıldı."}
