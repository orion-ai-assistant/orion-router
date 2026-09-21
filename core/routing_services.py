import logging
from datetime import datetime, timedelta, timezone

from core.route_types import ResolvedRoute, RoutePlan
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
            return RoutePlan(
                routes=tuple(ResolvedRoute.from_record(record) for record in records),
                requested_provider=provider,
            )
        if provider:
            return RoutePlan(
                routes=(ResolvedRoute(provider=provider, model=model),),
                requested_provider=provider,
            )
        return RoutePlan(routes=(), requested_provider=None)


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
    ) -> list[tuple[str | None, str | None]]:
        keys = []
        try:
            pool_keys = await db_manager.get_active_provider_keys(provider)
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
            logger.error("Failed to fetch keys from pool for %s: %s", provider, exc)

        if not keys:
            db_key = self.get_db_key(provider)
            if db_key:
                keys.append((db_key, None))
            else:
                clean_client_key = client_key
                if clean_client_key and clean_client_key.startswith("Bearer "):
                    clean_client_key = clean_client_key.removeprefix("Bearer ").strip()

                if clean_client_key and not clean_client_key.startswith("sk-orion-"):
                    keys.append((clean_client_key, None))
                else:
                    keys.append((None, None))
        return keys

    async def mark_key_error(self, key_pool_id: str | None, error: str) -> None:
        if key_pool_id:
            await db_manager.mark_provider_key_error(key_pool_id, error)
