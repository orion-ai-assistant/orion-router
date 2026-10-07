"""Uncached credential authorization, keyed only by immutable database IDs."""
from contextvars import ContextVar

from fastapi import HTTPException
from database import db_manager

ACCESS_MESSAGE = 'Bu model için erişiminiz yok, Router yöneticisine başvurun.'
selected_upstream = ContextVar('selected_upstream', default=(None, None))

# Both layers apply to personal records too; layer A is always their owner.
CANDIDATES_SQL = '''
WITH candidates AS (
 SELECT p.id, p.provider, p.label, p.is_active, 'shared' AS source,
        p.scope = 'all' OR EXISTS (
          SELECT 1 FROM router_provider_key_access a
          WHERE a.provider_key_id=p.id AND a.virtual_key_id=$1) AS layer_a,
        p.scope, NULL::text AS owner_id
 FROM router_provider_key_pool p
 UNION ALL
 SELECT p.id, p.provider, p.label, p.is_active, 'personal', p.key_id=$1,
        'selected', p.key_id FROM router_user_provider_keys p
)
SELECT c.*, v.provider_key_mode,
 (v.provider_key_mode='unrestricted' OR EXISTS (
   SELECT 1 FROM router_virtual_key_access b
   WHERE b.virtual_key_id=v.id AND b.provider_key_id=c.id)) AS layer_b,
 (v.is_active AND (v.hub_id IS NULL OR h.is_active)) AS account_active
FROM candidates c CROSS JOIN router_virtual_keys v
LEFT JOIN router_hubs h ON h.id=v.hub_id
WHERE v.id=$1
'''


async def candidates(key_id):
    return [dict(r) for r in await db_manager.fetch(CANDIDATES_SQL, key_id)]


def allowed(row):
    return bool(row['is_active'] and row['layer_a'] and row['layer_b'] and row['account_active'])


async def eligible_ids(key_id, provider):
    return {r['id'] for r in await candidates(key_id) if r['provider'] == provider and allowed(r)}


async def authorize_attempt(key_id, provider, upstream_id, secret=None):
    from core.secret_guard import remember
    remember(secret)
    source = 'shared' if upstream_id else None
    if key_id and provider != 'local':
        match = next((r for r in await candidates(key_id) if r['id'] == upstream_id and r['provider'] == provider and allowed(r)), None)
        if not match:
            raise HTTPException(403, ACCESS_MESSAGE)
        source = match['source']
    selected_upstream.set((upstream_id, source))


async def replace_rule(table, identifier, mode, selected):
    """Atomically replace a rule; foreign keys reject stale virtual IDs."""
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
        raise HTTPException(422, 'Seçim kimlik listesi olmalı.')
    if table == 'provider':
        root, column, relation, owner, target, valid = (
            'router_provider_key_pool', 'scope', 'router_provider_key_access',
            'provider_key_id', 'virtual_key_id', ('all', 'selected'))
    else:
        root, column, relation, owner, target, valid = (
            'router_virtual_keys', 'provider_key_mode', 'router_virtual_key_access',
            'virtual_key_id', 'provider_key_id', ('unrestricted', 'only_selected'))
    if mode not in valid:
        raise HTTPException(422, 'Geçersiz izin kapsamı.')
    pool = await db_manager.get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(f'UPDATE {root} SET {column}=$2 WHERE id=$1 RETURNING id', identifier, mode)
            if not row:
                raise HTTPException(404, 'Anahtar bulunamadı.')
            if table == 'provider' and selected:
                known = await conn.fetch('SELECT id FROM router_virtual_keys WHERE id=ANY($1::text[])', selected)
                if set(selected) != {r['id'] for r in known}:
                    raise HTTPException(422, 'Sanal anahtar bulunamadı.')
            if table != 'provider' and selected:
                known = await conn.fetch('SELECT id FROM router_provider_key_pool WHERE id=ANY($1::text[]) UNION ALL SELECT id FROM router_user_provider_keys WHERE id=ANY($1::text[]) AND key_id=$2', selected, identifier)
                if set(selected) != {r['id'] for r in known}:
                    raise HTTPException(422, 'Sağlayıcı anahtarı bulunamadı veya başka kullanıcıya ait.')
            await conn.execute(f'DELETE FROM {relation} WHERE {owner}=$1', identifier)
            for target_id in set(selected):
                await conn.execute(f'INSERT INTO {relation} ({owner},{target}) VALUES ($1,$2)', identifier, target_id)
