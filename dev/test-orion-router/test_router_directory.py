from types import SimpleNamespace
import unittest
from core.router_directory import public_record
import asyncio
from unittest.mock import AsyncMock, patch
from core.router_directory import DirectoryCache

ID = '12345678-1234-4321-8123-123456789abc'


class DirectoryTests(unittest.TestCase):
    def record(self, **changes):
        info = SimpleNamespace(properties={b'id': ID.encode(), b'v': b'1', b'scheme': b'https', b'path': b'/v1', b'name': b'Peer'}, port=9443, parsed_addresses=lambda: ['192.168.1.20'])
        for name, value in changes.items():
            setattr(info, name, value)
        return public_record(info, ID)

    def test_tls_navigation_uses_ip_and_marks_current_router(self):
        self.assertEqual(self.record()['url'], 'https://192.168.1.20:9443/dashboard')
        self.assertTrue(self.record()['current'])

    def test_public_loopback_and_bad_uuid_are_not_discovery_targets(self):
        for addresses in [['8.8.8.8'], ['127.0.0.1'], ['::1']]:
            with self.assertRaises(ValueError):
                self.record(parsed_addresses=lambda: addresses)
        with self.assertRaises(ValueError):
            self.record(properties={b'id': b'bad'})

    def test_plaintext_and_foreign_routes_are_rejected(self):
        for field, value in [(b'scheme', b'http'), (b'path', b'/evil'), (b'v', b'2')]:
            properties = {b'id': ID.encode(), b'v': b'1', b'scheme': b'https', b'path': b'/v1'}
            properties[field] = value
            with self.assertRaises(ValueError):
                self.record(properties=properties)


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_callers_share_one_scan_and_cached_result(self):
        cache = DirectoryCache()
        async def scan(*args, **kwargs):
            await asyncio.sleep(0.01)
            return [{'id': ID, 'name': 'Peer', 'url': 'https://192.168.1.20:9443/dashboard'}]
        with patch('core.router_directory.discover_routers', AsyncMock(side_effect=scan)) as scan_mock:
            results = await asyncio.gather(*(cache.get(ID) for _ in range(12)))
            self.assertEqual(scan_mock.await_count, 1)
            results[0][0]['name'] = 'mutated'
            self.assertEqual((await cache.get(ID))[0]['name'], 'Peer')
            self.assertEqual(scan_mock.await_count, 1)

    async def test_failed_scan_is_rate_limited(self):
        cache = DirectoryCache()
        with patch('core.router_directory.discover_routers', AsyncMock(side_effect=OSError('network'))) as scan:
            with self.assertRaises(OSError):
                await cache.get(ID)
            self.assertEqual(await cache.get(ID), [])
            self.assertEqual(scan.await_count, 1)


class BrowseTests(unittest.TestCase):
    def test_login_browse_requires_actual_local_listener_or_lan_tls_peer(self):
        from main import app, tls_app
        from core.tls_server import _LoopbackApplication
        from fastapi.testclient import TestClient
        previous = getattr(app.state, 'tls_identity', None)
        app.state.tls_identity = SimpleNamespace(id=ID)
        try:
            with patch('core.router_directory.directory_cache.get', AsyncMock(return_value=[])) as scan:
                lan = TestClient(tls_app, base_url='https://192.168.1.5:9443', client=('192.168.1.40', 52000))
                self.assertEqual(lan.get('/dashboard/api/routers/browse').status_code, 200)
                local = TestClient(_LoopbackApplication(app), base_url='http://localhost:20128', client=('127.0.0.1', 52000))
                self.assertEqual(local.get('/dashboard/api/routers/browse').status_code, 200)
                self.assertEqual(local.get('/dashboard/api/routers/browse', headers={'Host': 'evil.local:20128'}).status_code, 403)
                remote = TestClient(tls_app, base_url='https://192.168.1.5:9443', client=('8.8.8.8', 52000))
                self.assertEqual(remote.get('/dashboard/api/routers/browse', headers={'X-Forwarded-For': '127.0.0.1'}).status_code, 403)
                plain = TestClient(app, client=('127.0.0.1', 52000))
                self.assertEqual(plain.get('/dashboard/api/routers/browse', headers={'X-Forwarded-Proto': 'https'}).status_code, 403)
                self.assertEqual(scan.await_count, 2)
        finally:
            app.state.tls_identity = previous
