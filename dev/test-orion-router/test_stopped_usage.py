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
