"""Best-effort native LAN discovery, independent of API availability."""
import asyncio
import contextlib
import ipaddress
import logging
import os
import re
import socket
import tempfile
import uuid
from pathlib import Path

import psutil
from zeroconf import IPVersion, ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from core import config

logger = logging.getLogger(__name__)
SERVICE_TYPE = "_orion-router-tls._tcp.local."
TLS_SERVICE_TYPE = "_orion-router-tls._tcp.local."
LAN_NETWORKS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
VIRTUAL = re.compile(r"docker|wsl|vethernet|hyper-v|vpn|loopback|virtual|vmware|vbox|tailscale|zerotier|wireguard|tunnel|utun|^tun\d*|^tap\d*|^wg\d*|^br-|^veth", re.I)


def router_id(path: Path) -> str:
    """Publish a complete per-installation identity atomically; never replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # A hard link publishes the finished file without overwriting a concurrent
        # creator. Readers cannot see a partially written UUID.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="ascii") as file:
            temporary = Path(file.name)
            file.write(str(uuid.uuid4()) + "\n")
            file.flush()
            os.fsync(file.fileno())
        try:
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink()
    return str(uuid.UUID(path.read_text(encoding="ascii").strip()))


def hostname(value: str) -> str:
    value = value.rstrip(".").lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local", value):
        raise ValueError("mDNS hostname must be a single valid label followed by .local")
    if value == "orionrouter.local":
        raise ValueError("Shared browser shortcuts are not installation hostnames")
    return value + "."


def installation_hostname(identity: str, override: str = "") -> str:
    """Full UUID avoids truncated-ID collisions; display-name changes have no effect."""
    return hostname(override or f"orionrouter-{uuid.UUID(identity).hex}.local")


def display_name() -> str:
    return config.MDNS_NAME or f"{socket.gethostname()} — Orion Router"


def container() -> bool:
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists() or bool(os.getenv("container"))


def lan_addresses(selected=(), bind="0.0.0.0") -> tuple[str, ...]:
    stats = psutil.net_if_stats()
    result = set()
    for name, addresses in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup:
            continue
        if selected:
            if name not in selected:
                continue
        elif VIRTUAL.search(name):
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(address.address)
            if any(ip in network for network in LAN_NETWORKS) and bind in ("0.0.0.0", address.address):
                result.add(address.address)
    return tuple(sorted(result))


def listener() -> tuple[str, int] | None:
    """Inspect this process, so CLI port overrides and loopback binds are respected."""
    for connection in psutil.Process().net_connections(kind="tcp4"):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port == config.TLS_PORT:
            return connection.laddr.ip, connection.laddr.port
    return None


def interface_signature(addresses):
    """Also rebuild when an address moves between interfaces."""
    return tuple(sorted(name for name, entries in psutil.net_if_addrs().items()
                        if any(entry.family == socket.AF_INET and entry.address in addresses for entry in entries)))


class Advertiser:
    def __init__(self, *, tls_endpoint=None):
        self.task = None
        self.zc = None
        self.info = None
        self.current = None
        self.tls_endpoint = tls_endpoint

    def start(self):
        if not config.MDNS_ENABLED:
            return
        if container() and not config.MDNS_CONTAINER_HOST_NETWORK:
            logger.info("mDNS disabled in container; use a host advertiser or supported Linux host networking")
            return
        self.task = asyncio.create_task(self.run(), name="router-mdns")

    async def withdraw(self):
        zc, self.zc = self.zc, None
        self.info = None
        self.current = None
        if zc:
            # async_close unregisters services (goodbyes) and closes sockets.
            await zc.async_close()

    async def reconcile(self, identity, server):
        endpoint = self.tls_endpoint() if self.tls_endpoint else await asyncio.to_thread(listener)
        addresses = await asyncio.to_thread(lan_addresses, config.MDNS_INTERFACES, endpoint[0]) if endpoint else ()
        signature = await asyncio.to_thread(interface_signature, addresses) if addresses else ()
        target = (addresses, endpoint[1], signature) if addresses else None
        if target == self.current:
            return
        await self.withdraw()
        if target is None:
            logger.info("mDNS waiting for an API listener on an eligible LAN IPv4 interface")
            return
        self.zc = AsyncZeroconf(interfaces=list(addresses), ip_version=IPVersion.V4Only)
        service_type = TLS_SERVICE_TYPE if self.tls_endpoint else SERVICE_TYPE
        properties = {"id": identity, "name": display_name(), "path": "/v1", "version": config.APP_VERSION}
        properties.update({"v": "1", "scheme": "https"})
        self.info = ServiceInfo(
            service_type, f"Orion Router {identity}.{service_type}",
            parsed_addresses=list(addresses), port=endpoint[1], server=server,
            properties=properties,
        )
        # The shared Orion service name exceeds DNS-SD's optional 15-character
        # check. Keep that protocol name; Zeroconf supports it with strict=False.
        announcement = await self.zc.async_register_service(self.info, allow_name_change=True, strict=False)
        await announcement
        self.current = target
        logger.info("mDNS advertising %s on port %s (%s)", server, endpoint[1], ", ".join(addresses))

    async def run(self):
        try:
            try:
                identity = await asyncio.to_thread(router_id, config.MDNS_ID_FILE)
                server = installation_hostname(identity, config.MDNS_HOSTNAME)
            except (OSError, ValueError, UnicodeError) as exc:
                logger.error("mDNS identity/config invalid (%s); discovery disabled; existing identity retained", type(exc).__name__)
                return
            while True:
                retry_delay = 30
                try:
                    await self.reconcile(identity, server)
                    retry_delay = 30 if self.current else 1
                except Exception as exc:
                    logger.warning("mDNS failed (%s); retrying; API remains available", type(exc).__name__)
                    try:
                        await self.withdraw()
                    except Exception as cleanup_exc:
                        logger.warning("mDNS cleanup failed (%s)", type(cleanup_exc).__name__)
                await asyncio.sleep(retry_delay)
        finally:
            await self.withdraw()

    async def close(self):
        if self.task:
            self.task.cancel()
            try:
                with contextlib.suppress(asyncio.CancelledError):
                    await self.task
            except Exception as exc:
                logger.warning("mDNS shutdown failed (%s)", type(exc).__name__)
