import asyncio
import json
import os
import sys
import tempfile
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import lifespan as lifespan_module
from core import mdns, update_gate


class AdmissionInPlaceTest(unittest.IsolatedAsyncioTestCase):
    """A candidate started quarantined keeps running once the helper opens admission."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.operation = str(uuid.uuid4())
        (self.root / "updates" / self.operation).mkdir(parents=True)
        (self.root / "updates/active.json").write_text(
            json.dumps({"schema": 1, "operation_id": self.operation}), encoding="utf-8")
        self.phase("health_check")
        env = patch.dict(os.environ, {"ORION_INSTALLATION_REGISTRY": str(self.root / "registry.json"),
                                      "ORION_NO_BANNER": "1"})
        env.start()
        self.addCleanup(env.stop)

    def phase(self, value):
        journal = self.root / "updates" / self.operation / "journal.json"
        journal.write_text(json.dumps({"schema": 1, "operation_id": self.operation, "phase": value}), encoding="utf-8")

    def patched_startup(self, stack, advertiser, warmup):
        db = MagicMock(init_db=AsyncMock(), upsert_pricing=AsyncMock(), get_all_pricing=AsyncMock(return_value={}),
                       close_db=AsyncMock())
        listener = MagicMock(start=AsyncMock(), close=AsyncMock())
        router = MagicMock(tts_providers={"gemini": SimpleNamespace(fetch_remote_voices=warmup)})
        db.fetchrow = AsyncMock(return_value=None)
        db.get_config = AsyncMock(side_effect=lambda key: {"gemini": "key"} if key == "provider_api_keys" else {})
        for target, value in (
            ("core.lifespan.db_manager", db),
            ("core.lifespan.DynamicLLMRouter", MagicMock(return_value=router)),
            ("core.lifespan.load_model_catalog", MagicMock(return_value={"models": []})),
            ("core.lifespan.close_http_clients", AsyncMock()),
            ("core.lifespan.close_gemini_clients", AsyncMock()),
            ("core.windows_asyncio.install_reset_cleanup", MagicMock()),
            ("core.tts_archive.check_runtime", MagicMock(return_value="test")),
            ("core.tts_archive.close_archives", AsyncMock()),
            ("core.tls_identity.load_identity", MagicMock(return_value=SimpleNamespace(id="id", fp="fp"))),
            ("core.mdns.router_id", MagicMock(return_value="id")),
            ("core.local_installation.refresh_managed_installation", MagicMock()),
            ("core.dependencies.prewarm_vkey_cache", AsyncMock()),
            ("core.tls_server.LocalHTTPListener", MagicMock(return_value=listener)),
            ("core.mdns.Advertiser", MagicMock(return_value=advertiser)),
        ):
            stack.enter_context(patch(target, value))

    async def test_mdns_and_voice_warmup_start_after_admission_opens(self):
        advertiser = mdns.Advertiser()
        advertiser.start = MagicMock()
        warmup = AsyncMock()
        with ExitStack() as stack:
            self.patched_startup(stack, advertiser, warmup)
            async with lifespan_module.lifespan(SimpleNamespace(state=SimpleNamespace())):
                await asyncio.sleep(.5)
                self.assertTrue(update_gate.blocked())
                advertiser.start.assert_not_called()
                warmup.assert_not_awaited()
                self.phase("completed")
                for _ in range(50):
                    if advertiser.start.called and warmup.await_count:
                        break
                    await asyncio.sleep(.05)
                advertiser.start.assert_called_once()
                warmup.assert_awaited_once_with(api_key="key")

    async def test_shutdown_while_quarantined_never_starts_mdns(self):
        advertiser = mdns.Advertiser()
        advertiser.start = MagicMock()
        warmup = AsyncMock()
        with ExitStack() as stack:
            self.patched_startup(stack, advertiser, warmup)
            async with lifespan_module.lifespan(SimpleNamespace(state=SimpleNamespace())):
                await asyncio.sleep(.3)
        self.assertIsNone(advertiser.task)
        advertiser.start.assert_not_called()
        warmup.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
