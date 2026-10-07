"""Scoped Hub delegation and private provider credentials; all writes require TLS."""
import hashlib
import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.dependencies import authenticate_request, verify_admin
from core.security import encrypt
from database import db_manager

router = APIRouter(prefix='/api/v1/hubs', tags=['Hub'])


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
    handlers = {'models': admin.list_models, 'model-groups': admin.list_model_groups,
                'voices': lambda: admin.get_admin_voices(request),
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


@router.get('/providers')
async def providers(request: Request, auth: dict = Depends(current_account)):
    rows = await db_manager.fetch('SELECT provider FROM router_user_provider_keys WHERE key_id=$1', auth['key_id'])
    capabilities = request.app.state.dynamic_router.get_capabilities()
    return {'providers': sorted(capabilities), 'configured': [r['provider'] for r in rows]}


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
        ON CONFLICT(key_id,provider) DO UPDATE SET api_key=excluded.api_key
    ''', auth['key_id'], provider, encrypt(key))
    return {'saved': True}


@router.delete('/providers/{provider}')
async def remove_provider(provider: str, auth: dict = Depends(current_account)):
    await db_manager.execute('DELETE FROM router_user_provider_keys WHERE key_id=$1 AND provider=$2',
                             auth['key_id'], provider)
    return {'removed': True}
