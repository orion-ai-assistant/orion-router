import os
import logging
import asyncpg
from typing import Optional
import json

logger = logging.getLogger("service-router.db")

class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    def get_postgres_url(self) -> str:
        """Read Postgres connection parameters from environment variables."""
        user = os.environ.get("POSTGRES_USER", "orion_user")
        password = os.environ.get("POSTGRES_PASSWORD", "orion_pass")
        host = os.environ.get("POSTGRES_HOST", "postgres")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB", "orion_db")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    async def _ensure_tables(self, conn: asyncpg.Connection) -> None:
        """Create router-specific tables if they don't exist."""
        # 1. Virtual Keys (API Keys and budgets)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_virtual_keys (
                id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name TEXT NOT NULL DEFAULT 'New Key',
                api_key_hash TEXT NOT NULL UNIQUE,
                budget NUMERIC(10, 4) DEFAULT 0.0,
                used_amount NUMERIC(10, 4) DEFAULT 0.0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute("ALTER TABLE router_virtual_keys ADD COLUMN IF NOT EXISTS name TEXT DEFAULT 'New Key';")
        await conn.execute("ALTER TABLE router_virtual_keys ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;")
        
        # 2. Combo Routes (Dynamic provider/fallback logic)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_combo_routes (
                id TEXT PRIMARY KEY,
                alias_name TEXT NOT NULL UNIQUE,
                primary_provider TEXT NOT NULL,
                primary_model TEXT NOT NULL,
                fallback_provider TEXT,
                fallback_model TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        
        # 3. Request Logs (Logging token usage and cost)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_request_logs (
                id BIGSERIAL PRIMARY KEY,
                key_id TEXT REFERENCES router_virtual_keys(id) ON DELETE SET NULL,
                route_id TEXT REFERENCES router_combo_routes(id) ON DELETE SET NULL,
                provider TEXT NOT NULL,
                requested_model TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                thoughts_tokens INTEGER DEFAULT 0,
                cost NUMERIC(10, 6) DEFAULT 0.0,
                success BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER DEFAULT 0;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS completion_tokens INTEGER DEFAULT 0;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS thoughts_tokens INTEGER DEFAULT 0;")
        
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS request_json JSONB;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS response_json JSONB;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS upstream_key_id TEXT;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS capability TEXT DEFAULT 'chat';")
        
        # 4. Model Pricing
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_model_pricing (
                model_name TEXT PRIMARY KEY,
                input_price NUMERIC(15, 10) DEFAULT 0.0,
                output_price NUMERIC(15, 10) DEFAULT 0.0,
                think_price NUMERIC(15, 10) DEFAULT 0.0,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        
        # 5. Configurations (for model_info.json etc.)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_configs (
                config_key TEXT PRIMARY KEY,
                config_value JSONB,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        # 6. Provider key pool. Keys are stored so the router can rotate/fallback
        # at runtime without requiring users to pass upstream provider keys.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_provider_key_pool (
                id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                provider TEXT NOT NULL,
                label TEXT NOT NULL,
                api_key TEXT NOT NULL,
                priority INTEGER DEFAULT 100,
                is_active BOOLEAN DEFAULT true,
                last_error TEXT,
                last_error_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(provider, label)
            );
            """
        )

        # 7. Model registry and model groups.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_models (
                id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                capability TEXT NOT NULL DEFAULT 'chat',
                temperature NUMERIC(5, 2),
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(name, capability)
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_model_groups (
                id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                capability TEXT NOT NULL DEFAULT 'chat',
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(name, capability)
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS router_model_group_items (
                id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                group_id TEXT NOT NULL REFERENCES router_model_groups(id) ON DELETE CASCADE,
                model_id TEXT NOT NULL REFERENCES router_models(id) ON DELETE CASCADE,
                priority INTEGER DEFAULT 100,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(group_id, model_id)
            );
            """
        )

        await self._migrate_legacy_provider_keys(conn)
        await self._seed_default_models(conn)
        
        logger.info("Database tables verified.")

    async def _migrate_legacy_provider_keys(self, conn: asyncpg.Connection) -> None:
        """Move existing provider_api_keys config entries into the new key pool once."""
        raw = await conn.fetchval(
            "SELECT config_value FROM router_configs WHERE config_key = 'provider_api_keys'"
        )
        if not raw:
            return

        try:
            legacy_keys = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            logger.warning("Skipping legacy provider key migration: config is not a JSON object")
            return

        for provider, api_key in legacy_keys.items():
            if not provider or not api_key:
                continue
            await conn.execute(
                """
                INSERT INTO router_provider_key_pool (provider, label, api_key, priority, is_active)
                VALUES ($1, $2, $3, 100, true)
                ON CONFLICT (provider, label) DO NOTHING
                """,
                str(provider).strip().lower(),
                f"Migrated {str(provider).strip().lower()} key",
                str(api_key).strip(),
            )

    async def _seed_default_models(self, conn: asyncpg.Connection) -> None:
        # Delete old/invalid preview model if it exists
        await conn.execute(
            "DELETE FROM router_models WHERE name = 'gemini-3.1-flash-tts-preview' AND capability = 'tts'"
        )
        defaults = [
            ("local-model", "local", "chat", None),
            ("gpt-4o-mini", "openai", "chat", 0.7),
            ("gemini-3.1-flash-lite", "gemini", "chat", 0.7),
            ("gemini-3.1-flash-tts-preview", "gemini", "tts", None),
            ("tts-1", "openai", "tts", None),
            ("local-embed", "local", "embed", None),
        ]
        for name, provider, capability, temperature in defaults:
            await conn.execute(
                """
                INSERT INTO router_models (name, provider, capability, temperature, is_active)
                VALUES ($1, $2, $3, $4, true)
                ON CONFLICT (name, capability) DO NOTHING
                """,
                name,
                provider,
                capability,
                temperature,
            )

    async def init_db(self) -> None:
        """Initialize the asyncpg connection pool and ensure tables exist."""
        db_url = self.get_postgres_url()
        try:
            self.pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=2,
                max_size=20,
                command_timeout=60,
            )
            if self.pool:
                async with self.pool.acquire() as conn:
                    await self._ensure_tables(conn)
                logger.info("Successfully connected to Postgres and initialized pool.")
            else:
                logger.error("Failed to create asyncpg pool.")
        except Exception as e:
            logger.exception("Error initializing database pool.")
            raise

    async def close_db(self) -> None:
        """Close the asyncpg connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed.")

    async def get_db_pool(self) -> asyncpg.Pool:
        """Get the active connection pool."""
        if self.pool is None:
            raise RuntimeError("Database pool has not been initialized.")
        return self.pool

    # --- Repository Methods ---
    
    async def upsert_pricing(self, model_name: str, input_price: float, output_price: float, think_price: float):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO router_model_pricing (model_name, input_price, output_price, think_price)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (model_name) DO UPDATE SET
                    input_price = EXCLUDED.input_price,
                    output_price = EXCLUDED.output_price,
                    think_price = EXCLUDED.think_price,
                    updated_at = NOW();
                """,
                model_name, input_price, output_price, think_price
            )

    async def get_all_pricing(self) -> dict:
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT model_name, input_price, output_price, think_price FROM router_model_pricing")
            result = {}
            for row in rows:
                result[row["model_name"]] = {
                    "input": float(row["input_price"]),
                    "output": float(row["output_price"]),
                    "think": float(row["think_price"])
                }
            return result
            
    async def upsert_config(self, config_key: str, config_value: str):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO router_configs (config_key, config_value)
                VALUES ($1, $2::jsonb)
                ON CONFLICT (config_key) DO UPDATE SET
                    config_value = EXCLUDED.config_value,
                    updated_at = NOW();
                """,
                config_key, config_value
            )

    async def get_config(self, config_key: str) -> Optional[dict]:
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT config_value FROM router_configs WHERE config_key = $1", config_key)
            if val:
                return json.loads(val)
            return None

    async def log_request(self, key_id, provider, model, tokens_used, prompt_tokens, completion_tokens, thoughts_tokens, cost, request_json=None, response_json=None, upstream_key_id=None, success=True, capability='chat'):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO router_request_logs
                        (key_id, provider, requested_model, tokens_used,
                         prompt_tokens, completion_tokens, thoughts_tokens, cost, success, request_json, response_json, upstream_key_id, capability)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13)
                    """,
                    key_id, provider, model, tokens_used, prompt_tokens, completion_tokens, thoughts_tokens, cost, success, request_json, response_json, upstream_key_id, capability
                )
                if key_id and cost is not None and success:
                    await conn.execute(
                        "UPDATE router_virtual_keys SET used_amount = used_amount + $1 WHERE id = $2",
                        cost, key_id
                    )

    async def get_active_provider_keys(self, provider: str) -> list[dict]:
        rows = await self.fetch(
            """
            SELECT id, provider, label, api_key, priority, last_error, last_error_at
            FROM router_provider_key_pool
            WHERE provider = $1 AND is_active = true AND api_key <> ''
            ORDER BY
                CASE WHEN last_error IS NULL THEN 0 ELSE 1 END ASC,
                priority ASC,
                created_at ASC
            """,
            provider,
        )
        return [dict(r) for r in rows]

    async def mark_provider_key_error(self, key_id: str | None, error: str) -> None:
        if not key_id:
            return
        err_text = error[:1000]
        deactivate = any(
            marker in err_text
            for marker in ("API_KEY_INVALID", "API key not valid")
        )
        if deactivate:
            await self.execute(
                """
                UPDATE router_provider_key_pool
                SET last_error = $2,
                    last_error_at = NOW(),
                    is_active = false,
                    updated_at = NOW()
                WHERE id = $1
                """,
                key_id,
                err_text,
            )
            logger.warning("Provider key %s auto-deactivated: invalid API key", key_id)
            return
        await self.execute(
            """
            UPDATE router_provider_key_pool
            SET last_error = $2, last_error_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            key_id,
            err_text,
        )

    async def resolve_model_route(self, capability: str, name: str) -> list[dict]:
        """Return one or more concrete model routes for a model or group name."""
        normalized = (name or "").strip()
        if not normalized:
            return []

        group = await self.fetchrow(
            """
            SELECT id, name
            FROM router_model_groups
            WHERE lower(name) = lower($1) AND capability = $2 AND is_active = true
            """,
            normalized,
            capability,
        )
        if group:
            rows = await self.fetch(
                """
                SELECT m.id, m.name, m.provider, m.capability, m.temperature,
                       g.name AS requested_name, i.priority
                FROM router_model_group_items i
                JOIN router_models m ON m.id = i.model_id
                JOIN router_model_groups g ON g.id = i.group_id
                WHERE i.group_id = $1 AND m.is_active = true AND m.capability = $2
                ORDER BY i.priority ASC, i.created_at ASC
                """,
                group["id"],
                capability,
            )
            return [dict(r) for r in rows]

        row = await self.fetchrow(
            """
            SELECT id, name, provider, capability, temperature, name AS requested_name, 100 AS priority
            FROM router_models
            WHERE lower(name) = lower($1) AND capability = $2 AND is_active = true
            """,
            normalized,
            capability,
        )
        return [dict(row)] if row else []

    # Useful for endpoints
    async def fetch(self, query, *args):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)
            
    async def fetchrow(self, query, *args):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
            
    async def fetchval(self, query, *args):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args)
            
    async def execute(self, query, *args):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)
