"""Login validates the same admin secret without querying dashboard aggregates."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.admin import router, db_manager
from core.security import hash_secret


class AdminLoginTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, secret=None):
        app = FastAPI()
        app.include_router(router)
        headers = {'X-Admin-Key': secret} if secret is not None else {}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://router') as client:
            return await client.post('/dashboard/api/auth/login', headers=headers)

    async def test_valid_secret_does_not_wait_for_statistics(self):
        with patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('test-password'))), \
             patch.object(db_manager, 'fetchrow', AsyncMock(side_effect=AssertionError('stats queried'))) as rows, \
             patch.object(db_manager, 'fetchval', AsyncMock(side_effect=AssertionError('stats queried'))) as values:
            response = await self.request('test-password')
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b'')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            rows.assert_not_awaited()
            values.assert_not_awaited()

    async def test_wrong_or_missing_secret_is_rejected(self):
        with patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('test-password'))):
            self.assertEqual((await self.request()).status_code, 401)
            self.assertEqual((await self.request('wrong-password')).status_code, 401)

    async def test_encoded_admin_secret_uses_existing_verification(self):
        with patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('test+şifre'))):
            self.assertEqual((await self.request('test%2B%C5%9Fifre')).status_code, 204)


if __name__ == '__main__':
    unittest.main()
