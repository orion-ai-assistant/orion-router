import asyncio
import hashlib
import socket
import ipaddress
import ssl
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from core.tls_identity import load_identity, spki_fingerprint
from core.tls_server import TLSListener, LocalHTTPListener, _LoopbackApplication
from core import config, mdns
from fastapi import FastAPI
from fastapi.testclient import TestClient


class IdentityTests(unittest.TestCase):
    def test_browser_san_names_and_upgrade_preserve_spki(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        with tempfile.TemporaryDirectory() as directory:
            identity = load_identity(Path(directory), 'id')
            key = serialization.load_pem_private_key(identity.key_path.read_bytes(), None)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'old router')])
            now = datetime.now(timezone.utc)
            old = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=100))
                .sign(key, hashes.SHA256()))
            identity.certificate_path.write_bytes(old.public_bytes(serialization.Encoding.PEM))
            updated = load_identity(Path(directory), 'id')
            self.assertEqual(updated.fp, identity.fp)
            cert = x509.load_pem_x509_certificate(updated.certificate_path.read_bytes())
            names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertIn('localhost', names.get_values_for_type(x509.DNSName))
            self.assertIn(ipaddress.ip_address('127.0.0.1'), names.get_values_for_type(x509.IPAddress))
            self.assertIn(ipaddress.ip_address('::1'), names.get_values_for_type(x509.IPAddress))
    def test_restart_and_spki_not_certificate_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = load_identity(Path(directory), 'router-id')
            restarted = load_identity(Path(directory), 'router-id')
            self.assertEqual(identity, restarted)
            cert = x509.load_pem_x509_certificate(identity.certificate_path.read_bytes())
            self.assertEqual(identity.fp, spki_fingerprint(cert.public_key()))
            self.assertNotEqual(identity.fp, hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest())
            self.assertEqual(len(identity.fp), 64)

    def test_renew_certificate_preserves_key_and_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            original = load_identity(Path(directory), 'router-id')
            certificate = original.certificate_path.read_bytes()
            key = original.key_path.read_bytes()
            renewed = load_identity(Path(directory), 'router-id', now=datetime.now(timezone.utc) + timedelta(days=365*51))
            self.assertEqual(original.fp, renewed.fp)
            self.assertEqual(key, renewed.key_path.read_bytes())
            self.assertNotEqual(certificate, renewed.certificate_path.read_bytes())

    def test_invalid_key_and_missing_key_never_silently_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = load_identity(Path(directory), 'router-id')
            identity.key_path.write_bytes(b'broken')
            with self.assertRaises(ValueError):
                load_identity(Path(directory), 'router-id')
            self.assertEqual(identity.key_path.read_bytes(), b'broken')
            identity.key_path.unlink()
            with self.assertRaises(ValueError):
                load_identity(Path(directory), 'router-id')
            self.assertFalse(identity.key_path.exists())

    def test_replaced_key_changes_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            first = load_identity(Path(directory)/'one', 'same-id')
            second = load_identity(Path(directory)/'two', 'same-id')
            self.assertNotEqual(first.fp, second.fp)

    def test_mismatched_certificate_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            first = load_identity(Path(directory)/'one', 'same-id')
            second = load_identity(Path(directory)/'two', 'same-id')
            first.certificate_path.write_bytes(second.certificate_path.read_bytes())
            with self.assertRaises(ValueError):
                load_identity(Path(directory)/'one', 'same-id')

    def test_concurrent_first_launch_retains_one_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with ThreadPoolExecutor(max_workers=8) as pool:
                identities = list(pool.map(lambda _: load_identity(Path(directory), 'id'), range(16)))
            self.assertEqual(len({item.fp for item in identities}), 1)


class ListenerTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_loopback_listener_bind_host_origin_and_tls_only_identity(self):
        from main import app
        with patch.object(config, 'LOCAL_HTTP_PORT', 0):
            listener = LocalHTTPListener(app)
            await listener.start()
            try:
                host, port = listener.endpoint()
                self.assertEqual(host, '127.0.0.1')
                async def request(path, authority, origin=''):
                    reader, writer = await asyncio.open_connection(host, port)
                    extra = f'Origin: {origin}\r\n' if origin else ''
                    writer.write(f'GET {path} HTTP/1.1\r\nHost: {authority}\r\n{extra}Connection: close\r\n\r\n'.encode())
                    await writer.drain()
                    response = await reader.read()
                    writer.close()
                    await writer.wait_closed()
                    return response
                self.assertIn(b'200 OK', await request('/health', f'localhost:{port}'))
                self.assertIn(b'403 Forbidden', await request('/health', f'evil.local:{port}'))
                self.assertIn(b'403 Forbidden', await request('/health', f'localhost:{port}', 'http://evil.local'))
                self.assertIn(b'403 Forbidden', await request('/api/v1/tls/identity', f'localhost:{port}'))
            finally:
                await listener.close()

    def test_loopback_rejects_remote_peer_even_with_forwarded_headers(self):
        from main import app
        client = TestClient(_LoopbackApplication(app), base_url='http://localhost:20128',
                            client=('192.168.1.50', 50100))
        self.assertEqual(client.get('/health', headers={'X-Forwarded-For': '127.0.0.1',
                          'X-Forwarded-Proto': 'https'}).status_code, 403)

    async def test_real_https_listener_shared_routes_and_certificate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = load_identity(Path(directory), 'router-id')
            from main import app
            app.state.tls_identity = identity
            with patch.object(config, 'TLS_PORT', 0), patch.object(config, 'TLS_HOST', '127.0.0.1'):
                listener = TLSListener(app, identity)
                await listener.start()
                try:
                    _, port = listener.endpoint()
                    context = ssl.create_default_context(cafile=str(identity.certificate_path))
                    # The installed certificate is the explicit test CA. Hostname is
                    # its exact certificate CN; no accept-all verification occurs.
                    reader, writer = await asyncio.open_connection('127.0.0.1', port, ssl=context,
                        server_hostname='localhost')
                    cert = x509.load_der_x509_certificate(writer.get_extra_info('ssl_object').getpeercert(binary_form=True))
                    self.assertEqual(spki_fingerprint(cert.public_key()), identity.fp)
                    writer.write(b'GET /api/v1/tls/identity HTTP/1.1\r\nHost: router\r\nConnection: close\r\n\r\n')
                    await writer.drain()
                    response = await reader.read()
                    self.assertIn(b'200 OK', response)
                    self.assertIn(identity.fp.encode(), response)
                    self.assertIn(b'"id":"router-id"', response)
                    writer.close()
                    await writer.wait_closed()
                finally:
                    await listener.close()

    def test_legacy_identity_rejects_fake_tls_headers(self):
        from main import app
        client = TestClient(app)
        response = client.get('/api/v1/tls/identity', headers={
            'X-Forwarded-Proto': 'https', 'Forwarded': 'proto=https'})
        self.assertEqual(response.status_code, 403)

    def test_every_plain_http_route_fails_closed(self):
        from main import app, tls_app
        for target in (app, tls_app):
            client = TestClient(target)
            for path in ('/health', '/dashboard/api/tls/identity', '/v1/chat/completions', '/'):
                response = client.get(path, headers={'X-Forwarded-Proto': 'https'})
                self.assertEqual(response.status_code, 403, path)

    def test_admin_identity_requires_admin_key(self):
        from main import app
        from core.dependencies import verify_admin
        from fastapi import HTTPException
        async def reject():
            raise HTTPException(status_code=401)
        app.dependency_overrides[verify_admin] = reject
        try:
            from main import tls_app
            self.assertEqual(TestClient(tls_app, base_url='https://localhost').get('/dashboard/api/tls/identity').status_code, 401)
        finally:
            app.dependency_overrides.pop(verify_admin, None)

    async def test_tls_advertisement_real_tls_port_and_protocol_txt(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        async def register(*args, **kwargs):
            future = asyncio.get_running_loop().create_future()
            future.set_result(None)
            return future
        zc = SimpleNamespace(async_register_service=AsyncMock(side_effect=register), async_close=AsyncMock())
        advertiser = mdns.Advertiser(tls_endpoint=lambda: ('0.0.0.0', 9443))
        with patch.object(mdns, 'AsyncZeroconf', return_value=zc), patch.object(mdns, 'lan_addresses', return_value=('192.168.1.5',)):
            await advertiser.reconcile('router-id', 'orionrouter-install.local.')
            self.assertEqual(advertiser.info.type, mdns.TLS_SERVICE_TYPE)
            self.assertEqual(advertiser.info.port, 9443)
            self.assertEqual(advertiser.info.properties[b'v'], b'1')
            self.assertEqual(advertiser.info.properties[b'scheme'], b'https')
            self.assertEqual(advertiser.info.properties[b'id'], b'router-id')
            await advertiser.close()
            await advertiser.withdraw()


if __name__ == '__main__':
    unittest.main()
