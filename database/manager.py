import os
import logging
import asyncio
import asyncpg
from typing import Optional
import json

from core.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
)
from core.model_catalog import load_model_catalog

logger = logging.getLogger("service-router.db")

# Settings made of several values: a group item's override replaces only the values it sets, the model gives the rest
# (an item that sets top_k alone keeps the model's top_p; one engine's TTS settings leave the other engine's alone).
_NESTED_SETTINGS = {"local_sampling": 1, "per_engine": 2}


def _as_dict(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _merge(base: dict, over: dict, depth: int) -> dict:
    merged = dict(base)
    for key, value in over.items():
        if depth > 0 and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value, depth - 1)
        else:
            merged[key] = value
    return merged


def merge_item_config(model_config, item_config) -> dict:
    """A group item's settings as used: the model's current settings, with only what the item itself sets on top.
    Items hold no copy of the model (a change of the model reaches every group it is in)."""
    merged = _as_dict(model_config)
    for key, value in _as_dict(item_config).items():
        depth = _NESTED_SETTINGS.get(key)
        if depth and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value, depth - 1)
        else:
            merged[key] = value
    return merged


class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    def get_postgres_url(self) -> str:
        """Read Postgres connection parameters from config."""
        return f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS router_hubs (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL, is_active BOOLEAN NOT NULL DEFAULT true,
                user_budget NUMERIC(10,4) NOT NULL DEFAULT 0 CHECK (user_budget >= 0)
            );
            ALTER TABLE router_virtual_keys ADD COLUMN IF NOT EXISTS hub_id TEXT REFERENCES router_hubs(id);
            ALTER TABLE router_virtual_keys ADD COLUMN IF NOT EXISTS subject_id TEXT;
            CREATE UNIQUE INDEX IF NOT EXISTS router_hub_subject ON router_virtual_keys(hub_id, subject_id);
            CREATE TABLE IF NOT EXISTS router_removed_hubs (
                id TEXT PRIMARY KEY, removed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS router_hub_enrollment_codes (
                code_hash TEXT PRIMARY KEY, expires_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS router_user_provider_keys (
                key_id TEXT NOT NULL REFERENCES router_virtual_keys(id) ON DELETE CASCADE,
                provider TEXT NOT NULL, api_key TEXT NOT NULL,
                PRIMARY KEY (key_id, provider)
            );
        """)
        
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
        
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS prompt_cost NUMERIC(10, 6) DEFAULT 0.0;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS completion_cost NUMERIC(10, 6) DEFAULT 0.0;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS thoughts_cost NUMERIC(10, 6) DEFAULT 0.0;")
        
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS request_json JSONB;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS response_json JSONB;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS upstream_key_id TEXT;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS capability TEXT DEFAULT 'chat';")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed';")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS ttft_ms NUMERIC(10, 2);")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS duration_ms NUMERIC(10, 2);")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS resolved_model TEXT;")
        # Prompt cache: prompt tokens served from / written to the provider cache, and the USD saved
        # against billing them at the full input price. NULL = not a chat request or no usage reported.
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS cached_tokens INTEGER;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER;")
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS cache_saved_cost NUMERIC(10, 6);")
        # TRUE: the provider never reported this chat's usage (stopped before its usage chunk); the counts are the
        # Router's guess. FALSE: the provider's own counts. NULL: not a chat or no usage.
        await conn.execute("ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS usage_estimated BOOLEAN;")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS router_image_archives (
                id BIGSERIAL PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
                image BYTEA NOT NULL,
                mime_type TEXT NOT NULL, format TEXT NOT NULL,
                size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
                width INTEGER NOT NULL CHECK (width > 0), height INTEGER NOT NULL CHECK (height > 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            ALTER TABLE router_image_archives ALTER COLUMN image SET STORAGE EXTERNAL;
            ALTER TABLE router_image_archives ADD COLUMN IF NOT EXISTS filename TEXT;
            CREATE INDEX IF NOT EXISTS router_image_archive_created ON router_image_archives(created_at DESC, id DESC);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS router_video_archives (
                id BIGSERIAL PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
                video BYTEA NOT NULL,
                mime_type TEXT NOT NULL, format TEXT NOT NULL,
                size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
                width INTEGER NOT NULL CHECK (width > 0), height INTEGER NOT NULL CHECK (height > 0),
                duration_seconds DOUBLE PRECISION, filename TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            ALTER TABLE router_video_archives ALTER COLUMN video SET STORAGE EXTERNAL;
            CREATE INDEX IF NOT EXISTS router_video_archive_created ON router_video_archives(created_at DESC, id DESC);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS router_document_archives (
                id BIGSERIAL PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
                document BYTEA NOT NULL,
                mime_type TEXT NOT NULL, format TEXT NOT NULL, size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
                filename TEXT, representation TEXT NOT NULL CHECK (representation IN ('text','binary')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            ALTER TABLE router_document_archives ALTER COLUMN document SET STORAGE EXTERNAL;
            CREATE INDEX IF NOT EXISTS router_document_archive_created ON router_document_archives(created_at DESC, id DESC);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS router_tts_audio_archives (
                id BIGSERIAL PRIMARY KEY,
                log_id BIGINT REFERENCES router_request_logs(id) ON DELETE SET NULL,
                audio BYTEA NOT NULL,
                provider TEXT NOT NULL, requested_model TEXT NOT NULL, resolved_model TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                codec TEXT NOT NULL, container TEXT NOT NULL, mime_type TEXT NOT NULL,
                duration_seconds DOUBLE PRECISION NOT NULL, channels INTEGER NOT NULL, sample_rate INTEGER NOT NULL,
                source_sample_rate INTEGER NOT NULL, source_channels INTEGER NOT NULL, source_format TEXT NOT NULL,
                source_size_bytes BIGINT NOT NULL, archive_size_bytes BIGINT NOT NULL,
                generation_status TEXT NOT NULL CHECK (generation_status IN ('completed', 'interrupted'))
            );
            ALTER TABLE router_tts_audio_archives ALTER COLUMN audio SET STORAGE EXTERNAL;
            ALTER TABLE router_tts_audio_archives DROP COLUMN IF EXISTS tts_text;
            CREATE INDEX IF NOT EXISTS router_tts_archive_created ON router_tts_audio_archives(created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS router_tts_archive_log ON router_tts_audio_archives(log_id);
        """)
        
        # Allow NULL for token columns (no estimation, only real API values) and success (None = Interrupted)
        await conn.execute("ALTER TABLE router_request_logs ALTER COLUMN tokens_used DROP DEFAULT;")
        await conn.execute("ALTER TABLE router_request_logs ALTER COLUMN prompt_tokens DROP DEFAULT;")
        await conn.execute("ALTER TABLE router_request_logs ALTER COLUMN completion_tokens DROP DEFAULT;")
        await conn.execute("ALTER TABLE router_request_logs ALTER COLUMN thoughts_tokens DROP DEFAULT;")
        await conn.execute("ALTER TABLE router_request_logs ALTER COLUMN success DROP DEFAULT;")
        
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
        # NULL = not priced separately: cached / cache-written tokens are billed at input_price.
        await conn.execute("ALTER TABLE router_model_pricing ADD COLUMN IF NOT EXISTS cache_read_price NUMERIC(15, 10);")
        await conn.execute("ALTER TABLE router_model_pricing ADD COLUMN IF NOT EXISTS cache_write_price NUMERIC(15, 10);")

        # 5. Configurations (for admin secret hash, etc.)
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

        await conn.execute('''
            ALTER TABLE router_provider_key_pool ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all','selected'));
            ALTER TABLE router_provider_key_pool DROP CONSTRAINT IF EXISTS router_provider_key_pool_provider_label_key;
            ALTER TABLE router_virtual_keys ADD COLUMN IF NOT EXISTS provider_key_mode TEXT NOT NULL DEFAULT 'unrestricted' CHECK (provider_key_mode IN ('unrestricted','only_selected'));
            ALTER TABLE router_user_provider_keys ADD COLUMN IF NOT EXISTS id TEXT NOT NULL DEFAULT gen_random_uuid()::text;
            CREATE UNIQUE INDEX IF NOT EXISTS router_personal_provider_id ON router_user_provider_keys(id);
            ALTER TABLE router_user_provider_keys ADD COLUMN IF NOT EXISTS label TEXT NOT NULL DEFAULT 'Kişisel';
            ALTER TABLE router_user_provider_keys ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
            ALTER TABLE router_user_provider_keys ADD COLUMN IF NOT EXISTS admin_updated BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE router_user_provider_keys ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100;
            CREATE TABLE IF NOT EXISTS router_provider_key_access (
                provider_key_id TEXT REFERENCES router_provider_key_pool(id) ON DELETE CASCADE,
                virtual_key_id TEXT REFERENCES router_virtual_keys(id) ON DELETE CASCADE,
                PRIMARY KEY(provider_key_id,virtual_key_id)
            );
            CREATE TABLE IF NOT EXISTS router_virtual_key_access (
                virtual_key_id TEXT REFERENCES router_virtual_keys(id) ON DELETE CASCADE,
                provider_key_id TEXT NOT NULL,
                PRIMARY KEY(virtual_key_id,provider_key_id)
            );
            ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS upstream_key_source TEXT;
            ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS recorded_key_id TEXT;
            ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS recorded_hub_id TEXT;
            ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS usage_unit TEXT;
            ALTER TABLE router_request_logs ADD COLUMN IF NOT EXISTS usage_amount NUMERIC;
            UPDATE router_request_logs l SET recorded_key_id=v.id,recorded_hub_id=v.hub_id
              FROM router_virtual_keys v WHERE l.key_id=v.id AND l.recorded_key_id IS NULL;
            CREATE INDEX IF NOT EXISTS router_logs_key_time ON router_request_logs(key_id,created_at);
        ''')

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
        await conn.execute("ALTER TABLE router_models ADD COLUMN IF NOT EXISTS thinking_level TEXT;")
        await conn.execute("ALTER TABLE router_models ADD COLUMN IF NOT EXISTS system_prompt TEXT;")
        await conn.execute("ALTER TABLE router_models ADD COLUMN IF NOT EXISTS default_config JSONB DEFAULT '{}'::jsonb;")
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
        await conn.execute("ALTER TABLE router_model_group_items ADD COLUMN IF NOT EXISTS thinking_level TEXT;")
        await conn.execute("ALTER TABLE router_model_group_items ADD COLUMN IF NOT EXISTS system_prompt TEXT;")
        await conn.execute("ALTER TABLE router_model_group_items ADD COLUMN IF NOT EXISTS temperature NUMERIC(5, 2);")
        await conn.execute("ALTER TABLE router_model_group_items ADD COLUMN IF NOT EXISTS default_config JSONB;")

        await self._migrate_legacy_provider_keys(conn)
        await self._clear_copied_group_item_settings(conn)
        await self._seed_default_models(conn)
        await self._seed_admin_secret(conn)
        await self._migrate_plaintext_keys(conn)
        
        logger.info("Database tables verified.")

    async def _seed_admin_secret(self, conn: asyncpg.Connection) -> None:
        """Seed admin secret into DB on first run."""
        val = await conn.fetchval("SELECT config_value FROM router_configs WHERE config_key = 'admin_secret_hash'")
        if not val:
            from core.config import ADMIN_SECRET
            if ADMIN_SECRET:
                from core.security import hash_secret
                hashed = hash_secret(ADMIN_SECRET)
                await conn.execute(
                    """
                    INSERT INTO router_configs (config_key, config_value)
                    VALUES ($1, $2::jsonb)
                    ON CONFLICT (config_key) DO NOTHING
                    """,
                    'admin_secret_hash', json.dumps(hashed)
                )

    async def _migrate_plaintext_keys(self, conn: asyncpg.Connection) -> None:
        """Encrypt any existing plaintext provider keys."""
        from core.security import encrypt
        rows = await conn.fetch("SELECT id, api_key FROM router_provider_key_pool WHERE api_key NOT LIKE 'gAAAAA%' AND api_key != ''")
        for row in rows:
            encrypted = encrypt(row["api_key"])
            await conn.execute(
                "UPDATE router_provider_key_pool SET api_key = $1 WHERE id = $2",
                encrypted, row["id"]
            )

    async def _clear_copied_group_item_settings(self, conn: asyncpg.Connection) -> None:
        """Once (2026-11-11): group items no longer copy their model. The groups page used to copy every setting of
        the model into the item when it was added, so later changes of the model never reached the group. Those
        copies are dropped; every item then uses its model's current settings until something is set on it."""
        if await conn.fetchval("SELECT config_value FROM router_configs WHERE config_key='group_item_copies_cleared'"):
            return
        async with conn.transaction():
            await conn.execute(
                "UPDATE router_model_group_items "
                "SET thinking_level = NULL, system_prompt = NULL, temperature = NULL, default_config = NULL"
            )
            await conn.execute(
                "INSERT INTO router_configs(config_key,config_value) VALUES('group_item_copies_cleared','true'::jsonb) "
                "ON CONFLICT(config_key) DO NOTHING"
            )

    async def _migrate_legacy_provider_keys(self, conn: asyncpg.Connection) -> None:
        """Move existing provider_api_keys config entries into the new key pool once."""
        if await conn.fetchval("SELECT config_value FROM router_configs WHERE config_key='provider_api_keys_migrated'"):
            return
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

        from core.security import encrypt
        for provider, api_key in legacy_keys.items():
            if not provider or not api_key:
                continue
            # Existing records may have been renamed/disabled by an admin.
            # Reimporting a config secret must never undo that decision.
            if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM router_provider_key_pool WHERE provider=$1)', str(provider).strip().lower()):
                continue
            await conn.execute(
                """
                INSERT INTO router_provider_key_pool (provider, label, api_key, priority, is_active)
                VALUES ($1, $2, $3, 100, true)
                """,
                str(provider).strip().lower(),
                f"Migrated {str(provider).strip().lower()} key",
                encrypt(str(api_key).strip()),
            )
        await conn.execute("INSERT INTO router_configs(config_key,config_value) VALUES('provider_api_keys_migrated','true'::jsonb) ON CONFLICT(config_key) DO NOTHING")

    async def _seed_default_models(self, conn: asyncpg.Connection) -> None:
        catalog = load_model_catalog()
        for model in catalog["models"]:
            if not model.get("seed", True):
                continue
            await conn.execute(
                """
                INSERT INTO router_models (name, provider, capability, temperature, is_active, default_config)
                VALUES ($1, $2, $3, $4, true, $5::jsonb)
                ON CONFLICT (name, capability) DO NOTHING
                """,
                model["name"],
                model["provider"],
                model["capability"],
                model.get("temperature"),
                json.dumps(model.get("settings", {})),
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
                    async with conn.transaction():
                        await conn.execute("SELECT pg_advisory_xact_lock(724109850)")
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
    
    async def upsert_pricing(
        self,
        model_name: str,
        input_price: float | None,
        output_price: float | None,
        think_price: float | None,
        cache_read_price: float | None = None,
        cache_write_price: float | None = None,
    ):
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO router_model_pricing (model_name, input_price, output_price, think_price, cache_read_price, cache_write_price)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (model_name) DO UPDATE SET
                    input_price = EXCLUDED.input_price,
                    output_price = EXCLUDED.output_price,
                    think_price = EXCLUDED.think_price,
                    cache_read_price = EXCLUDED.cache_read_price,
                    cache_write_price = EXCLUDED.cache_write_price,
                    updated_at = NOW();
                """,
                model_name, input_price, output_price, think_price, cache_read_price, cache_write_price
            )

    async def get_all_pricing(self) -> dict:
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT model_name, input_price, output_price, think_price, cache_read_price, cache_write_price FROM router_model_pricing"
            )
            result = {}
            for row in rows:
                result[row["model_name"]] = {
                    key: float(row[column]) if row[column] is not None else None
                    for key, column in (
                        ("input", "input_price"), ("output", "output_price"), ("think", "think_price"),
                        ("cache_read", "cache_read_price"), ("cache_write", "cache_write_price"),
                    )
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

    async def log_request(self, key_id, provider, model, tokens_used, prompt_tokens, completion_tokens, thoughts_tokens, cost, request_json=None, response_json=None, upstream_key_id=None, success=True, capability='chat', prompt_cost=0.0, completion_cost=0.0, thoughts_cost=0.0, status=None, ttft_ms=None, duration_ms=None, usage_unit=None, usage_amount=None, cached_tokens=None, cache_write_tokens=None, cache_saved_cost=None, usage_estimated=None):
        from core.key_policy import selected_upstream
        selected_id, selected_source = selected_upstream.get()
        upstream_key_id = upstream_key_id or selected_id
        if capability == "chat":
            from core.video_archive import archive_log_media_json
            request_json = await archive_log_media_json(request_json, self)
            response_json = await archive_log_media_json(response_json, self)
        from core.secret_guard import redact_json
        request_json, response_json = redact_json(request_json), redact_json(response_json)
        pool = await self.get_db_pool()
        if status is None:
            status = "success" if success is True else ("failed" if success is False else "interrupted")
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO router_request_logs
                        (key_id, provider, requested_model, tokens_used,
                         prompt_tokens, completion_tokens, thoughts_tokens, cost, success, request_json, response_json, upstream_key_id, capability, prompt_cost, completion_cost, thoughts_cost, status, ttft_ms, duration_ms, upstream_key_source, recorded_key_id, recorded_hub_id, usage_unit, usage_amount, cached_tokens, cache_write_tokens, cache_saved_cost, usage_estimated)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13,$14,$15,$16,$17,$18,$19,$20,$1,(SELECT hub_id FROM router_virtual_keys WHERE id=$1),$21,$22,$23,$24,$25,$26)
                    """,
                    key_id, provider, model, tokens_used, prompt_tokens, completion_tokens, thoughts_tokens, cost, success, request_json, response_json, upstream_key_id, capability, prompt_cost, completion_cost, thoughts_cost, status, ttft_ms, duration_ms, selected_source, usage_unit, usage_amount, cached_tokens, cache_write_tokens, cache_saved_cost, usage_estimated
                )
                if key_id and cost is not None and (success or cost > 0):
                    await conn.execute(
                        "UPDATE router_virtual_keys SET used_amount = used_amount + $1 WHERE id = $2",
                        cost, key_id
                    )

    async def create_streaming_log(
        self,
        key_id: str | None,
        provider: str,
        model: str,
        request_json: str | None = None,
        response_json: str | None = None,
        capability: str = "stt",
        status: str = "streaming",
    ) -> int:
        """Yeni bir canlı streaming oturumu için log kaydı başlatır ve log_id döner."""
        if capability == "chat":
            from core.video_archive import archive_log_media_json
            request_json = await archive_log_media_json(request_json, self)
            response_json = await archive_log_media_json(response_json, self)
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                log_id = await conn.fetchval(
                    """
                    INSERT INTO router_request_logs
                        (key_id, provider, requested_model, tokens_used,
                         prompt_tokens, completion_tokens, thoughts_tokens, cost, success,
                         request_json, response_json, capability, status, recorded_key_id, recorded_hub_id)
                    VALUES ($1, $2, $3, NULL, NULL, NULL, NULL, NULL, NULL, $4::jsonb, $5::jsonb, $6, $7, $1, (SELECT hub_id FROM router_virtual_keys WHERE id=$1))
                    RETURNING id
                    """,
                    key_id, provider, model, request_json, response_json, capability, status,
                )
                return log_id

    async def update_streaming_log(
        self,
        log_id: int,
        response_json: str | None = None,
        status: str = "success",
        success: bool | None = True,
        tokens_used: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        thoughts_tokens: int | None = None,
        cost: float | None = None,
        prompt_cost: float | None = None,
        completion_cost: float | None = None,
        thoughts_cost: float | None = None,
        key_id: str | None = None,
        duration_ms: float | None = None,
        ttft_ms: float | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_json: str | None = None,
        usage_unit: str | None = None,
        usage_amount: float | None = None,
        capability: str | None = None,
        cached_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        cache_saved_cost: float | None = None,
        usage_estimated: bool | None = None,
    ) -> None:
        """Canlı streaming oturumunun ara veya nihai sonucunu günceller. A finished log changes again only to put
        the provider's own usage in place of the Router's estimate (usage_estimated False over True)."""
        if capability == "chat":
            from core.video_archive import archive_log_media_json
            request_json = await archive_log_media_json(request_json, self)
            response_json = await archive_log_media_json(response_json, self)
        from core.key_policy import selected_upstream
        upstream_id, upstream_source = selected_upstream.get()
        from core.secret_guard import redact_json
        request_json, response_json = redact_json(request_json), redact_json(response_json)
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT cost, usage_estimated FROM router_request_logs WHERE id = $1 FOR UPDATE", log_id)
                result = await conn.execute(
                    """
                    UPDATE router_request_logs
                    SET response_json = COALESCE($2::jsonb, response_json),
                        status = $3,
                        success = $4,
                        tokens_used = COALESCE($5, tokens_used),
                        prompt_tokens = COALESCE($6, prompt_tokens),
                        completion_tokens = COALESCE($7, completion_tokens),
                        thoughts_tokens = COALESCE($8, thoughts_tokens),
                        cost = CASE WHEN $3 IN ('success','failed','interrupted') THEN $9 ELSE COALESCE($9,cost) END,
                                                prompt_cost = COALESCE($10, prompt_cost),
                                                completion_cost = COALESCE($11, completion_cost),
                                                thoughts_cost = COALESCE($12, thoughts_cost),
                                                duration_ms = COALESCE($13, duration_ms),
                                                ttft_ms = COALESCE($14, ttft_ms),
                        provider = COALESCE($15, provider),
                        resolved_model = COALESCE($16, resolved_model),
                        request_json = COALESCE($17::jsonb, request_json),
                        upstream_key_id = COALESCE($18, upstream_key_id),
                        upstream_key_source = COALESCE($19, upstream_key_source),
                        usage_unit = COALESCE($20, usage_unit),
                        usage_amount = COALESCE($21, usage_amount),
                        cached_tokens = COALESCE($22, cached_tokens),
                        cache_write_tokens = COALESCE($23, cache_write_tokens),
                        cache_saved_cost = COALESCE($24, cache_saved_cost),
                        usage_estimated = COALESCE($25, usage_estimated)
                                        WHERE id = $1
                                            AND ($3 = 'success' OR status NOT IN ('success', 'failed', 'interrupted')
                                                 OR ($25 IS FALSE AND usage_estimated IS TRUE))
                    """,
                    log_id, response_json, status, success, tokens_used, prompt_tokens,
                                        completion_tokens, thoughts_tokens, cost, prompt_cost, completion_cost,
                                        thoughts_cost, duration_ms, ttft_ms, provider, model, request_json, upstream_id, upstream_source, usage_unit, usage_amount,
                                        cached_tokens, cache_write_tokens, cache_saved_cost, usage_estimated
                )
                charged = cost if cost is not None and cost > 0 else 0
                if before is not None and before["usage_estimated"] is True and usage_estimated is False:
                    # The estimate's cost was already added to the key: only the difference goes on top.
                    charged = (cost or 0) - float(before["cost"] or 0)
                if result.endswith(" 1") and key_id and charged:
                    await conn.execute(
                        "UPDATE router_virtual_keys SET used_amount = used_amount + $1 WHERE id = $2",
                        charged, key_id,
                    )

    async def close_abandoned_logs(self, min_age_seconds: int = 120) -> int:
        """Mark requests still "processing" after a restart as interrupted: the process that ran them is gone."""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            closed = await conn.fetch(
                """
                UPDATE router_request_logs
                SET status = 'interrupted', success = NULL,
                    response_json = '{"error": "Router stopped before this request finished"}'::jsonb
                WHERE status = 'processing' AND created_at < NOW() - make_interval(secs => $1)
                RETURNING id
                """,
                min_age_seconds,
            )
        return len(closed)

    async def update_streaming_request(self, log_id: int, request_json: str) -> None:
        # This path records the exact local chat provider payload.
        from core.video_archive import archive_log_media_json
        request_json = await archive_log_media_json(request_json, self)
        await self.execute(
            "UPDATE router_request_logs SET request_json = $2::jsonb WHERE id = $1",
            log_id,
            request_json,
        )

    async def get_active_provider_keys(self, provider: str) -> list[dict]:
        from core.security import decrypt
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
        keys = []
        for r in rows:
            d = dict(r)
            decrypted = decrypt(d["api_key"])
            if decrypted is None:
                err_msg = "Şifre çözülemiyor; anahtarı yeniden kaydet"
                logger.warning("Provider key %s (%s) cannot be decrypted; skipping and deactivating.", d["id"], d["label"])
                asyncio.create_task(self.mark_provider_key_error(d["id"], err_msg))
                continue
            d["api_key"] = decrypted
            keys.append(d)
        return keys

    async def mark_provider_key_error(self, key_id: str | None, error: str) -> None:
        if not key_id:
            return
        err_text = error[:1000]
        deactivate = any(
            marker in err_text
            for marker in ("API_KEY_INVALID", "API key not valid", "Şifre çözülemiyor")
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
                SELECT m.id, m.name, m.provider, m.capability,
                       COALESCE(i.temperature, m.temperature) AS temperature,
                       g.name AS requested_name, i.priority,
                       COALESCE(i.thinking_level, m.thinking_level) AS thinking_level,
                       COALESCE(i.system_prompt, m.system_prompt) AS system_prompt,
                       m.default_config AS model_config, i.default_config AS item_config
                FROM router_model_group_items i
                JOIN router_models m ON m.id = i.model_id
                JOIN router_model_groups g ON g.id = i.group_id
                WHERE i.group_id = $1 AND m.is_active = true AND m.capability = $2
                ORDER BY i.priority ASC, i.created_at ASC
                """,
                group["id"],
                capability,
            )
            if not rows:
                raise ValueError(f"Model group '{group['name']}' exists but has no active models.")
            resolved = []
            for r in rows:
                row = dict(r)
                row["default_config"] = merge_item_config(row.pop("model_config"), row.pop("item_config"))
                resolved.append({"is_group": True, **row})
            return resolved

        row = await self.fetchrow(
            """
            SELECT id, name, provider, capability, temperature, name AS requested_name, 100 AS priority, thinking_level, system_prompt, default_config
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
