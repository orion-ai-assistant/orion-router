#!/usr/bin/env python3
"""
cli.py — Orion Router | CLI Entrypoint
========================================
Merkezi komut yoneticisi. dev, prod ve stop komutlarini yonlendirir.

Kullanim:
    python cli.py [dev | prod | stop]
"""

import os
import runpy
import sys
from pathlib import Path
from bin.i18n import t
from core.console import utf8_console

# UTF-8 kod sayfasi ve Windows ANSI destegi (cmd.exe baslatmadan)
utf8_console()

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
    print(t("cmd_usage_format"), end="")
    print(f"{BOLD}{t('valid_commands')}{RESET}")
    print(f"    {GREEN}{BOLD}dev{RESET}   : {t('cmd_dev_desc')}")
    print(f"    {GREEN}{BOLD}prod{RESET}  : {t('cmd_prod_desc')}")
    print(f"    {CYAN}{BOLD}update{RESET}: Orion Router'ı en güncel sürüme günceller")
    print(f"    {RED}{BOLD}stop{RESET}  : {t('cmd_stop_desc')}\n")
    print("    python cli.py prod --build (alias: --force-build)")
    print(f"{GRAY}{t('cmd_example')}{RESET}\n")

def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1].lower()
    script_map = {
        "dev": BIN_DIR / "dev.py",
        "prod": BIN_DIR / "prod.py",
        "update": BIN_DIR / "update.py",
        "stop": BIN_DIR / "stop.py"
    }

    if cmd in script_map:
        script_path = script_map[cmd]
        if not script_path.exists():
            err_msg = t("err_file_not_found", name=script_path.name, dir=BIN_DIR)
            print(f"{RED}{BOLD}{t('err_prefix')}{RESET} {err_msg}")
            sys.exit(1)
        
        try:
            # İlgili scripti bu süreçte çalıştır: ikinci bir Python her başlatmaya yorumlayıcı açılışını ve
            # import'ları ekliyordu. Betik, kendi süreciymiş gibi çalışır (argv, __main__, çalışma dizini);
            # çıkış kodu sys.exit ile aynen döner. Hub'ın başlattığı süreç böylece supervisor'ın kendisidir.
            sys.argv = [str(script_path), *sys.argv[2:]]
            os.chdir(ROOT)
            runpy.run_path(str(script_path), run_name="__main__")
        except KeyboardInterrupt:
            # CTRL+C ile kesildiğinde ana script temiz sonlansın
            pass
    else:
        err_msg = t("err_unknown_command", cmd=cmd)
        print(f"\n{RED}{BOLD}✘  {t('err_prefix')}{RESET} {err_msg}")
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
