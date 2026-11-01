"""Port 9443 is reachable from the home network: no file outside the dashboard,
no default password, no cross-site callers."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.admin import router, db_manager
from core import config
from core.dependencies import verify_token_string
from core.security import hash_secret


def loopback(app):
    async def wrapped(scope, receive, send):
        await app(dict(scope, orion_loopback_listener=True), receive, send)
    return wrapped


class NetworkExposureTests(unittest.IsolatedAsyncioTestCase):
    async def get(self, path, *, local=False, headers=None):
        app = FastAPI()
        app.include_router(router)
        transport = httpx.ASGITransport(app=loopback(app) if local else app)
        async with httpx.AsyncClient(transport=transport, base_url='https://router') as client:
            return await client.get(path, headers=headers or {})

    async def test_dashboard_never_serves_files_outside_its_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'out'
            out.mkdir()
            (out / 'index.html').write_text('<html>panel</html>', encoding='utf-8')
            (out / 'app.js').write_text('ok', encoding='utf-8')
            (Path(folder) / 'secret.env').write_text('ADMIN_SECRET=x', encoding='utf-8')
            with patch('core.config.DASHBOARD_OUT_DIR', str(out)):
                self.assertEqual((await self.get('/dashboard/app.js')).text, 'ok')
                for path in ('/dashboard/..%2Fsecret.env', '/dashboard/..%2F..%2FREADME.md',
                             '/dashboard/C:/Windows/win.ini', '/dashboard/' + str(Path(folder) / 'secret.env')):
                    with self.subTest(path=path):
                        response = await self.get(path)
                        self.assertNotIn('ADMIN_SECRET', response.text)
                        self.assertEqual(response.status_code, 404)

    async def test_default_password_is_shown_only_on_this_pc(self):
        with patch.object(config, 'ADMIN_SECRET', 'orion'), \
                patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('orion'))):
            remote = (await self.get('/dashboard/api/settings/is-default-password')).json()
            local = (await self.get('/dashboard/api/settings/is-default-password', local=True)).json()
        self.assertEqual(remote, {'is_default': True, 'default_password': None})
        self.assertEqual(local, {'is_default': True, 'default_password': 'orion'})

    async def test_default_password_opens_admin_only_on_this_pc(self):
        with patch.object(config, 'ADMIN_SECRET', 'orion'), \
                patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('orion'))):
            app = FastAPI()
            app.include_router(router)
            for target, expected in ((app, 403), (loopback(app), 204)):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=target),
                                             base_url='https://router') as client:
                    response = await client.post('/dashboard/api/auth/login', headers={'X-Admin-Key': 'orion'})
                self.assertEqual(response.status_code, expected)
            with self.assertRaises(HTTPException) as refused:
                await verify_token_string('orion', {'orion_tls_listener': True})
            self.assertEqual(refused.exception.status_code, 401)
            self.assertEqual((await verify_token_string('orion', {'orion_loopback_listener': True}))['source'],
                             'system')

    async def test_a_changed_password_works_over_the_network(self):
        with patch.object(config, 'ADMIN_SECRET', 'orion'), \
                patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('long new secret'))):
            self.assertEqual((await verify_token_string('long new secret', {'orion_tls_listener': True}))['source'],
                             'system')

    def test_no_cross_site_cors_outside_development(self):
        source = (ROOT / 'main.py').read_text(encoding='utf-8')
        self.assertNotIn('allow_origins=["*"]', source)
        self.assertIn('if os.getenv("UVICORN_RELOAD"', source)


if __name__ == '__main__':
    unittest.main()
