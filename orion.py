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
from bin.i18n import t

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
    print(f"{CYAN}{BOLD}║{t('cli_title'):^55}║{RESET}")
    print(f"{CYAN}{BOLD}╚{line}╝{RESET}\n")

def print_usage():
    print_banner()
    print(f"{BOLD}{t('usage')}{RESET}")
    print(f"    python orion.py <komut>\n")
    print(f"{BOLD}{t('valid_commands')}{RESET}")
    print(f"    {GREEN}{BOLD}dev{RESET}   : {t('cmd_dev_desc')}")
    print(f"    {GREEN}{BOLD}prod{RESET}  : {t('cmd_prod_desc')}")
    print(f"    {RED}{BOLD}stop{RESET}  : {t('cmd_stop_desc')}\n")
    print(f"{GRAY}{t('cmd_example')}{RESET}\n")

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
            err_msg = t("err_file_not_found", name=script_path.name, dir=BIN_DIR)
            if "Hata:" in err_msg:
                rest = err_msg.replace("Hata:", "")
                print(f"{RED}{BOLD}Hata:{RESET}{rest}")
            else:
                rest = err_msg.replace("Error:", "")
                print(f"{RED}{BOLD}Error:{RESET}{rest}")
            sys.exit(1)
        
        try:
            # İlgili scripti doğrudan çalıştır
            args = [sys.executable, str(script_path)]
            subprocess.run(args, cwd=ROOT)
        except KeyboardInterrupt:
            # CTRL+C ile kesildiğinde ana script temiz sonlansın
            pass
    else:
        err_msg = t("err_unknown_command", cmd=cmd)
        if "Hata:" in err_msg:
            rest = err_msg.replace("Hata:", "")
            print(f"\n{RED}{BOLD}✘  Hata:{RESET}{rest}{RESET}")
        else:
            rest = err_msg.replace("Error:", "")
            print(f"\n{RED}{BOLD}✘  Error:{RESET}{rest}{RESET}")
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
