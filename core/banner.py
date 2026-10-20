"""
core/banner.py
--------------
Terminalde gösterilen "ORION ROUTER" adres afişi. Bilerek hafif: supervisor (bin/prod.py, bin/dev.py) bunu
import ederken FastAPI/veritabanı/sağlayıcı yığınını (core/lifespan.py) yüklemez.
"""
import os


def get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def print_active_services_banner(
    router_port: str | None,
    dashboard_port: str | None = None,
) -> None:
    # Terminal Colors (ANSI)
    BLUE   = "\033[94m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    UNDERLINE = "\033[4m"
    YELLOW = "\033[93m"
    BOLD   = "\033[1m"
    GRAY   = "\033[90m"
    RESET  = "\033[0m"

    port = router_port or str(__import__('core.config', fromlist=['TLS_PORT']).TLS_PORT)
    is_docker = os.path.exists("/.dockerenv")

    # Try to resolve IP
    local_ip = os.getenv("LOCAL_IP") or os.getenv("HOST_IP")
    if not local_ip:
        if is_docker:
            local_ip = "192.168.x.x"  # Monospaced safe placeholder
        else:
            local_ip = get_local_ip()

    from core import config
    dashboard_url = f"http://localhost:{config.LOCAL_HTTP_PORT}/dashboard"
    local_url = f"https://{local_ip}:{port}/dashboard"

    try:
        from bin.i18n import t
        local_net_label = t("banner_other_devices_https")
        local_pc_label = t("banner_this_pc_http")
        cmds_hint = t("banner_commands_hint")
    except Exception:
        local_net_label = "Other devices (HTTPS)"
        local_pc_label = "This PC (HTTP)"
        cmds_hint = "Commands: orionrouter start | stop | logs | help"

    border_line = f"{GRAY}────────────────────────────────────────────────{RESET}"
    title_colored = f"{BLUE}{BOLD}ORION ROUTER{RESET}"
    dash_colored  = f"{BLUE}➜{RESET}  {BOLD}{local_pc_label}:{RESET}   {CYAN}{UNDERLINE}{dashboard_url}{RESET}"
    ip_colored    = f"{BLUE}➜{RESET}  {BOLD}{local_net_label}:{RESET}    {CYAN}{UNDERLINE}{local_url}{RESET}"

    # Print the banner block with clean newlines to separate from surrounding logs
    print()
    print(border_line)
    print(title_colored)
    print()
    print(dash_colored)
    print(ip_colored)
    print(border_line)
    print(f"{GRAY}{cmds_hint}{RESET}")
    print()
