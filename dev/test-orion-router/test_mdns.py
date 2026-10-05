import asyncio
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import mdns


class IdentityTests(unittest.TestCase):
    def test_identity_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mdns-id"
            self.assertEqual(mdns.router_id(path), mdns.router_id(path))

    def test_corrupt_identity_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mdns-id"
            path.write_text("broken")
            with self.assertRaises(ValueError):
                mdns.router_id(path)
            self.assertEqual(path.read_text(), "broken")

    def test_hostname(self):
        self.assertEqual(mdns.hostname("OrionRouter-home.local."), "orionrouter-home.local.")
        for value in ("localhost", "bad.name.local", "-bad.local", "bad.local:20128", "OrionRouter.local."):
            with self.assertRaises(ValueError):
                mdns.hostname(value)

    def test_two_installations_same_computer_have_different_persistent_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / install / "mdns-id" for install in ("first", "second")]
            identities = [mdns.router_id(path) for path in paths]
            hosts = [mdns.installation_hostname(identity) for identity in identities]
            self.assertNotEqual(identities[0], identities[1])
            self.assertNotEqual(hosts[0], hosts[1])
            for path, identity, host in zip(paths, identities, hosts):
                self.assertEqual(mdns.router_id(path), identity)
                self.assertEqual(mdns.installation_hostname(mdns.router_id(path)), host)

    def test_display_name_changes_preserve_identity_and_hostname(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mdns-id"
            identity = mdns.router_id(path)
            host = mdns.installation_hostname(identity)
            with patch.object(mdns.config, "MDNS_NAME", ""), patch.object(mdns.socket, "gethostname", return_value="Same PC"):
                self.assertEqual(mdns.display_name(), "Same PC — Orion Router")
            with patch.object(mdns.config, "MDNS_NAME", "My Router"):
                self.assertEqual(mdns.display_name(), "My Router")
                self.assertEqual(mdns.router_id(path), identity)
                self.assertEqual(mdns.installation_hostname(identity), host)

    def test_concurrent_first_launch_has_one_complete_identity(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mdns-id"
            with ThreadPoolExecutor(max_workers=8) as executor:
                identities = list(executor.map(lambda _: mdns.router_id(path), range(16)))
            self.assertEqual(len(set(identities)), 1)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_interface_selection_and_bind(self):
        addresses = {name: [SimpleNamespace(family=socket.AF_INET, address=ip)] for name, ip in (
            ("Wi-Fi", "192.168.1.7"), ("Ethernet", "10.1.2.3"),
            ("vEthernet (WSL)", "172.20.1.1"), ("VPN", "10.8.0.2"),
            ("down", "192.168.2.1"), ("lo", "127.0.0.1"), ("public", "8.8.8.8"),
        )}
        stats = {name: SimpleNamespace(isup=name != "down") for name in addresses}
        with patch.object(mdns.psutil, "net_if_addrs", return_value=addresses), patch.object(mdns.psutil, "net_if_stats", return_value=stats):
            self.assertEqual(mdns.lan_addresses(), ("10.1.2.3", "192.168.1.7"))
            self.assertEqual(mdns.lan_addresses(("VPN",)), ("10.8.0.2",))
            self.assertEqual(mdns.lan_addresses(bind="127.0.0.1"), ())
            self.assertEqual(mdns.lan_addresses(bind="192.168.1.7"), ("192.168.1.7",))


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_tls_protocol_name_registers_with_real_zeroconf(self):
        # Do not mock register_service: its strict length check caused the live
        # BadTypeInNameException that the mocked lifecycle tests missed.
        import uuid
        identity = str(uuid.uuid4())
        advertiser = mdns.Advertiser(tls_endpoint=lambda: ('0.0.0.0', 9443))
        try:
            with patch.object(mdns, 'lan_addresses', return_value=('127.0.0.1',)), patch.object(mdns, 'interface_signature', return_value=('test-loopback',)):
                await advertiser.reconcile(identity, mdns.installation_hostname(identity))
            found = await advertiser.zc.async_get_service_info(mdns.TLS_SERVICE_TYPE, advertiser.info.name, timeout=1000)
            self.assertIsNotNone(found)
            self.assertEqual(found.port, 9443)
            self.assertEqual(found.properties[b'id'].decode(), identity)
        finally:
            await advertiser.withdraw()

    async def test_ready_port_txt_and_rebuild(self):
        instances = []
        def factory(**kwargs):
            async def register(info, **options):
                future = asyncio.get_running_loop().create_future()
                future.set_result(None)
                return future
            zc = SimpleNamespace(async_register_service=AsyncMock(side_effect=register), async_close=AsyncMock(), interfaces=kwargs["interfaces"])
            instances.append(zc)
            return zc
        advertiser = mdns.Advertiser()
        identity = "8ead767e-f2ce-4514-a4c3-5bdbb5b9550d"
        server = mdns.installation_hostname(identity)
        with patch.object(mdns, "AsyncZeroconf", side_effect=factory), patch.object(mdns, "listener", return_value=("0.0.0.0", 20200)), patch.object(mdns, "lan_addresses", return_value=("192.168.1.7",)) as addresses:
            await advertiser.reconcile(identity, server)
            self.assertEqual(advertiser.info.port, 20200)
            self.assertEqual(advertiser.info.server, server)
            self.assertEqual(advertiser.info.type, "_orion-router-tls._tcp.local.")
            self.assertEqual(instances[0].async_register_service.await_count, 1)
            self.assertNotEqual(advertiser.info.port, 80)
            self.assertNotEqual(advertiser.info.server, "orionrouter.local.")
            self.assertIn(identity, advertiser.info.name)
            self.assertEqual(set(advertiser.info.properties), {b"id", b"name", b"path", b"version", b"v", b"scheme"})
            for key, value in {b"id": identity.encode(), b"name": mdns.display_name().encode(), b"path": b"/v1", b"version": mdns.config.APP_VERSION.encode()}.items():
                self.assertEqual(advertiser.info.properties[key], value)
            await advertiser.reconcile(identity, server)
            self.assertEqual(len(instances), 1)
            with patch.object(mdns, "interface_signature", return_value=("new-interface",)):
                await advertiser.reconcile(identity, server)
            instances[0].async_close.assert_awaited_once()
            addresses.return_value = ("192.168.1.8",)
            await advertiser.reconcile(identity, server)
            instances[1].async_close.assert_awaited_once()
            self.assertEqual(instances[2].interfaces, ["192.168.1.8"])
            addresses.return_value = ()
            await advertiser.reconcile(identity, server)
            instances[2].async_close.assert_awaited_once()
            self.assertIsNone(advertiser.zc)

    async def test_no_listener_no_advertisement(self):
        with patch.object(mdns, "listener", return_value=None), patch.object(mdns, "AsyncZeroconf") as factory:
            await mdns.Advertiser().reconcile("id", "orionrouter-test-installation.local.")
            factory.assert_not_called()

    async def test_disabled_and_container(self):
        for enabled, in_container in ((False, False), (True, True)):
            with patch.object(mdns.config, "MDNS_ENABLED", enabled), patch.object(mdns.config, "MDNS_CONTAINER_HOST_NETWORK", False), patch.object(mdns, "container", return_value=in_container):
                advertiser = mdns.Advertiser()
                advertiser.start()
                self.assertIsNone(advertiser.task)

    async def test_failure_retries_and_shutdown_closes(self):
        advertiser = mdns.Advertiser()
        advertiser.reconcile = AsyncMock(side_effect=[OSError("temporary"), None])
        advertiser.withdraw = AsyncMock()
        attempted = asyncio.Event()
        async def sleep(seconds):
            if advertiser.reconcile.await_count >= 2:
                attempted.set()
                await asyncio.Future()
        with patch.object(mdns, "router_id", return_value="8ead767e-f2ce-4514-a4c3-5bdbb5b9550d"), patch.object(mdns.asyncio, "sleep", side_effect=sleep):
            advertiser.task = asyncio.create_task(advertiser.run())
            await asyncio.wait_for(attempted.wait(), 2)
            await advertiser.close()
        self.assertEqual(advertiser.reconcile.await_count, 2)
        self.assertEqual(advertiser.withdraw.await_count, 2)


if __name__ == "__main__":
    unittest.main()
