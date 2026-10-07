"""Administrator-only policy and reporting APIs. Never return stored secrets."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from core.dependencies import verify_admin, invalidate_vkey_cache
from core.key_policy import candidates, allowed, replace_rule
from core.security import encrypt
from database import db_manager

router = APIRouter(dependencies=[Depends(verify_admin)])


@router.get('/api/hubs')
async def hubs():
    return {'hubs': [dict(r) for r in await db_manager.fetch(
        'SELECT id,name,is_active,user_budget FROM router_hubs ORDER BY name,id')]}


@router.put('/api/hubs/{hub_id}')
async def set_hub(hub_id: str, request: Request):
    body = await request.json()
    if not isinstance(body.get('is_active'), bool):
        raise HTTPException(422, 'is_active gerekli.')
    row = await db_manager.fetchrow('UPDATE router_hubs SET is_active=$2 WHERE id=$1 RETURNING id,name,is_active', hub_id, body['is_active'])
    if not row:
        raise HTTPException(404, 'Hub bulunamadı.')
    invalidate_vkey_cache()
    return dict(row)


@router.get('/api/provider-key-pool/{identifier}/access')
async def provider_access(identifier: str):
    row = await db_manager.fetchrow('SELECT scope FROM router_provider_key_pool WHERE id=$1', identifier)
    if not row:
        raise HTTPException(404, 'Anahtar bulunamadı.')
    selected = await db_manager.fetch('SELECT virtual_key_id FROM router_provider_key_access WHERE provider_key_id=$1', identifier)
    return {'scope': row['scope'], 'selected': [r['virtual_key_id'] for r in selected]}


@router.put('/api/provider-key-pool/{identifier}/access')
async def save_provider_access(identifier: str, request: Request):
    body = await request.json()
    await replace_rule('provider', identifier, body.get('scope'), body.get('selected', []))
    return {'saved': True}


@router.get('/api/keys/{identifier}/access')
async def virtual_access(identifier: str):
    row = await db_manager.fetchrow('SELECT provider_key_mode FROM router_virtual_keys WHERE id=$1', identifier)
    if not row:
        raise HTTPException(404, 'Anahtar bulunamadı.')
    selected = await db_manager.fetch('SELECT provider_key_id FROM router_virtual_key_access WHERE virtual_key_id=$1', identifier)
    visible = [r for r in await candidates(identifier) if r['source'] != 'personal' or r['owner_id'] == identifier]
    for r in visible:
        r['allowed'] = allowed(r)
        r['reason'] = ('Pasif' if not r['is_active'] or not r['account_active'] else
                       'Sağlayıcı anahtarı bu sanal anahtara izin vermiyor' if not r['layer_a'] else
                       'Bu sanal anahtarın kısıtı dışında' if not r['layer_b'] else None)
    return {'mode': row['provider_key_mode'], 'selected': [r['provider_key_id'] for r in selected], 'keys': visible}


@router.put('/api/keys/{identifier}/access')
async def save_virtual_access(identifier: str, request: Request):
    body = await request.json()
    await replace_rule('virtual', identifier, body.get('mode'), body.get('selected', []))
    return {'saved': True}


@router.get('/api/personal-provider-keys')
async def personal_keys():
    return {'keys': [dict(r) for r in await db_manager.fetch('''
        SELECT p.id,p.provider,p.label,p.is_active,p.admin_updated,
               v.id AS key_id,v.name,h.id AS hub_id,h.name AS hub_name
        FROM router_user_provider_keys p JOIN router_virtual_keys v ON v.id=p.key_id
        LEFT JOIN router_hubs h ON h.id=v.hub_id ORDER BY h.name,v.name,p.provider
    ''')]}


@router.put('/api/personal-provider-keys/{identifier}')
async def edit_personal(identifier: str, request: Request):
    body = await request.json()
    secret = body.get('api_key')
    if secret is not None and (not isinstance(secret, str) or not secret.strip() or len(secret) > 8192 or secret.startswith(('sk-orion-', 'hub-orion-'))):
        raise HTTPException(422, 'Sağlayıcının kendi anahtarını girin.')
    active = body.get('is_active')
    if active is not None and not isinstance(active, bool):
        raise HTTPException(422, 'Geçersiz durum.')
    row = await db_manager.fetchrow('''
        UPDATE router_user_provider_keys SET api_key=COALESCE($2,api_key),
          is_active=COALESCE($3,is_active),admin_updated=admin_updated OR $4
        WHERE id=$1 RETURNING id,provider,label,is_active,admin_updated
    ''', identifier, encrypt(secret.strip()) if secret is not None else None, active, secret is not None)
    if not row:
        raise HTTPException(404, 'Anahtar bulunamadı.')
    return dict(row)


@router.delete('/api/personal-provider-keys/{identifier}')
async def delete_personal(identifier: str):
    await db_manager.execute('DELETE FROM router_user_provider_keys WHERE id=$1', identifier)
    return {'removed': True}


@router.get('/api/usage')
async def usage(start: datetime | None = None, end: datetime | None = None,
                hub_id: str | None = None, key_id: str | None = None,
                provider: str | None = None, model: str | None = None,
                upstream_key_id: str | None = None):
    if any(d is not None and d.tzinfo is None for d in (start,end)):
        raise HTTPException(422, "Zaman aralığı saat dilimi içermeli.")
    if start and end and start >= end:
        raise HTTPException(422, 'Başlangıç bitişten önce olmalı.')
    filters = '''($1::timestamptz IS NULL OR l.created_at >= $1)
      AND ($2::timestamptz IS NULL OR l.created_at < $2)
      AND ($3::text IS NULL OR COALESCE(l.recorded_hub_id,v.hub_id)=$3) AND ($4::text IS NULL OR COALESCE(l.recorded_key_id,l.key_id)=$4)
      AND ($5::text IS NULL OR l.provider=$5)
      AND ($6::text IS NULL OR COALESCE(l.resolved_model,l.requested_model)=$6)
      AND ($7::text IS NULL OR l.upstream_key_id=$7)'''
    # Group by capability: STT seconds and TTS characters never enter LLM sums.
    fields = '''count(*) AS requests,count(*) FILTER(WHERE l.success) AS succeeded,
        count(*) FILTER(WHERE l.success=false) AS failed,
        count(*) FILTER(WHERE l.success IS NULL) AS pending_or_interrupted,
        sum(l.prompt_tokens) AS input,sum(l.completion_tokens) AS output,
        sum(l.thoughts_tokens) AS thoughts,sum(l.tokens_used) AS total,
        count(*) FILTER(WHERE l.tokens_used IS NULL) AS missing_usage,
        sum(l.usage_amount) AS usage_amount,sum(l.cost) AS cost,count(*) FILTER(WHERE l.cost IS NULL) AS missing_cost'''
    base = ' FROM router_request_logs l LEFT JOIN router_virtual_keys v ON v.id=l.key_id WHERE ' + filters
    args = (start,end,hub_id,key_id,provider,model,upstream_key_id)
    totals = await db_manager.fetch('SELECT l.capability,l.usage_unit,'+fields+base+' GROUP BY l.capability,l.usage_unit', *args)
    daily = await db_manager.fetch("SELECT (l.created_at AT TIME ZONE 'UTC')::date AS day,l.capability,l.usage_unit,"+fields+base+" GROUP BY day,l.capability,l.usage_unit ORDER BY day", *args)
    return {'totals': [dict(r) for r in totals], 'daily': [dict(r) for r in daily], 'timezone': 'UTC',
            'units': {'chat': 'token', 'embed': 'token', 'tts': 'character', 'stt': 'provider usage'}}
