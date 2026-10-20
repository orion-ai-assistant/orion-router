"""The Router's start path: nothing slow before readiness that readiness does not need, no check weakened."""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core import lifespan as lifespan_module
from core import tts_archive

NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


class EncoderCheckTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_does_not_wait_for_the_encoder_check(self):
        release, finished = threading.Event(), threading.Event()

        def slow_check():
            release.wait(10)
            finished.set()
            return "ffmpeg version test"

        db = MagicMock(init_db=AsyncMock(), upsert_pricing=AsyncMock(), get_all_pricing=AsyncMock(return_value={}),
                       close_db=AsyncMock(), fetchrow=AsyncMock(return_value=None), get_config=AsyncMock(return_value={}))
        listener = MagicMock(start=AsyncMock(), close=AsyncMock())
        advertiser = MagicMock(close=AsyncMock())
        with ExitStack() as stack, patch.dict(os.environ, {"ORION_NO_BANNER": "1"}):
            for target, value in (
                ("core.lifespan.db_manager", db),
                ("core.lifespan.DynamicLLMRouter", MagicMock(return_value=MagicMock(tts_providers={}))),
                ("core.lifespan.load_model_catalog", MagicMock(return_value={"models": []})),
                ("core.lifespan.close_http_clients", AsyncMock()),
                ("core.lifespan.close_gemini_clients", AsyncMock()),
                ("core.windows_asyncio.install_reset_cleanup", MagicMock()),
                ("core.tts_archive.check_runtime", slow_check),
                ("core.tts_archive.close_archives", AsyncMock()),
                ("core.tls_identity.load_identity", MagicMock(return_value=SimpleNamespace(id="id", fp="fp"))),
                ("core.mdns.router_id", MagicMock(return_value="id")),
                ("core.local_installation.refresh_managed_installation", MagicMock()),
                ("core.dependencies.prewarm_vkey_cache", AsyncMock()),
                ("core.tls_server.LocalHTTPListener", MagicMock(return_value=listener)),
                ("core.mdns.Advertiser", MagicMock(return_value=advertiser)),
            ):
                stack.enter_context(patch(target, value))
            try:
                async with lifespan_module.lifespan(SimpleNamespace(state=SimpleNamespace())):
                    # Started (the listeners are up) while the check is still running.
                    listener.start.assert_awaited_once()
                    await asyncio.sleep(.2)
                    self.assertFalse(finished.is_set())
                    release.set()
                    for _ in range(100):
                        if finished.is_set():
                            break
                        await asyncio.sleep(.02)
                    self.assertTrue(finished.is_set())  # It still runs: diagnostics are kept.
            finally:
                release.set()

    def test_one_ffmpeg_run_reports_version_and_encoders(self):
        calls = []

        def run(command, **options):
            calls.append(command[1:])
            if command[1:] == ["-encoders"]:
                return SimpleNamespace(stdout=" A....D libopus  libopus Opus\n",
                                       stderr="ffmpeg version 9.0 Copyright\n  built with gcc\n")
            return SimpleNamespace(stdout=b"", stderr=b"")

        with patch("core.tts_archive.subprocess.run", side_effect=run):
            self.assertEqual(tts_archive._check_runtime(), "ffmpeg version 9.0 Copyright")
        self.assertCountEqual(calls, [["-encoders"], ["-version"]])

    def test_encoder_check_still_requires_libopus_ffprobe_and_a_version(self):
        def run_with(stdout, stderr, probe=None):
            def run(command, **options):
                if command[1:] == ["-version"]:
                    if probe:
                        raise probe
                    return SimpleNamespace(stdout=b"", stderr=b"")
                return SimpleNamespace(stdout=stdout, stderr=stderr)
            return run

        cases = (
            (run_with(" A....D aac\n", "ffmpeg version 9.0\n"), RuntimeError, "libopus"),
            (run_with(" A....D libopus\n", ""), RuntimeError, "version"),
            (run_with(" A....D libopus\n", "ffmpeg version 9.0\n",
                      subprocess.CalledProcessError(1, "ffprobe")), subprocess.CalledProcessError, ""),
        )
        for run, error, message in cases:
            with self.subTest(message=message), patch("core.tts_archive.subprocess.run", side_effect=run):
                with self.assertRaisesRegex(error, message):
                    tts_archive._check_runtime()


class SupervisorImportTest(unittest.TestCase):
    def test_supervisor_does_not_import_the_backend_stack(self):
        # The banner lives in core/banner.py: importing core.lifespan (FastAPI, database, providers) cost the
        # supervisor ~0.8 s on every start.
        probe = ("import sys; sys.argv = ['prod.py']; import bin.prod; "
                 "loaded = [name for name in ('core.lifespan', 'fastapi', 'database') if name in sys.modules]; "
                 "print('loaded=' + ','.join(loaded))")
        result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True,
                                timeout=60, **NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "loaded=")


@unittest.skipUnless((ROOT / "tools/pgsql/bin").is_dir() or os.name != "nt", "portable PostgreSQL not installed")
class DatabaseSetupTest(unittest.TestCase):
    """setup_db_and_user against a real throwaway cluster: one psql session, idempotent, failures still fail."""

    @classmethod
    def setUpClass(cls):
        from bin import common
        cls.common = common
        cls.directory = Path(tempfile.mkdtemp(prefix="orion-router-setup-"))
        cls.data = cls.directory / "data"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        subprocess.run([str(common.INITDB), "-D", str(cls.data), "-U", "router_user", "--auth=trust",
                        "--locale=C", "-E", "UTF8"], check=True, capture_output=True, timeout=120, **NO_WINDOW)
        subprocess.run([str(common.PG_CTL), "start", "-D", str(cls.data), "-l", str(cls.directory / "server.log"),
                        "-o", f"-p {cls.port}", "-w", "-t", "60"], check=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, **NO_WINDOW)

    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(cls.common.PG_CTL), "stop", "-D", str(cls.data), "-m", "fast", "-w"],
                       capture_output=True, timeout=60, **NO_WINDOW)
        import shutil
        shutil.rmtree(cls.directory, ignore_errors=True)

    def query(self, sql):
        result = subprocess.run([str(self.common.PSQL), "-h", "127.0.0.1", "-p", str(self.port), "-U", "router_user",
                                 "-d", "postgres", "-w", "-X", "-At", "-c", sql],
                                capture_output=True, text=True, timeout=30, **NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_creates_the_database_once_and_sets_the_password(self):
        calls = []
        real_run = self.common.run

        def counted(command, **options):
            calls.append(command)
            return real_run(command, **options)

        with patch.object(self.common, "run", side_effect=counted):
            self.common.setup_db_and_user("router_user", "it's secret", self.port, "orion_router_setup")
            self.common.setup_db_and_user("router_user", "it's secret", self.port, "orion_router_setup")
        self.assertEqual(len(calls), 2)  # One psql per setup, whether or not the database existed.
        self.assertEqual(self.query("SELECT count(*) FROM pg_database WHERE datname = 'orion_router_setup'"), "1")
        self.assertEqual(self.query("SELECT pg_get_userbyid(datdba) FROM pg_database "
                                    "WHERE datname = 'orion_router_setup'"), "router_user")
        self.assertEqual(self.query("SELECT rolpassword IS NOT NULL FROM pg_authid "
                                    "WHERE rolname = 'router_user'"), "t")

    def test_a_failing_statement_fails_the_setup(self):
        from core.process_lifecycle import LifecycleError
        with self.assertRaisesRegex(LifecycleError, "setup failed"):
            self.common.setup_db_and_user("missing_role", "secret", self.port, "orion_router_missing")
        self.assertEqual(self.query("SELECT count(*) FROM pg_database WHERE datname = 'orion_router_missing'"), "0")
        with self.assertRaisesRegex(LifecycleError, "Invalid database identifier"):
            self.common.setup_db_and_user("router_user", "secret", self.port, "bad-name")


if __name__ == "__main__":
    unittest.main()
