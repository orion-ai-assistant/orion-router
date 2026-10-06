#!/usr/bin/env python3
"""
update.py — Orion Router | CLI Updater
=======================================
Orion Router'ı en güncel sürüme günceller.

Kullanım:
    python cli.py update
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.common import (
    ROOT,
    RESET, BOLD, CYAN, GREEN, YELLOW, RED, GRAY,
    ok, info, warn, err, dim, run
)
from core.updater import check_for_updates, APP_VERSION
from bin.dashboard_build import ensure_dashboard
from bin.i18n import t

def banner():
    line = "═" * 55
    print(f"\n{CYAN}{BOLD}╔{line}╗{RESET}")
    print(f"{CYAN}{BOLD}║{'Orion Router — Güncelleyici':^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def main():
    banner()
    info(f"Mevcut Sürüm: {BOLD}v{APP_VERSION}{RESET}")
    info("Güncellemeler denetleniyor...")
    
    status = check_for_updates(force=True)
    latest = status.get("latest_version", APP_VERSION)
    update_available = status.get("update_available", False)

    if not update_available:
        ok(f"Orion Router zaten en güncel sürümde (v{APP_VERSION})!")
        if "--force" not in sys.argv:
            sys.exit(0)
        else:
            warn("Zorunlu güncelleme modu (--force) devrede.")
    else:
        warn(f"Yeni sürüm bulundu: {BOLD}v{latest}{RESET}")

    print()
    info("[1/3] Kodlar GitHub'dan çekiliyor (git pull)...")
    if (ROOT / ".git").exists():
        res_fetch = run("git fetch origin main", cwd=ROOT, shell=True)
        if res_fetch.returncode != 0:
            err("git fetch başarısız oldu!")
            sys.exit(1)
        res_pull = run("git pull --ff-only origin main", cwd=ROOT, shell=True)
        if res_pull.returncode != 0:
            warn("Fast-forward yapılamadı, yerel değişiklikler sıfırlanıyor (git reset)...")
            res_reset = run("git reset --hard origin/main", cwd=ROOT, shell=True)
            if res_reset.returncode != 0:
                err("git reset başarısız oldu!")
                sys.exit(1)
        ok("Kodlar başarıyla güncellendi.")
    else:
        warn("Git deposu bulunamadı, mevcut dosyalar ile devam ediliyor.")

    print()
    info("[2/3] Bağımlılıklar denetleniyor...")
    req_file = ROOT / "requirements.txt"
    if req_file.exists():
        dim("Python paketleri güncelleniyor...")
        run(f'"{sys.executable}" -m pip install -r requirements.txt --quiet', cwd=ROOT, shell=True)
    ok("Python paketleri kontrol edildi.")

    print()
    info("[3/3] Dashboard denetleniyor...")
    try:
        ensure_dashboard()
    except Exception as exc:
        err(f"Kod güncellendi ancak dashboard hazırlanamadı: {exc}")
        sys.exit(1)

    print()
    ok(f"{BOLD}✔ Orion Router başarıyla güncellendi!{RESET}")
    dim("Çalışan servis varsa yeniden başlatmak için `python cli.py stop` ve `python cli.py prod` çalıştırabilirsiniz.")

if __name__ == "__main__":
    main()
