#!/usr/bin/env python3
"""
orion.py — Orion Router | CLI Entrypoint
========================================
Merkezi komut yoneticisi. dev, prod ve stop komutlarini yonlendirir.

Kullanim:
    python orion.py [dev | prod | stop]
"""

import os
import sys
import subprocess
from pathlib import Path

# Terminal Renkleri (ANSI)
if sys.platform == "win32":
    os.system("")  # Windows ANSI destegini etkinlestir
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

ROOT = Path(__file__).parent.resolve()
BIN_DIR = ROOT / "bin"

def print_banner():
    line = "═" * 55
    print(f"\n{CYAN}{BOLD}╔{line}╗{RESET}")
    print(f"{CYAN}{BOLD}║{'Orion Router — Command Line Interface':^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def print_usage():
    print_banner()
    print(f"{BOLD}Kullanım:{RESET}")
    print(f"    python orion.py <komut>\n")
    print(f"{BOLD}Geçerli Komutlar:{RESET}")
    print(f"    {GREEN}{BOLD}dev{RESET}   : Geliştirme (Development) ortamını başlatır (hot-reload aktiftir).")
    print(f"    {GREEN}{BOLD}prod{RESET}  : Üretim (Production) ortamını derler ve yerel olarak başlatır.")
    print(f"    {RED}{BOLD}stop{RESET}  : Çalışan tüm arka plan servislerini ve portları temizler.\n")
    print(f"{GRAY}Örnek: python orion.py prod{RESET}\n")

def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1].lower()
    script_map = {
        "dev": BIN_DIR / "dev.py",
        "prod": BIN_DIR / "prod.py",
        "stop": BIN_DIR / "stop.py"
    }

    if cmd in script_map:
        script_path = script_map[cmd]
        if not script_path.exists():
            print(f"{RED}{BOLD}Hata:{RESET} '{script_path.name}' dosyası {BIN_DIR} altında bulunamadı!")
            sys.exit(1)
        
        try:
            # İlgili scripti doğrudan çalıştır
            args = [sys.executable, str(script_path)]
            subprocess.run(args, cwd=ROOT)
        except KeyboardInterrupt:
            # CTRL+C ile kesildiğinde ana script temiz sonlansın
            pass
    else:
        print(f"\n{RED}{BOLD}✘  Hata: Bilinmeyen komut '{cmd}'{RESET}")
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
