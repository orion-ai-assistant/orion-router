"""Transactional dashboard forms against an isolated rollback PostgreSQL schema."""
import unittest
from uuid import uuid4
import test_key_policy as fixtures
from core.key_policy import eligible_ids
from core.security import decrypt

class DashboardKeyFormTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.PolicyTests.asyncSetUp
    create_account = fixtures.PolicyTests.create_account
    shared = fixtures.PolicyTests.shared

    async def test_virtual_create_permissions_are_saved_without_secret_echo(self):
        secret='sk-orion-'+'e'*64
        response=await self.client.post('/dashboard/api/keys',headers={'x-admin-key':'admin'},json={
            'name':'manual','budget':2,'api_key':secret,'access':{'mode':'only_selected','selected':[self.a]}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(secret,response.text)
        identifier=response.json()['id']
        self.assertEqual(await eligible_ids(identifier,'openrouter'),{self.a})
        invalid=await self.client.post('/dashboard/api/keys',headers={'x-admin-key':'admin'},json={
            'name':'must-rollback','api_key':'sk-orion-'+'f'*64,'access':{'mode':'only_selected','selected':['missing']}})
        self.assertEqual(invalid.status_code,422,invalid.text)
        self.assertFalse(await self.conn.fetchval("SELECT EXISTS(SELECT 1 FROM router_virtual_keys WHERE name='must-rollback')"))

    async def test_virtual_update_rolls_back_fields_if_permission_is_invalid(self):
        response=await self.client.put('/dashboard/api/keys/'+self.x,headers={'x-admin-key':'admin'},json={
            'name':'changed','access':{'mode':'only_selected','selected':['missing']}})
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(await self.conn.fetchval('SELECT name FROM router_virtual_keys WHERE id=$1',self.x),'user')
        response=await self.client.put('/dashboard/api/keys/'+self.x,headers={'x-admin-key':'admin'},json={
            'name':'changed','access':{'mode':'only_selected','selected':[self.a]}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(await eligible_ids(self.x,'openrouter'),{self.a})

    async def test_edit_discards_orphaned_personal_permission_ids(self):
        headers={'x-admin-key':'admin'}
        response=await self.client.post('/dashboard/api/personal-provider-keys',headers=headers,json={
            'provider':'openrouter','key_id':self.x,'api_key':'old-personal-fixture'})
        self.assertEqual(response.status_code,200,response.text)
        identifier=response.json()['id']
        await self.conn.execute("UPDATE router_virtual_keys SET provider_key_mode='only_selected' WHERE id=$1",self.x)
        await self.conn.execute('INSERT INTO router_virtual_key_access(virtual_key_id,provider_key_id) VALUES($1,$2)',self.x,identifier)
        await self.conn.execute('DELETE FROM router_user_provider_keys WHERE id=$1',identifier)
        access=(await self.client.get('/dashboard/api/keys/'+self.x+'/access',headers=headers)).json()
        self.assertNotIn(identifier,access['selected'])
        response=await self.client.put('/dashboard/api/keys/'+self.x,headers=headers,json={
            'name':'renamed','access':{'mode':access['mode'],'selected':access['selected']}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(await eligible_ids(self.x,'openrouter'),set())

    async def test_provider_create_and_edit_use_same_permission_transaction(self):
        response=await self.client.post('/dashboard/api/provider-key-pool',headers={'x-admin-key':'admin'},json={
            'provider':'openrouter','label':'limited','api_key':'upstream-fixture','access':{'mode':'selected','selected':[self.x]}})
        self.assertEqual(response.status_code,200,response.text)
        identifier=response.json()['id']
        self.assertIn(identifier,await eligible_ids(self.x,'openrouter'))
        self.assertNotIn(identifier,await eligible_ids(self.y,'openrouter'))
        response=await self.client.put('/dashboard/api/provider-key-pool/'+identifier,headers={'x-admin-key':'admin'},json={
            'label':'must-rollback','access':{'mode':'selected','selected':['missing']}})
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(await self.conn.fetchval('SELECT label FROM router_provider_key_pool WHERE id=$1',identifier),'limited')
        response=await self.client.put('/dashboard/api/provider-key-pool/'+identifier,headers={'x-admin-key':'admin'},json={
            'access':{'mode':'selected','selected':[]}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(identifier,await eligible_ids(self.x,'openrouter'))

    async def test_admin_personal_create_masking_priority_and_ownership(self):
        response=await self.client.post('/dashboard/api/personal-provider-keys',headers={'x-admin-key':'admin'},json={
            'provider':'openrouter','key_id':self.x,'api_key':'personal-fixture-secret','priority':3})
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn('personal-fixture-secret',response.text)
        identifier=response.json()['id']
        self.assertIn(identifier,await eligible_ids(self.x,'openrouter'))
        self.assertNotIn(identifier,await eligible_ids(self.y,'openrouter'))
        stored=await self.conn.fetchval('SELECT api_key FROM router_user_provider_keys WHERE id=$1',identifier)
        self.assertEqual(decrypt(stored),'personal-fixture-secret')
        listing=await self.client.get('/dashboard/api/personal-provider-keys',headers={'x-admin-key':'admin'})
        self.assertNotIn('personal-fixture-secret',listing.text)
        self.assertNotIn('api_key',listing.json()['keys'][0])
        summary=await self.client.get('/api/v1/hubs/providers',headers={'Authorization':'Bearer '+self.key})
        self.assertEqual(summary.status_code,200,summary.text)
        self.assertEqual(summary.json()['personal_keys'][0]['masked_key'],'••••cret')
        self.assertNotIn('personal-fixture-secret',summary.text)
        self.assertNotIn(stored,summary.text)
        self.assertNotIn('api_key',summary.json()['personal_keys'][0])

        response=await self.client.put('/dashboard/api/personal-provider-keys/'+identifier,headers={'x-admin-key':'admin'},json={'priority':1,'is_active':False,'label':'renamed','api_key':''})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['priority'],1)
        duplicate=await self.client.post('/dashboard/api/personal-provider-keys',headers={'x-admin-key':'admin'},json={
            'provider':'openrouter','key_id':self.x,'api_key':'replacement'})
        self.assertEqual(duplicate.status_code,409,duplicate.text)
        self.assertEqual(decrypt(await self.conn.fetchval('SELECT api_key FROM router_user_provider_keys WHERE id=$1',identifier)),'personal-fixture-secret')
        self.assertFalse(await self.conn.fetchval('SELECT is_active FROM router_user_provider_keys WHERE id=$1',identifier))

    async def test_new_personal_endpoint_requires_admin_and_valid_owner(self):
        body={'provider':'openrouter','key_id':self.x,'api_key':'fixture'}
        response=await self.client.post('/dashboard/api/personal-provider-keys',headers={'x-admin-key':self.key},json=body)
        self.assertEqual(response.status_code,401)
        body['key_id']=str(uuid4())
        response=await self.client.post('/dashboard/api/personal-provider-keys',headers={'x-admin-key':'admin'},json=body)
        self.assertEqual(response.status_code,422)

if __name__=='__main__':unittest.main()
