"""Checks for the bundled model catalog and database seed inputs."""

import asyncio
import json

from core.local_chat_defaults import LOCAL_SAMPLING_DEFAULTS
from core.model_catalog import bundled_model, load_model_catalog
from database.manager import DatabaseManager


def test_catalog_has_one_source_for_models_and_local_defaults():
    catalog = load_model_catalog()
    assert catalog["pricing_unit"] == "per_million_tokens"
    assert bundled_model("local", "chat")["settings"]["local_sampling"] == LOCAL_SAMPLING_DEFAULTS
    assert LOCAL_SAMPLING_DEFAULTS == {
        "top_p": 0.95, "top_k": 64, "min_p": 0.05, "repeat_penalty": 1,
    }
    assert len([model for model in catalog["models"] if model.get("seed", True)]) == 9
    assert all(model.get("seed") is False for model in catalog["models"] if "provider" not in model)
    assert "pricing" not in bundled_model("gemini", "chat")


def test_database_seed_uses_catalog_without_overwriting_registered_models():
    calls = []

    class FakeConnection:
        async def execute(self, query, *args):
            calls.append((query, args))

    asyncio.run(DatabaseManager()._seed_default_models(FakeConnection()))
    inserts = [(query, args) for query, args in calls if "INSERT INTO router_models" in query]
    assert len(inserts) == 9
    assert all("ON CONFLICT (name, capability) DO NOTHING" in query for query, _ in inserts)
    local_chat = next(args for _, args in inserts if args[0] == bundled_model("local", "chat")["name"])
    assert json.loads(local_chat[4])["local_sampling"] == LOCAL_SAMPLING_DEFAULTS
    assert len(calls) == len(inserts)
