"""HTTPS listener wrapper; production runs one primary TLS listener."""
import asyncio
import ipaddress
from urllib.parse import urlsplit
from contextlib import contextmanager

import uvicorn

from core import config
from starlette.responses import JSONResponse


class _TLSApplication:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Set by this listener, never by client/proxy headers.
        scope = dict(scope, orion_tls_listener=True)
        await self.app(scope, receive, send)


class _LoopbackApplication:
    """Local browser compatibility; neither proxy headers nor DNS rebinding grant access."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            headers = scope.get('headers', [])
            hosts = [value.decode('latin1') for name, value in headers if name.lower() == b'host']
            origins = [value.decode('latin1') for name, value in headers if name.lower() == b'origin']
            try:
                peer = ipaddress.ip_address(scope['client'][0]).is_loopback
                authority = urlsplit('http://' + hosts[0]) if len(hosts) == 1 else None
                host_ok = (authority is not None and authority.hostname in ('localhost', '127.0.0.1', '::1')
                    and not authority.username and not authority.password and not authority.path
                    and not authority.query and not authority.fragment
                    and (authority.port or 80) == scope['server'][1])
                origin_ok = not origins or (len(origins) == 1 and origins[0] == 'http://' + hosts[0])
                allowed = peer and host_ok and origin_ok and scope.get('scheme') in ('http', 'ws')
            except (ValueError, KeyError, IndexError, TypeError):
                allowed = False
            if not allowed:
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1008})
                else:
                    await JSONResponse({'detail': 'loopback_required'}, status_code=403)(scope, receive, send)
                return
            scope = dict(scope, orion_loopback_listener=True)
        await self.app(scope, receive, send)


class _Server(uvicorn.Server):
    async def serve(self, sockets=None):
        try:
            await super().serve(sockets=sockets)
        except SystemExit as exc:
            raise RuntimeError("Router HTTPS listener could not bind") from exc

    @contextmanager
    def capture_signals(self):
        yield  # The primary uvicorn server owns process shutdown signals.

    def install_signal_handlers(self):
        pass  # Compatibility with uvicorn versions before capture_signals.


class TLSListener:
    def __init__(self, app, identity):
        self.server = _Server(uvicorn.Config(_TLSApplication(app), host=config.TLS_HOST, port=config.TLS_PORT,
            ssl_keyfile=str(identity.key_path), ssl_certfile=str(identity.certificate_path),
            ssl_version=__import__("ssl").PROTOCOL_TLS_SERVER, lifespan="off", proxy_headers=False,
            log_level="info", timeout_graceful_shutdown=5))
        self.task = None

    def endpoint(self):
        if not self.server.started:
            return None
        for server in self.server.servers:
            for sock in server.sockets:
                address = sock.getsockname()
                if ":" not in address[0]:
                    return address[0], address[1]
        return None

    async def start(self):
        self.task = asyncio.create_task(self.server.serve(), name="router-https")
        for _ in range(1000):
            if self.server.started:
                return
            if self.task.done():
                await self.task
                raise RuntimeError("Router HTTPS listener exited before startup")
            await asyncio.sleep(0.01)
        await self.close()
        raise RuntimeError("Router HTTPS listener startup timed out")

    async def close(self):
        self.server.should_exit = True
        if self.task:
            await self.task


class LocalHTTPListener(TLSListener):
    def __init__(self, app):
        # Host is intentionally not configurable: local HTTP can never bind LAN.
        self.server = _Server(uvicorn.Config(_LoopbackApplication(app), host='127.0.0.1',
            port=config.LOCAL_HTTP_PORT, lifespan='off', proxy_headers=False,
            log_level='info', timeout_graceful_shutdown=5))
        self.task = None
