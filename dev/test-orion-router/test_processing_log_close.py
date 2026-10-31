"""A chat request's log never stays "processing" when the request ends before a provider took it over."""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.router.route_types import ResolvedRoute, RoutePlan
from core.router.runners.chat import ChatRunner


def make_runner(get_keys, stream_chat=None):
    telemetry = SimpleNamespace(
        create_processing_log=AsyncMock(return_value=7),
        finish_processing_log=AsyncMock(),
        log_usage=AsyncMock(),
        update_processing_request=AsyncMock(),
    )
    resolver = SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(
        ResolvedRoute(provider="gemini", model="gemini-test"),
    ))))
    runner = ChatRunner(
        registry=SimpleNamespace(chat_providers={"gemini": SimpleNamespace(stream_chat=stream_chat)}),
        route_resolver=resolver,
        key_pool=SimpleNamespace(get_keys_for_provider=get_keys, mark_key_error=AsyncMock()),
        telemetry=telemetry,
    )
    return runner, telemetry


MESSAGES = [{"role": "user", "content": "hello"}]


class ProcessingLogClose(unittest.IsolatedAsyncioTestCase):
    async def test_client_leaving_while_keys_are_picked_closes_the_log(self):
        waiting = asyncio.Event()

        async def get_keys(*args, **kwargs):
            waiting.set()
            await asyncio.Event().wait()

        runner, telemetry = make_runner(get_keys)

        async def consume():
            async for _ in runner.run_combo(provider=None, model="m", messages=MESSAGES):
                pass

        task = asyncio.create_task(consume())
        await waiting.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        telemetry.finish_processing_log.assert_awaited_once()
        log_id, response, status, success = telemetry.finish_processing_log.await_args.args
        self.assertEqual((log_id, status, success), (7, "interrupted", None))
        self.assertIn("cancelled", response["error"].lower())

    async def test_unexpected_error_before_the_provider_closes_the_log_as_failed(self):
        runner, telemetry = make_runner(AsyncMock(side_effect=RuntimeError("key store down")))
        with self.assertRaises(RuntimeError):
            _ = [chunk async for chunk in runner.run_combo(provider=None, model="m", messages=MESSAGES)]
        log_id, response, status, success = telemetry.finish_processing_log.await_args.args
        self.assertEqual((log_id, status, success), (7, "failed", False))
        self.assertIn("key store down", response["error"])

    async def test_finished_stream_leaves_the_log_to_the_stream(self):
        async def stream_chat(**kwargs):
            yield 'data: {"choices": [{"delta": {"content": "hi"}}]}\n\n'
            yield {"internal_usage": {"prompt_tokens": 5, "completion_tokens": 1}}

        runner, telemetry = make_runner(AsyncMock(return_value=[(None, None)]), stream_chat)
        chunks = [chunk async for chunk in runner.run_combo(provider=None, model="m", messages=MESSAGES)]
        await asyncio.gather(*runner._log_writers)
        self.assertIn("hi", "".join(chunks))
        telemetry.finish_processing_log.assert_not_awaited()
        self.assertEqual(telemetry.log_usage.await_args.kwargs["log_id"], 7)

    async def test_client_leaving_mid_stream_leaves_the_log_to_the_stream(self):
        async def stream_chat(**kwargs):
            yield 'data: {"choices": [{"delta": {"content": "one"}}]}\n\n'
            await asyncio.Event().wait()

        runner, telemetry = make_runner(AsyncMock(return_value=[(None, None)]), stream_chat)
        combo = runner.run_combo(provider=None, model="m", messages=MESSAGES)
        self.assertIn("one", await combo.__anext__())
        await combo.aclose()
        telemetry.finish_processing_log.assert_not_awaited()

    async def test_closed_log_is_not_closed_twice(self):
        runner, telemetry = make_runner(AsyncMock(return_value=[]))
        runner.route_resolver.resolve = AsyncMock(side_effect=ValueError("no such model"))
        _ = [chunk async for chunk in runner.run_combo(provider=None, model="m", messages=MESSAGES)]
        telemetry.finish_processing_log.assert_awaited_once()
        self.assertEqual(telemetry.finish_processing_log.await_args.args[2], "failed")


if __name__ == "__main__":
    unittest.main()
