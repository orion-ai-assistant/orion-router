"""Hub delegation, private credentials and PostgreSQL retry/limit regressions."""
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
import httpx

from api import hubs
from core import config
from core.dependencies import invalidate_vkey_cache
from core.router.routing_services import ProviderKeyPool
from core.security import decrypt
from core.tls_server import _TLSApplication
from database import db_manager


class PersonalKeyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        policy = patch("core.key_policy.eligible_ids", AsyncMock(return_value={"personal-id"}))
        policy.start(); self.addCleanup(policy.stop)
    async def test_personal_provider_key_does_not_enter_shared_pool(self):
        with patch.object(db_manager, 'fetchrow', AsyncMock(return_value={'id':'personal-id','api_key': 'personal', 'is_active':True})), patch.object(
            db_manager, 'get_active_provider_keys', AsyncMock()) as shared:
            self.assertEqual(await ProviderKeyPool().get_keys_for_provider('openrouter', 'sk-orion-user', key_id='user'), [('personal', 'personal-id')])
        shared.assert_not_awaited()

    async def test_other_user_without_personal_key_uses_only_shared_credentials(self):
        with patch.object(db_manager, 'fetchrow', AsyncMock(return_value=None)) as lookup, patch.object(
            db_manager, 'get_active_provider_keys', AsyncMock(return_value=[])):
            result = await ProviderKeyPool(SimpleNamespace(provider_keys={'openrouter': 'shared'})).get_keys_for_provider(
                'openrouter', 'sk-orion-other', key_id='other')
        self.assertEqual(result, [])
        self.assertEqual(lookup.await_args.args[1:], ('other', 'openrouter'))

    async def test_unreadable_personal_key_never_falls_back_to_shared_billing(self):
        with patch.object(db_manager, 'fetchrow', AsyncMock(return_value={'id':'personal-id','api_key': 'gAAAAA-broken','is_active':True})), patch.object(
            db_manager, 'get_active_provider_keys', AsyncMock()) as shared:
            with self.assertRaises(HTTPException):
                await ProviderKeyPool().get_keys_for_provider('openrouter', key_id='user')
        shared.assert_not_awaited()

    async def test_tls_required_and_limited_hub_token_cannot_enroll(self):
        app = FastAPI(); app.include_router(hubs.router)
        with patch('core.security.check_admin_secret', AsyncMock(return_value=False)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://router') as client:
                response = await client.post('/api/v1/hubs/enroll', json={'id': str(uuid4()), 'name': 'PC', 'token': 'hub-orion-' + 'a' * 43})
                self.assertEqual(response.status_code, 403)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_TLSApplication(app)), base_url='https://router') as client:
                response = await client.post('/api/v1/hubs/enroll', headers={'x-admin-key': 'hub-orion-' + 'a' * 43},
                    json={'id': str(uuid4()), 'name': 'PC', 'token': 'hub-orion-' + 'a' * 43})
                self.assertEqual(response.status_code, 401)


class PostgreSQLHubTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            self.conn = await asyncpg.connect(db_manager.get_postgres_url(), timeout=2)
        except Exception:
            self.skipTest('Local PostgreSQL is unavailable')
        self.transaction = self.conn.transaction()
        await self.transaction.start()
        self.addAsyncCleanup(self.conn.close)
        async def rollback():
            await self.transaction.rollback()
        self.addAsyncCleanup(rollback)
        schema = 'orion_test_' + uuid4().hex
        await self.conn.execute('CREATE SCHEMA ' + schema)
        await self.conn.execute('SET LOCAL search_path TO ' + schema + ', public')
        await db_manager._ensure_tables(self.conn)
        await db_manager._ensure_tables(self.conn)
        for name in ('execute', 'fetch', 'fetchrow'):
            p = patch.object(db_manager, name, getattr(self.conn, name)); p.start(); self.addCleanup(p.stop)
        p = patch.object(config, 'ENCRYPTION_KEY', Fernet.generate_key().decode()); p.start(); self.addCleanup(p.stop)
        invalidate_vkey_cache(); self.addCleanup(invalidate_vkey_cache)
        self.app = FastAPI(); self.app.include_router(hubs.router)
        self.app.state.dynamic_router = SimpleNamespace(get_capabilities=lambda: {'openrouter': {}, 'local': {}})
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=_TLSApplication(self.app)), base_url='https://router')
        self.addAsyncCleanup(self.client.aclose)
        self.hub = str(uuid4()); self.subject = str(uuid4())
        self.token = 'hub-orion-' + 'a' * 43; self.key = 'sk-orion-' + 'b' * 43
        with patch('core.security.check_admin_secret', AsyncMock(return_value=True)):
            response = await self.client.post('/api/v1/hubs/enroll', headers={'x-admin-key': 'password'},
                json={'id': self.hub, 'name': 'PC', 'token': self.token})
        self.assertEqual(response.status_code, 200)

    async def create_account(self, subject=None, key=None):
        return await self.client.post('/api/v1/hubs/accounts', headers={'x-orion-hub-key': self.token},
            json={'subject_id': subject or self.subject, 'name': 'user', 'key': key or self.key})

    async def test_retry_preserves_budget_usage_and_deactivation(self):
        first = await self.create_account(); self.assertEqual(first.status_code, 200)
        identifier = first.json()['id']
        await self.conn.execute('UPDATE router_virtual_keys SET budget=5,used_amount=3,is_active=false WHERE id=$1', identifier)
        second = await self.create_account()
        self.assertEqual(first.json(), second.json())
        row = await self.conn.fetchrow('SELECT budget,used_amount,is_active FROM router_virtual_keys WHERE id=$1', identifier)
        self.assertEqual((float(row['budget']), float(row['used_amount']), row['is_active']), (5, 3, False))
        conflict = await self.create_account(key='sk-orion-' + 'c' * 43)
        self.assertEqual(conflict.status_code, 409)

    async def test_hub_catalog_works_without_admin_password_and_only_allows_catalog_sections(self):
        headers = {'x-orion-hub-key': self.token}
        models = await self.client.get('/api/v1/hubs/catalog/models', headers=headers)
        groups = await self.client.get('/api/v1/hubs/catalog/model-groups', headers=headers)
        self.assertEqual(models.status_code, 200)
        self.assertEqual(groups.status_code, 200)
        self.assertTrue(models.json()['models'])
        self.app.state.dynamic_router.tts_providers = {}
        voices = await self.client.get('/api/v1/hubs/catalog/voices', headers=headers)
        self.assertEqual(voices.json(), {'voices': {}})
        forbidden = await self.client.get('/api/v1/hubs/catalog/provider-keys', headers=headers)
        self.assertEqual(forbidden.status_code, 404)

    async def test_account_uses_router_policy_and_cannot_choose_its_own_budget(self):
        await self.conn.execute('UPDATE router_hubs SET user_budget=2 WHERE id=$1', self.hub)
        response = await self.client.post('/api/v1/hubs/accounts', headers={'x-orion-hub-key': self.token},
            json={'subject_id': self.subject, 'name': 'user', 'key': self.key, 'budget': 0})
        identifier = response.json()['id']
        self.assertEqual(await self.conn.fetchval('SELECT budget FROM router_virtual_keys WHERE id=$1', identifier), 2)
        await self.conn.execute('UPDATE router_virtual_keys SET used_amount=2 WHERE id=$1', identifier)
        over_budget = await self.client.get('/api/v1/hubs/providers', headers={'Authorization': 'Bearer ' + self.key})
        self.assertEqual(over_budget.status_code, 402)

    async def test_private_provider_is_encrypted_isolated_and_used_for_routing(self):
        first = await self.create_account()
        second = await self.create_account(str(uuid4()), 'sk-orion-' + 'c' * 43)
        response = await self.client.put('/api/v1/hubs/providers/openrouter', headers={'Authorization': 'Bearer ' + self.key},
            json={'api_key': 'provider-private'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('provider-private', response.text)
        stored = await self.conn.fetchval('SELECT api_key FROM router_user_provider_keys WHERE key_id=$1', first.json()['id'])
        self.assertNotEqual(stored, 'provider-private'); self.assertEqual(decrypt(stored), 'provider-private')
        mine = await self.client.get('/api/v1/hubs/providers', headers={'Authorization': 'Bearer ' + self.key})
        other = await self.client.get('/api/v1/hubs/providers', headers={'Authorization': 'Bearer sk-orion-' + 'c' * 43})
        self.assertEqual(mine.json()['configured'], ['openrouter']); self.assertEqual(other.json()['configured'], [])
        pool = ProviderKeyPool(SimpleNamespace(provider_keys={'openrouter': 'shared'}))
        self.assertEqual(await pool.get_keys_for_provider('openrouter', key_id=first.json()['id']), [('provider-private', await self.conn.fetchval('SELECT id FROM router_user_provider_keys WHERE key_id=$1', first.json()['id']))])
        self.assertEqual(await pool.get_keys_for_provider('openrouter', key_id=second.json()['id']), [])

    async def test_shared_router_keeps_two_hubs_distinct_and_respects_revocation(self):
        first = await self.create_account()
        self.hub = str(uuid4()); self.token = 'hub-orion-' + 'd' * 43
        with patch('core.security.check_admin_secret', AsyncMock(return_value=True)):
            await self.client.post('/api/v1/hubs/enroll', headers={'x-admin-key': 'password'},
                json={'id': self.hub, 'name': 'PC', 'token': self.token})
        self.key = 'sk-orion-' + 'e' * 43
        second = await self.create_account()
        self.assertNotEqual(first.json()['id'], second.json()['id'])
        await self.conn.execute('UPDATE router_hubs SET is_active=false WHERE id=$1', self.hub)
        response = await self.client.get('/api/v1/hubs/providers', headers={'Authorization': 'Bearer ' + self.key})
        self.assertEqual(response.status_code, 403)
        self.assertEqual((await self.create_account()).status_code, 401)
