import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from zeroconf import DNSAddress, DNSService
from zeroconf.const import _CLASS_IN, _TYPE_AAAA, _TYPE_SRV

from core.zeroconf_compat import _UniqueExpirationCache
from core.windows_asyncio import _reset_safe_connection_lost


class ExpirationTests(unittest.TestCase):
    def address(self, ttl, created=1000):
        return DNSAddress('Hiro.local.', _TYPE_AAAA, _CLASS_IN, ttl,
                          socket.inet_pton(socket.AF_INET6, '2a00::1'), created=created)

    def test_ttl_returning_to_prior_expiry_removes_record_once(self):
        cache = _UniqueExpirationCache()
        for ttl in (60, 1, 60):
            record = self.address(ttl)
            cache.async_add_records([record])
        self.assertEqual(cache.async_expire(62000), [record])
        self.assertEqual(cache.entries_with_name('Hiro.local.'), [])
        self.assertEqual(cache._total_records, 0)
        self.assertEqual(cache._expirations, {})
        # Cleanup remains usable for the next received record.
        record = self.address(60, created=63000)
        cache.async_add_records([record])
        self.assertEqual(cache.async_expire(124000), [record])
        self.assertEqual(cache._total_records, 0)

    def test_ttl_refresh_does_not_prematurely_remove_live_record(self):
        cache = _UniqueExpirationCache()
        cache.async_add_records([self.address(1)])
        refreshed = self.address(60)
        cache.async_add_records([refreshed])
        self.assertEqual(cache.async_expire(3000), [])
        self.assertEqual(cache.entries_with_name('Hiro.local.'), [refreshed])
        self.assertEqual(cache.async_expire(62000), [refreshed])

    def test_service_secondary_index_and_other_records_survive(self):
        cache = _UniqueExpirationCache()
        address = self.address(120)
        cache.async_add_records([address])
        for ttl in (60, 1, 60):
            service = DNSService('Orion._orion-router-tls._tcp.local.', _TYPE_SRV,
                                 _CLASS_IN, ttl, 0, 0, 9443, 'Hiro.local.', created=1000)
            cache.async_add_records([service])
        self.assertEqual(cache.async_expire(62000), [service])
        self.assertEqual(cache.entries_with_server('Hiro.local.'), [])
        self.assertEqual(cache.entries_with_name('Hiro.local.'), [address])
        self.assertEqual(cache._total_records, 1)


class ProactorCleanupTests(unittest.TestCase):
    def setUp(self):
        from asyncio.proactor_events import _ProactorBasePipeTransport
        import inspect
        original = inspect.unwrap(_ProactorBasePipeTransport._call_connection_lost)
        self.close = _reset_safe_connection_lost(original)
        self.transport = SimpleNamespace(_called_connection_lost=False,
            _protocol=Mock(), _sock=Mock(), _server=Mock())
        self.transport._sock.fileno.return_value = 7

    def reset(self, code=10054):
        error = ConnectionResetError('peer reset')
        error.winerror = code
        return error

    def test_reset_still_closes_socket_detaches_server_and_notifies_once(self):
        transport = self.transport
        sock, server = transport._sock, transport._server
        sock.shutdown.side_effect = self.reset()
        self.close(transport, None)
        self.close(transport, None)
        transport._protocol.connection_lost.assert_called_once_with(None)
        sock.close.assert_called_once()
        server._detach.assert_called_once()
        self.assertIsNone(transport._sock)
        self.assertIsNone(transport._server)
        self.assertTrue(transport._called_connection_lost)

    def test_protocol_errors_are_not_suppressed(self):
        error = self.reset()
        self.transport._protocol.connection_lost.side_effect = error
        with self.assertRaises(ConnectionResetError) as caught:
            self.close(self.transport, None)
        self.assertIs(caught.exception, error)

    def test_other_socket_errors_are_not_suppressed(self):
        error = self.reset(10053)
        self.transport._sock.shutdown.side_effect = error
        with self.assertRaises(ConnectionResetError) as caught:
            self.close(self.transport, None)
        self.assertIs(caught.exception, error)

    def test_normal_close_keeps_existing_behavior(self):
        sock, server = self.transport._sock, self.transport._server
        self.close(self.transport, None)
        sock.close.assert_called_once()
        server._detach.assert_called_once()
        self.assertTrue(self.transport._called_connection_lost)
