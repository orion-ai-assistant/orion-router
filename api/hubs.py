"""Scoped Hub delegation and private provider credentials; all writes require TLS."""
import hashlib
import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.dependencies import authenticate_request, verify_admin
from core.security import encrypt, decrypt
from core.secret_guard import SecretRoute
from database import db_manager

router = APIRouter(prefix='/api/v1/hubs', tags=['Hub'], route_class=SecretRoute)


def require_tls(request: Request):
    if not request.scope.get('orion_tls_listener') or request.scope.get('scheme') != 'https':
        raise HTTPException(403, 'tls_required')


class Enrollment(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=120)
    token: str = Field(pattern=r'^hub-orion-[A-Za-z0-9_-]{43}$')


@router.post('/enroll', dependencies=[Depends(require_tls), Depends(verify_admin)])
async def enroll(payload: Enrollment):
    # Reconnecting preserves the Router administrator's active flag and policy.
    row = await db_manager.fetchrow('''
        INSERT INTO router_hubs(id, name, token_hash) VALUES ($1,$2,$3)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name, token_hash=excluded.token_hash
        RETURNING is_active
    ''', str(payload.id), payload.name, hashlib.sha256(payload.token.encode()).hexdigest())
    if not row['is_active']:
        raise HTTPException(403, 'Router yöneticisi bu Hub’ın erişimini kapatmış.')
    return {'connected': True}




async def current_hub(request: Request):
    require_tls(request)
    token = request.headers.get('x-orion-hub-key', '')
    row = await db_manager.fetchrow('SELECT id, user_budget, is_active FROM router_hubs WHERE token_hash=$1',
                                    hashlib.sha256(token.encode()).hexdigest())
    if not row or not row['is_active']:
        raise HTTPException(401, 'Hub bağlantı yetkisi geçersiz veya kaldırılmış.')
    return dict(row)


@router.get('/status')
async def connection_status(hub: dict = Depends(current_hub)):
    return {'connected': True}


class Account(BaseModel):
    subject_id: UUID
    name: str = Field(min_length=1, max_length=120)
    key: str = Field(pattern=r'^sk-orion-[A-Za-z0-9_-]{43}$')


@router.post('/accounts')
async def account(payload: Account, hub: dict = Depends(current_hub)):
    digest = hashlib.sha256(payload.key.encode()).hexdigest()
    # A deterministic client credential makes retries idempotent, even if the
    # successful response was lost. Never reset usage, budgets or revocation.
    row = await db_manager.fetchrow('''
        INSERT INTO router_virtual_keys(name, api_key_hash, budget, hub_id, subject_id)
        VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT(hub_id,subject_id) DO UPDATE SET name=excluded.name
        RETURNING id, api_key_hash
    ''', payload.name, digest, hub['user_budget'], hub['id'], str(payload.subject_id))
    if not hmac.compare_digest(row['api_key_hash'], digest):
        raise HTTPException(409, 'Hesap erişimi farklı bir anahtarla kayıtlı; Router yöneticisi kontrol etmeli.')
    return {'id': row['id']}


@router.get('/catalog/{section}')
async def catalog(section: str, request: Request, hub: dict = Depends(current_hub)):
    from api import admin
    async def get_catalog_voices():
        v = await admin.get_admin_voices(request)
        return {'voices': v.get('voices', {})}

    handlers = {'models': admin.list_models, 'model-groups': admin.list_model_groups,
                'voices': get_catalog_voices,
                'local-tts-info': admin.get_local_tts_info}
    if section not in handlers:
        raise HTTPException(404, 'Unknown catalog section')
    return await handlers[section]()


async def current_account(request: Request):
    require_tls(request)
    auth = await authenticate_request(request)
    if auth.get('source') != 'virtual_key':
        raise HTTPException(403, 'Kişisel sağlayıcı için kullanıcı erişimi gerekli.')
    return auth


@router.get('/account-catalog/{section}')
async def account_catalog(section: str, request: Request, auth: dict = Depends(current_account)):
    from api import admin
    from core.key_policy import candidates, allowed
    usable = {'local'} | {r['provider'] for r in await candidates(auth['key_id']) if allowed(r)}
    # A saved personal key blocks shared credentials even when it is disabled.
    private = await db_manager.fetch('SELECT id,provider FROM router_user_provider_keys WHERE key_id=$1', auth['key_id'])
    eligible = {r['id'] for r in await candidates(auth['key_id']) if allowed(r)}
    usable -= {r['provider'] for r in private if r['id'] not in eligible}
    if section == 'models':
        data = await admin.list_models()
        return {'models': [m for m in data['models'] if m['is_active'] and m['provider'] in usable]}
    if section == 'model-groups':
        data = await admin.list_model_groups()
        groups = []
        for g in data['groups']:
            if not g['is_active']:
                continue
            g['items'] = [m for m in g['items'] if m['provider'] in usable]
            if g['items']:
                groups.append(g)
        return {'groups': groups}
    if section == 'voices':
        data = await admin.get_admin_voices(request)
        return {'voices': {p:v for p,v in data['voices'].items() if p in usable}}
    raise HTTPException(404, 'Unknown catalog section')


@router.get('/providers')
async def providers(request: Request, auth: dict = Depends(current_account)):
    from core.key_policy import candidates, allowed
    rows = await db_manager.fetch('SELECT provider,label,is_active,admin_updated,api_key FROM router_user_provider_keys WHERE key_id=$1', auth['key_id'])
    capabilities = request.app.state.dynamic_router.get_capabilities()
    summary = {}
    for row in await candidates(auth['key_id']):
        if not allowed(row):
            continue
        counts = summary.setdefault(row['provider'], {'provider': row['provider'], 'shared': 0, 'private': 0})
        exclusive = row['source'] == 'personal'
        if not exclusive and row['scope'] == 'selected':
            population = await db_manager.fetchval(
                'SELECT count(*) FROM router_provider_key_access WHERE provider_key_id=$1', row['id'])
            exclusive = population == 1
        counts['private' if exclusive else 'shared'] += 1
    from core.mdns import lan_addresses, container
    from core import config
    addresses = () if container() and not config.MDNS_CONTAINER_HOST_NETWORK else lan_addresses(config.MDNS_INTERFACES, config.TLS_HOST)
    host = next(iter(addresses), '127.0.0.1')
    from api.admin import _mask_key
    personal = []
    for row in rows:
        item = dict(row)
        value = decrypt(item.pop('api_key'))
        item['masked_key'] = _mask_key(value) if value else '••••'
        personal.append(item)
    return {'providers': sorted(capabilities), 'configured': [r['provider'] for r in rows],
            'personal_keys': personal, 'summary': list(summary.values()),
            'active_keys': sum(r['shared'] + r['private'] for r in summary.values()),
            'dashboard_url': f'https://{host}:{config.TLS_PORT}/dashboard'}


class ProviderCredential(BaseModel):
    api_key: str = Field(min_length=1, max_length=8192)


@router.put('/providers/{provider}')
async def save_provider(provider: str, payload: ProviderCredential, request: Request,
                        auth: dict = Depends(current_account)):
    if provider == 'local' or provider not in request.app.state.dynamic_router.get_capabilities():
        raise HTTPException(400, 'Desteklenmeyen sağlayıcı.')
    key = payload.api_key.strip()
    if not key or key.startswith(('sk-orion-', 'hub-orion-')):
        raise HTTPException(400, 'Sağlayıcının kendi API anahtarını girin.')
    await db_manager.execute('''
        INSERT INTO router_user_provider_keys(key_id,provider,api_key) VALUES ($1,$2,$3)
        ON CONFLICT(key_id,provider) DO UPDATE SET api_key=excluded.api_key,admin_updated=false
    ''', auth['key_id'], provider, encrypt(key))
    return {'saved': True}


@router.delete('/providers/{provider}')
async def remove_provider(provider: str, auth: dict = Depends(current_account)):
    row = await db_manager.fetchrow('SELECT is_active FROM router_user_provider_keys WHERE key_id=$1 AND provider=$2', auth['key_id'], provider)
    if row and not row['is_active']:
        raise HTTPException(403, 'Yönetici tarafından kapatılan anahtar için Router yöneticisine başvurun.')
    await db_manager.execute('DELETE FROM router_user_provider_keys WHERE key_id=$1 AND provider=$2',
                             auth['key_id'], provider)
    return {'removed': True}
