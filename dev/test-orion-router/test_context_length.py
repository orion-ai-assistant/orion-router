import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import context_length as cl
from core.model_catalog import load_model_catalog
from providers.openrouter import chat as orchat


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    async def get(self, url, timeout=None):
        self.calls.append(url)
        for suffix, response in self.routes.items():
            if url.endswith(suffix):
                return response
        raise RuntimeError("down")


def test_openrouter_context_from_cached_list(monkeypatch):
    client = FakeClient({"/api/v1/models": FakeResponse({"data": [
        {"id": "acme/big-1", "context_length": 200000},
        {"id": "acme/none", "context_length": None},
    ]})})
    monkeypatch.setattr(orchat, "get_http_client", lambda: client)
    monkeypatch.setattr(orchat, "_MODEL_CATALOG_CACHE", {})
    monkeypatch.setattr(orchat, "_MODEL_CATALOG_LAST_FETCH", 0.0)
    row = lambda name: {"name": name, "provider": "openrouter", "capability": "chat", "default_config": {}}

    async def run():
        return (await cl.resolve_context_length(row("acme/big-1"), None),
                await cl.resolve_context_length(row("big-1"), None),
                await cl.resolve_context_length(row("acme/none"), None),
                await cl.resolve_context_length(row("acme/unknown"), None))

    assert asyncio.run(run()) == (200000, 200000, None, None)
    assert len(client.calls) == 1  # one fetch, then cached


def test_local_uses_n_ctx_then_trained_length_and_caches(monkeypatch):
    client = FakeClient({"/props": FakeResponse({"default_generation_settings": {"n_ctx": 32768}})})
    monkeypatch.setattr(cl, "get_http_client", lambda: client)
    monkeypatch.setattr(cl, "_local_cache", (0.0, None))
    row = {"name": "local-chat", "provider": "local", "capability": "chat", "default_config": {}}
    assert asyncio.run(cl.resolve_context_length(row, None)) == 32768
    asyncio.run(cl.resolve_context_length(row, None))
    assert len(client.calls) == 1

    client = FakeClient({"/props": FakeResponse({}, 404),
                         "/v1/models": FakeResponse({"data": [{"meta": {"n_ctx_train": 8192}}]})})
    monkeypatch.setattr(cl, "get_http_client", lambda: client)
    monkeypatch.setattr(cl, "_local_cache", (0.0, None))
    assert asyncio.run(cl.resolve_context_length(row, None)) == 8192


def test_bundled_override_and_non_chat():
    models = {m["name"]: m for m in load_model_catalog()["models"]}
    gpt = {"name": "gpt-4o-mini", "provider": "openai", "capability": "chat", "default_config": {}}
    assert asyncio.run(cl.resolve_context_length(gpt, models["gpt-4o-mini"])) == 128000
    gpt["default_config"] = {"context_length": 64000}
    assert asyncio.run(cl.resolve_context_length(gpt, models["gpt-4o-mini"])) == 64000
    ds = {"name": "deepseek-flash", "provider": "deepseek", "capability": "chat", "default_config": {}}
    assert asyncio.run(cl.resolve_context_length(ds, models["deepseek-flash"])) is None
    tts = {"name": "tts-1", "provider": "openai", "capability": "tts", "default_config": {}}
    assert asyncio.run(cl.resolve_context_length(tts, models["tts-1"])) is None
