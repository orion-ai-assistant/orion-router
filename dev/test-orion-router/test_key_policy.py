"""Permission, isolation and all-history reporting regressions (rollback schemas)."""
import asyncio
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import test_hub_accounts as fixtures
from api import admin
from api.key_management import usage, save_virtual_access, edit_personal
from core.key_policy import eligible_ids, replace_rule, authorize_attempt, selected_upstream
from core.router.routing_services import ProviderKeyPool
from core.router.telemetry import TelemetryService
from core.secret_guard import redact
from core.security import encrypt
from database import db_manager


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    create_account = fixtures.PostgreSQLHubTests.create_account

    async def asyncSetUp(self):
        await fixtures.PostgreSQLHubTests.asyncSetUp(self)
        p = patch.object(db_manager, 'fetchval', self.conn.fetchval); p.start(); self.addCleanup(p.stop)
        @asynccontextmanager
        async def acquire():
            yield self.conn
        pool = SimpleNamespace(acquire=acquire)
        p = patch.object(db_manager, 'get_db_pool', AsyncMock(return_value=pool)); p.start(); self.addCleanup(p.stop)
        self.app.include_router(admin.router)
        p = patch('core.security.check_admin_secret', AsyncMock(side_effect=lambda value: value == 'admin'))
        p.start(); self.addCleanup(p.stop)
        p = patch('core.mdns.lan_addresses', return_value=['192.168.1.22']); p.start(); self.addCleanup(p.stop)
        self.x = (await self.create_account()).json()['id']
        self.y = (await self.create_account(str(uuid4()), 'sk-orion-'+'c'*43)).json()['id']
        self.z = (await self.create_account(str(uuid4()), 'sk-orion-'+'d'*43)).json()['id']
        self.a = await self.shared('A')
        self.b = await self.shared('B')
        selected_upstream.set((None,None))

    async def test_denied_credentials_never_reach_any_operation(self):
        from core.router.route_types import RoutePlan
        from core.router.runners.chat import ChatRunner
        from core.router.runners.embeddings import EmbeddingsRunner
        from core.router.runners.stt import STTRunner
        from core.router.runners.tts import TTSRunner
        from dynamic_router import DynamicLLMRouter
        from fastapi import HTTPException
        await replace_rule('virtual',self.x,'only_selected',[])
        resolver=SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan.direct('test','openrouter')))
        pool=ProviderKeyPool(SimpleNamespace(provider_keys={'openrouter':'env-bypass'}))
        telemetry=AsyncMock()
        embed=SimpleNamespace(generate_embeddings=AsyncMock())
        stt=SimpleNamespace(generate_transcription=AsyncMock())
        tts=SimpleNamespace(generate_speech=AsyncMock())
        registry=SimpleNamespace(embed_providers={'openrouter':embed},stt_providers={'openrouter':stt},tts_providers={'openrouter':tts})
        for runner,args in [(EmbeddingsRunner(registry,resolver,pool,telemetry).run_embeddings,('openrouter','test','hello')),
                            (STTRunner(registry,resolver,pool,telemetry).run_transcription,('openrouter','test',b'audio')),
                            (TTSRunner(registry,resolver,pool,telemetry).run_speech,('openrouter','test','hello'))]:
            with self.assertRaises(HTTPException) as error:
                await runner(*args,key_id=self.x)
            self.assertEqual(error.exception.status_code,403)
        embed.generate_embeddings.assert_not_awaited();stt.generate_transcription.assert_not_awaited();tts.generate_speech.assert_not_awaited()
        chat=SimpleNamespace(stream_chat=AsyncMock())
        registry.chat_providers={'openrouter':chat}
        chunks=[c async for c in ChatRunner(registry,resolver,pool,telemetry).run_combo('openrouter','test',[],key_id=self.x)]
        self.assertIn('Router yöneticisine',''.join(chunks));chat.stream_chat.assert_not_called()
        file=SimpleNamespace(upload_file=AsyncMock())
        fake=SimpleNamespace(file_providers={'openrouter':file},key_pool=pool)
        with self.assertRaises(HTTPException):
            await DynamicLLMRouter.upload_file(fake,'openrouter',b'file','text/plain','fixture',key_id=self.x)
        file.upload_file.assert_not_awaited()

    async def shared(self, label):
        return await self.conn.fetchval('INSERT INTO router_provider_key_pool(provider,label,api_key) VALUES($1,$2,$3) RETURNING id', 'openrouter', label, encrypt('secret-'+label))

    async def test_duplicate_labels_and_one_time_legacy_migration_preserve_revocation(self):
        duplicate = await self.shared('A')
        self.assertNotEqual(duplicate,self.a)
        await self.conn.execute("INSERT INTO router_configs(config_key,config_value) VALUES('provider_api_keys',$1::jsonb)",'{"legacy":"legacy-fixture"}')
        await db_manager._migrate_legacy_provider_keys(self.conn)
        identifier=await self.conn.fetchval("SELECT id FROM router_provider_key_pool WHERE provider='legacy'")
        await self.conn.execute("UPDATE router_provider_key_pool SET label='renamed',is_active=false,scope='selected' WHERE id=$1",identifier)
        await db_manager._migrate_legacy_provider_keys(self.conn)
        self.assertEqual(await self.conn.fetchval("SELECT count(*) FROM router_provider_key_pool WHERE provider='legacy'"),1)
        self.assertFalse(await self.conn.fetchval('SELECT is_active FROM router_provider_key_pool WHERE id=$1',identifier))

    async def test_missing_usage_and_distinct_speech_units_are_not_token_totals(self):
        service=TelemetryService()
        log_id=await service.create_processing_log(self.x,'openrouter','test','chat',{})
        await service.log_usage(self.x,'openrouter','test',None,log_id=log_id)
        row=await self.conn.fetchrow('SELECT cost,tokens_used FROM router_request_logs WHERE id=$1',log_id)
        self.assertIsNone(row['cost']);self.assertIsNone(row['tokens_used'])
        await service.log_usage(self.x,'local','local-stt',None,capability='stt',usage_unit='second',usage_amount=12)
        await service.log_usage(self.x,'openai','tts-1',{'prompt_tokens':50,'completion_tokens':0,'thoughts_tokens':0},capability='tts')
        report=await usage(key_id=self.x)
        buckets={r['capability']:r for r in report['totals']}
        self.assertIsNone(buckets['chat']['total'])
        self.assertEqual(buckets['stt']['usage_unit'],'second')
        self.assertEqual(buckets['stt']['usage_amount'],12)
        self.assertEqual(buckets['tts']['usage_unit'],'character')
        self.assertEqual(buckets['tts']['total'],50)

    async def test_layers_cannot_expand_each_other_and_revocation_is_immediate(self):
        await replace_rule('provider', self.a, 'selected', [self.x,self.y])
        await replace_rule('virtual', self.z, 'only_selected', [self.a])
        self.assertNotIn(self.a, await eligible_ids(self.z,'openrouter'))
        await replace_rule('virtual', self.x, 'only_selected', [self.a])
        self.assertEqual(await eligible_ids(self.x,'openrouter'), {self.a})
        new = await self.shared('new')
        self.assertNotIn(new, await eligible_ids(self.x,'openrouter'))
        await replace_rule('provider', self.a, 'selected', [])
        self.assertEqual(await eligible_ids(self.x,'openrouter'), set())
        await replace_rule('provider', self.a, 'all', [])
        self.assertEqual(await eligible_ids(self.x,'openrouter'), {self.a})
        await replace_rule('virtual', self.x, 'only_selected', [])
        self.assertEqual(await eligible_ids(self.x,'openrouter'), set())

    async def test_denied_primary_route_uses_only_authorized_fallback(self):
        from core.router.route_types import RoutePlan, ResolvedRoute
        from core.router.runners.embeddings import EmbeddingsRunner
        await replace_rule('provider',self.a,'selected',[])
        await replace_rule('provider',self.b,'selected',[])
        fallback_id = await self.conn.fetchval("INSERT INTO router_provider_key_pool(provider,label,api_key) VALUES('fallback','allowed',$1) RETURNING id",encrypt('fallback-fixture'))
        primary=SimpleNamespace(generate_embeddings=AsyncMock())
        fallback=SimpleNamespace(generate_embeddings=AsyncMock(return_value={'data':[], 'usage':{'prompt_tokens':1}}))
        registry=SimpleNamespace(embed_providers={'openrouter':primary,'fallback':fallback})
        resolver=SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(ResolvedRoute('openrouter','primary'),ResolvedRoute('fallback','alternative')))))
        telemetry=AsyncMock()
        await EmbeddingsRunner(registry,resolver,ProviderKeyPool(),telemetry).run_embeddings(None,'group','hello',key_id=self.x)
        await asyncio.sleep(0)
        primary.generate_embeddings.assert_not_called()
        self.assertEqual(fallback.generate_embeddings.await_args.kwargs['api_key'],'fallback-fixture')
        self.assertEqual(selected_upstream.get(),(fallback_id,'shared'))

    async def test_retry_rechecks_revoked_candidate_and_personal_failure_never_uses_shared(self):
        from core.router.route_types import RoutePlan
        from core.router.runners.embeddings import EmbeddingsRunner
        from fastapi import HTTPException
        async def first_fails(**kwargs):
            await replace_rule('provider',self.b,'selected',[])
            raise ValueError('invalid key')
        plugin=SimpleNamespace(generate_embeddings=AsyncMock(side_effect=first_fails))
        registry=SimpleNamespace(embed_providers={'openrouter':plugin})
        resolver=SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan.direct('test','openrouter')))
        runner=EmbeddingsRunner(registry,resolver,ProviderKeyPool(),AsyncMock())
        with self.assertRaises(HTTPException):
            await runner.run_embeddings('openrouter','test','hello',key_id=self.x)
        self.assertEqual(plugin.generate_embeddings.await_count,1)
        await self.client.put('/api/v1/hubs/providers/openrouter',headers={'Authorization':'Bearer '+self.key},json={'api_key':'bad-private-fixture'})
        plugin.generate_embeddings=AsyncMock(side_effect=ValueError('invalid key'))
        with self.assertRaises(RuntimeError):
            await runner.run_embeddings('openrouter','test','hello',key_id=self.x)
        self.assertEqual(plugin.generate_embeddings.await_count,1)
        self.assertEqual(plugin.generate_embeddings.await_args.kwargs['api_key'],'bad-private-fixture')

    async def test_deleted_account_permission_cannot_transfer_to_new_account(self):
        await replace_rule('provider', self.a, 'selected', [self.z])
        await self.conn.execute('DELETE FROM router_virtual_keys WHERE id=$1', self.z)
        recreated = (await self.create_account(str(uuid4()), 'sk-orion-'+'e'*43)).json()['id']
        self.assertNotIn(self.a, await eligible_ids(recreated,'openrouter'))

    async def test_shared_private_counts_and_no_other_user_metadata(self):
        await replace_rule('provider', self.a, 'selected', [self.x])
        await self.client.put('/api/v1/hubs/providers/openrouter',headers={'Authorization':'Bearer '+self.key},json={'api_key':'private-fixture'})
        response = await self.client.get('/api/v1/hubs/providers',headers={'Authorization':'Bearer '+self.key})
        self.assertEqual(response.json()['summary'],[{'provider':'openrouter','shared':1,'private':2}])
        self.assertEqual(response.json()['active_keys'],3)
        self.assertIn('192.168.1.22',response.json()['dashboard_url'])
        self.assertNotIn(self.a,response.text);self.assertNotIn(self.y,response.text)
        self.assertNotIn('private-fixture',response.text)

    async def test_personal_admin_update_disable_and_owner_cannot_reactivate(self):
        headers={'Authorization':'Bearer '+self.key}
        await self.client.put('/api/v1/hubs/providers/openrouter',headers=headers,json={'api_key':'private-fixture'})
        identifier = await self.conn.fetchval('SELECT id FROM router_user_provider_keys WHERE key_id=$1',self.x)
        response = await self.client.put('/dashboard/api/personal-provider-keys/'+identifier,headers={'x-admin-key':'admin'},json={'api_key':'admin-fixture','is_active':False})
        self.assertEqual(response.status_code,200);self.assertNotIn('admin-fixture',response.text)
        status = (await self.client.get('/api/v1/hubs/providers',headers=headers)).json()
        self.assertTrue(status['personal_keys'][0]['admin_updated'])
        self.assertFalse(status['personal_keys'][0]['is_active'])
        pool=ProviderKeyPool(SimpleNamespace(provider_keys={'openrouter':'global-fixture'}))
        self.assertEqual(await pool.get_keys_for_provider('openrouter',key_id=self.x),[])
        await self.client.put('/api/v1/hubs/providers/openrouter',headers=headers,json={'api_key':'owner-fixture'})
        self.assertEqual(await pool.get_keys_for_provider('openrouter',key_id=self.x),[])
        self.assertEqual((await self.client.delete('/api/v1/hubs/providers/openrouter',headers=headers)).status_code,403)

    async def test_admin_only_policy_and_personal_management(self):
        for path, body in [(f'/dashboard/api/keys/{self.x}/access',{'mode':'unrestricted'}),
                           (f'/dashboard/api/provider-key-pool/{self.a}/access',{'scope':'all'}),
                           ('/dashboard/api/personal-provider-keys/unknown',{'is_active':True})]:
            response=await self.client.put(path,headers={'x-admin-key':self.key},json=body)
            self.assertEqual(response.status_code,401)

    async def test_hub_deactivation_preserves_reconnect_decision(self):
        response=await self.client.put('/dashboard/api/hubs/'+self.hub,headers={'x-admin-key':'admin'},json={'is_active':False})
        self.assertEqual(response.status_code,200)
        self.assertEqual(await eligible_ids(self.x,'openrouter'),set())
        response=await self.client.post('/api/v1/hubs/enroll',headers={'x-admin-key':'admin'},json={'id':self.hub,'name':'PC','token':self.token})
        self.assertEqual(response.status_code,403)
        self.assertEqual((await self.create_account()).status_code,401)

    async def test_summary_and_catalog_obey_virtual_restriction(self):
        await replace_rule('virtual',self.x,'only_selected',[])
        headers={'Authorization':'Bearer '+self.key}
        summary=(await self.client.get('/api/v1/hubs/providers',headers=headers)).json()
        self.assertEqual(summary['active_keys'],0)
        catalog=(await self.client.get('/api/v1/hubs/account-catalog/models',headers=headers)).json()
        self.assertTrue(all(m['provider']=='local' for m in catalog['models']))
        pool=ProviderKeyPool(SimpleNamespace(provider_keys={'openrouter':'global-secret'}))
        self.assertEqual(await pool.get_keys_for_provider('openrouter','incoming-secret',key_id=self.x),[])
        self.assertEqual(await pool.get_keys_for_provider('local',key_id=self.x),[(None,None)])

    async def test_usage_over_100_boundaries_unknown_zero_units_and_deleted_history(self):
        await self.conn.execute('''INSERT INTO router_request_logs(key_id,recorded_key_id,recorded_hub_id,provider,requested_model,capability,tokens_used,prompt_tokens,completion_tokens,thoughts_tokens,cost,success,created_at,usage_unit)
            SELECT $1,$1,$2,'openrouter','test','chat',3,1,2,0,0.01,true,'2026-01-01T12:00:00Z','token' FROM generate_series(1,150)''',self.x,self.hub)
        await self.conn.execute("INSERT INTO router_request_logs(key_id,recorded_key_id,recorded_hub_id,provider,requested_model,capability,success,created_at) VALUES($1,$1,$2,'openrouter','test','chat',false,'2026-01-02T00:00:00Z')",self.x,self.hub)
        response=await self.client.get('/dashboard/api/usage',headers={'x-admin-key':'admin'},params={'key_id':self.x,'start':'2026-01-01T00:00:00Z','end':'2026-01-02T00:00:00Z'})
        self.assertEqual(response.status_code,200,response.text)
        total=response.json()['totals'][0]
        self.assertEqual(total['requests'],150);self.assertEqual(total['total'],450)
        self.assertEqual(total['thoughts'],0);self.assertEqual(total['missing_usage'],0)
        self.assertEqual(len(response.json()['daily']),1)
        await self.conn.execute('DELETE FROM router_virtual_keys WHERE id=$1',self.x)
        history=await usage(key_id=self.x,hub_id=self.hub)
        self.assertEqual(sum(r['requests'] for r in history['totals']),151)
        unknown=next(r for r in history['totals'] if r['usage_unit'] is None)
        self.assertIsNone(unknown['total']);self.assertEqual(unknown['missing_usage'],1)

    async def test_actual_selected_personal_id_and_source_survive_delete(self):
        await self.client.put('/api/v1/hubs/providers/openrouter',headers={'Authorization':'Bearer '+self.key},json={'api_key':'private-fixture'})
        value,identifier=(await ProviderKeyPool().get_keys_for_provider('openrouter',key_id=self.x))[0]
        await authorize_attempt(self.x,'openrouter',identifier,value)
        await TelemetryService().log_usage(self.x,'openrouter','test',{'prompt_tokens':0,'completion_tokens':0,'thoughts_tokens':0},response_json='"private-fixture"')
        row=await self.conn.fetchrow('SELECT * FROM router_request_logs ORDER BY id DESC LIMIT 1')
        self.assertEqual(row['upstream_key_id'],identifier);self.assertEqual(row['upstream_key_source'],'personal')
        self.assertEqual(row['recorded_key_id'],self.x);self.assertEqual(row['tokens_used'],0)
        self.assertNotIn('private-fixture',str(row['response_json']))
        await self.conn.execute('DELETE FROM router_user_provider_keys WHERE id=$1',identifier)
        report=await usage(upstream_key_id=identifier)
        self.assertEqual(report['totals'][0]['requests'],1)
