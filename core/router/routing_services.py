import logging
from datetime import datetime, timedelta, timezone

from core.router.route_types import ResolvedRoute, RoutePlan
from database import db_manager

logger = logging.getLogger("service-router.dynamic")

QUOTA_COOLDOWN_SECONDS = 45


def pool_key_on_quota_cooldown(pool_key: dict) -> bool:
    last_error = pool_key.get("last_error") or ""
    if "RESOURCE_EXHAUSTED" not in last_error and "429" not in last_error:
        return False
    last_at = pool_key.get("last_error_at")
    if not last_at:
        return False
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_at < timedelta(seconds=QUOTA_COOLDOWN_SECONDS)


class RouteResolver:
    async def resolve(self, capability: str, model: str, provider: str | None) -> RoutePlan:
        records = await db_manager.resolve_model_route(capability, model)
        if records:
            is_group = any(bool(r.get("is_group")) for r in records)
            return RoutePlan(
                routes=tuple(ResolvedRoute.from_record(record) for record in records),
                requested_provider=provider,
                is_group=is_group,
            )
        if provider:
            return RoutePlan(
                routes=(ResolvedRoute(provider=provider, model=model),),
                requested_provider=provider,
                is_group=False,
            )
        return RoutePlan(routes=(), requested_provider=None, is_group=False)


class ProviderKeyPool:
    def __init__(self, app_state=None) -> None:
        self.app_state = app_state

    def get_db_key(self, provider: str) -> str | None:
        db_keys = getattr(self.app_state, "provider_keys", {})
        key = db_keys.get(provider)
        return key if key else None

    async def get_keys_for_provider(
        self,
        provider: str,
        client_key: str | None = None,
        key_id: str | None = None,
    ) -> list[tuple[str | None, str | None]]:
        if provider == 'local':
            return [(None, None)]  # Local engines do not consume provider credentials.
        permitted = None
        if key_id:
            from core.key_policy import eligible_ids
            permitted = await eligible_ids(key_id, provider)
            # Personal credentials never enter the shared pool or fall back to
            # shared billing when the user's saved credential cannot be read.
            from core.security import decrypt
            from fastapi import HTTPException
            row = await db_manager.fetchrow(
                'SELECT id, api_key, is_active FROM router_user_provider_keys WHERE key_id=$1 AND provider=$2',
                key_id, provider)
            if row:
                if row['id'] not in permitted:
                    return []  # A saved personal record forbids silent shared fallback.
                key = decrypt(row['api_key'])
                if not key:
                    raise HTTPException(503, 'Kişisel sağlayıcı anahtarı okunamadı; yeniden kaydedin.')
                return [(key, row['id'])]
        keys = []
        try:
            pool_keys = await db_manager.get_active_provider_keys(provider)
            if permitted is not None:
                pool_keys = [pk for pk in pool_keys if pk['id'] in permitted]
            usable_keys = [pk for pk in pool_keys if not pool_key_on_quota_cooldown(pk)]
            skipped = len(pool_keys) - len(usable_keys)
            if skipped:
                logger.info(
                    "Skipping %d provider key(s) for %s on quota cooldown.",
                    skipped,
                    provider,
                )
            if not usable_keys and pool_keys:
                usable_keys = pool_keys
                logger.info(
                    "All active key(s) for %s are on quota cooldown; trying anyway.",
                    provider,
                )
            for pk in usable_keys:
                keys.append((pk["api_key"], pk["id"]))
        except Exception as exc:
            if key_id:
                raise  # A policy/storage failure must fail closed.
            logger.error("Failed to fetch keys from pool for %s: %s", provider, exc)

        if not keys:
            if key_id:
                return []  # Global/config/environment credentials are system-only.
            db_key = self.get_db_key(provider)
            if db_key:
                keys.append((db_key, None))
            elif provider in ("openrouter", "deepseek"):
                # Router credentials are never OpenRouter or DeepSeek credentials.
                keys.append((None, None))
            else:
                # Router authentication secrets must never become upstream keys.
                keys.append((None, None))
        return keys

    async def mark_key_error(self, key_pool_id: str | None, error: str) -> None:
        if key_pool_id:
            await db_manager.mark_provider_key_error(key_pool_id, error)
