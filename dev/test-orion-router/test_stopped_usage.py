"""A stream the client stopped before its usage chunk: the provider's real usage replaces the estimate."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from core.router.runners.chat import ChatRunner
from providers.openrouter.chat import OpenRouterChatProvider


class _Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


async def test_openrouter_recovers_billed_usage_once_the_stats_exist():
    replies = [_Response(404), _Response(200, {"data": {
        "native_tokens_prompt": 695, "native_tokens_completion": 254, "native_tokens_reasoning": 85,
        "native_tokens_cached": 656, "cancelled": True}})]
    client = SimpleNamespace(get=AsyncMock(side_effect=replies))
    with patch("providers.openrouter.chat.get_http_client", return_value=client), \
            patch("asyncio.sleep", AsyncMock()):
        usage = await OpenRouterChatProvider().recover_usage("gen-1", api_key="sk-or-test")
    assert usage == {"prompt_tokens": 695, "completion_tokens": 169, "thoughts_tokens": 85,
                     "prompt_tokens_details": {"cached_tokens": 656}}
    call = client.get.await_args
    assert call.kwargs["params"] == {"id": "gen-1"}
    assert call.kwargs["headers"]["Authorization"] == "Bearer sk-or-test"


async def test_openrouter_gives_up_without_stats_or_key():
    client = SimpleNamespace(get=AsyncMock(return_value=_Response(404)))
    with patch("providers.openrouter.chat.get_http_client", return_value=client), \
            patch("asyncio.sleep", AsyncMock()):
        assert await OpenRouterChatProvider().recover_usage("gen-1", api_key="sk-or-test") is None
        assert await OpenRouterChatProvider().recover_usage("gen-1", api_key="sk-orion-virtual") is None


async def test_a_stopped_stream_is_logged_again_with_the_recovered_usage():
    async def stream_chat(**_):
        yield {"internal_generation_id": "gen-9"}
        yield 'data: {"choices":[{"delta":{"content":"Bir gün Nasrettin Hoca"}}]}\n\n'
        await asyncio.sleep(3600)  # The client stops here, before the usage chunk.

    real = {"prompt_tokens": 695, "completion_tokens": 40, "prompt_tokens_details": {"cached_tokens": 656}}
    plugin = SimpleNamespace(stream_chat=stream_chat, recover_usage=AsyncMock(return_value=real))
    telemetry = SimpleNamespace(log_usage=AsyncMock())
    runner = ChatRunner(None, None, None, telemetry)
    stream = runner.stream(plugin, "key-1", "openrouter", "openai/gpt-oss-120b",
                           [{"role": "user", "content": "fıkra"}], "sk-or-test", None, log_id=7)

    async def consume():
        async for chunk in stream:
            assert not isinstance(chunk, dict)  # The id never reaches the client.
    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    for _ in range(20):
        await asyncio.sleep(0)
    await asyncio.gather(*list(runner._log_writers))

    plugin.recover_usage.assert_awaited_once_with("gen-9", api_key="sk-or-test", auth_header=None)
    first, second = telemetry.log_usage.await_args_list
    assert first.kwargs["is_estimated"] is True and first.kwargs["success"] is None
    assert second.args[3]["prompt_tokens"] == 695
    assert second.args[3]["prompt_tokens_details"]["cached_tokens"] == 656
    assert second.kwargs["is_estimated"] is False and second.kwargs["log_id"] == 7


async def test_a_finished_stream_asks_nothing_afterwards():
    async def stream_chat(**_):
        yield {"internal_generation_id": "gen-2"}
        yield 'data: {"choices":[{"delta":{"content":"tamam"}}]}\n\n'
        yield {"internal_usage": {"prompt_tokens": 10, "completion_tokens": 2}}

    plugin = SimpleNamespace(stream_chat=stream_chat, recover_usage=AsyncMock())
    runner = ChatRunner(None, None, None, SimpleNamespace(log_usage=AsyncMock()))
    async for _ in runner.stream(plugin, None, "openrouter", "m", [], "sk-or-test", None, log_id=1):
        pass
    await asyncio.gather(*list(runner._log_writers))
    plugin.recover_usage.assert_not_awaited()


async def test_the_estimate_counts_the_tool_definitions_too():
    tools = [{"type": "function", "function": {"name": f"tool_{n}", "description": "x" * 400,
                                               "parameters": {"type": "object"}}} for n in range(5)]

    async def stream_chat(**_):
        yield 'data: {"choices":[{"delta":{"content":"Bir gün"}}]}\n\n'
        await asyncio.sleep(3600)

    estimates = []
    for given in ({}, {"tools": tools}):
        telemetry = SimpleNamespace(log_usage=AsyncMock())
        runner = ChatRunner(None, None, None, telemetry)
        stream = runner.stream(SimpleNamespace(stream_chat=stream_chat), None, "deepseek", "m",
                               [{"role": "user", "content": "fıkra"}], None, None, log_id=1, **given)

        async def consume():
            async for _ in stream:
                pass
        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.gather(*list(runner._log_writers))
        estimates.append(telemetry.log_usage.await_args.args[3]["prompt_tokens"])
    assert estimates[1] > estimates[0] + 500


import os
import unittest
import uuid


@unittest.skipUnless(os.getenv('ORION_IMAGE_TEST_PORT'), 'Requires disposable PostgreSQL cluster')
class RecoveredUsageInTheDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        from database.manager import DatabaseManager
        port = int(os.environ['ORION_IMAGE_TEST_PORT'])
        self.schema = 'stopped_usage_test_' + uuid.uuid4().hex
        self.connection = await asyncpg.connect(host='127.0.0.1', port=port, user='postgres', database='postgres')
        await self.connection.execute(f'CREATE SCHEMA "{self.schema}"')
        self.manager = DatabaseManager()
        self.manager.pool = await asyncpg.create_pool(host='127.0.0.1', port=port, user='postgres', database='postgres',
                                                      min_size=1, max_size=4, server_settings={'search_path': self.schema})
        async with self.manager.pool.acquire() as conn:
            with patch.object(self.manager, '_seed_default_models', AsyncMock()), \
                    patch.object(self.manager, '_seed_admin_secret', AsyncMock()), \
                    patch.object(self.manager, '_migrate_legacy_provider_keys', AsyncMock()), \
                    patch.object(self.manager, '_migrate_plaintext_keys', AsyncMock()):
                await self.manager._ensure_tables(conn)

    async def asyncTearDown(self):
        await self.manager.pool.close()
        assert self.schema.startswith('stopped_usage_test_')
        await self.connection.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.connection.close()

    async def row(self, log_id):
        return await self.manager.fetchrow(
            'SELECT status, prompt_tokens, cached_tokens, cost, usage_estimated FROM router_request_logs WHERE id=$1',
            log_id)

    async def test_the_providers_usage_replaces_the_estimate_once(self):
        log_id = await self.manager.create_streaming_log(None, 'openrouter', 'm', '{}', '{}', capability='chat')
        write = self.manager.update_streaming_log
        await write(log_id, status='interrupted', success=None, prompt_tokens=351, cost=0.001,
                    capability='chat', usage_estimated=True)
        await write(log_id, status='interrupted', success=None, prompt_tokens=774, cached_tokens=656, cost=0.0004,
                    capability='chat', usage_estimated=False)
        row = await self.row(log_id)
        assert (row['status'], row['prompt_tokens'], row['cached_tokens'], row['usage_estimated']) == \
            ('interrupted', 774, 656, False)
        # Settled: a later estimate (or a second recovery) changes nothing.
        await write(log_id, status='interrupted', success=None, prompt_tokens=1, cost=9.0,
                    capability='chat', usage_estimated=True)
        await write(log_id, status='interrupted', success=None, prompt_tokens=2, cost=9.0,
                    capability='chat', usage_estimated=False)
        assert (await self.row(log_id))['prompt_tokens'] == 774


def test_the_estimate_counts_by_script():
    from core.token_estimate import prompt_tokens, text_tokens
    assert text_tokens('a' * 400) == 100            # Latin: about four letters a token.
    assert text_tokens('привет' * 10) == 30          # Cyrillic: about two.
    assert text_tokens('你好世界' * 25) == 100       # Chinese: about one a character, not a quarter.
    assert text_tokens('ı' * 40) == 10               # Turkish letters as letters, never as ı.
    tools = [{"type": "function", "function": {"name": "t", "description": "x" * 400}}]
    assert prompt_tokens([{"role": "user", "content": "hi"}], tools) > 100   # The tools count.
    parts = [{"type": "text", "text": "a" * 40}, {"type": "image_url", "image_url": {"url": "data:..."}}]
    assert prompt_tokens([{"role": "user", "content": parts}]) == 4 + 10
