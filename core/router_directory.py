"""Untrusted discovery hints for dashboard navigation, never trust enrollment."""
import asyncio
import ipaddress
import time
from uuid import UUID

from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from core.mdns import LAN_NETWORKS, TLS_SERVICE_TYPE, lan_addresses

class DirectoryCache:
    """One shared scan per process per ten seconds; cancelled requests do not cancel it."""
    def __init__(self):
        self.task = None
        self.current_id = None
        self.records = []
        self.expires = 0.0

    async def get(self, current_id):
        if self.current_id == current_id and time.monotonic() < self.expires:
            return [dict(record) for record in self.records]
        if self.task is None:
            self.task = asyncio.create_task(discover_routers(current_id, duration=2))
        task = self.task
        try:
            records = await asyncio.shield(task)
            self.records, self.current_id = records, current_id
            self.expires = time.monotonic() + 10
            return [dict(record) for record in records]
        except Exception:
            self.records, self.current_id = [], current_id
            self.expires = time.monotonic() + 10
            raise
        finally:
            if task.done() and self.task is task:
                self.task = None


directory_cache = DirectoryCache()


def public_record(info, current_id):
    props = {key.decode('utf-8'): value.decode('utf-8') for key, value in info.properties.items() if value is not None}
    identity = str(UUID(props['id']))
    if props.get('v') != '1' or props.get('scheme') != 'https' or props.get('path') != '/v1':
        raise ValueError('Not a compatible TLS Router')
    if not 1 <= info.port <= 65535:
        raise ValueError('Invalid port')
    addresses = sorted(address for address in info.parsed_addresses()
                       if isinstance(ipaddress.ip_address(address), ipaddress.IPv4Address)
                       and any(ipaddress.ip_address(address) in network for network in LAN_NETWORKS))
    if not addresses:
        raise ValueError('No LAN address')
    return {'id': identity, 'name': props.get('name', 'Orion Router')[:120],
            'url': f'https://{addresses[0]}:{info.port}/dashboard', 'current': identity == current_id}


async def discover_routers(current_id, duration=2):
    interfaces = await asyncio.to_thread(lan_addresses)
    if not interfaces:
        return []
    zc = AsyncZeroconf(interfaces=list(interfaces), ip_version=IPVersion.V4Only)
    names = set()
    def changed(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Removed:
            names.discard(name)
        elif len(names) < 64:
            names.add(name)
    browser = AsyncServiceBrowser(zc.zeroconf, TLS_SERVICE_TYPE, handlers=[changed])
    try:
        await asyncio.sleep(duration)
        async def resolve(name):
            info = AsyncServiceInfo(TLS_SERVICE_TYPE, name)
            try:
                if await info.async_request(zc.zeroconf, 1000):
                    return public_record(info, current_id)
            except (ValueError, KeyError, UnicodeError):
                pass
            return None
        records = [record for record in await asyncio.gather(*(resolve(name) for name in names)) if record]
        by_id = {}
        for record in records:
            previous = by_id.get(record['id'])
            if previous:
                if previous['url'] != record['url']:
                    previous['conflict'] = True
            else:
                by_id[record['id']] = record
        return sorted(by_id.values(), key=lambda record: record['name'])
    finally:
        await browser.async_cancel()
        await zc.async_close()
