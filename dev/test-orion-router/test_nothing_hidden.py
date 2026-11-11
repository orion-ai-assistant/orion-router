"""The request log is the body the provider was sent, as it was sent (core/outgoing.py), and the Router sends only
what the request or the model's own saved settings give: no hidden defaults."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.outgoing import record, record_httpx_request
from core.router.route_types import ResolvedRoute, RoutePlan
from core.router.runners.chat import ChatRunner

MESSAGES = [{"role": "user", "content": "merhaba"}]


def chat_runner(route, provider_name):
    sent = {}

    async def stream_chat(**kwargs):
        sent.update(kwargs)
        body = {"model": kwargs["model"], "messages": kwargs["messages"],
                **{k: kwargs[k] for k in ("temperature", "top_k", "top_p", "min_p") if k in kwargs}}
        record(body)  # as the HTTP client does when the request leaves
        sent["_body"] = body
        yield 'data: {"choices":[{"delta":{"content":"selam"}}]}\n\n'

    telemetry = SimpleNamespace(create_processing_log=AsyncMock(return_value=3), finish_processing_log=AsyncMock(),
                                log_usage=AsyncMock(), update_processing_request=AsyncMock())
    runner = ChatRunner(
        registry=SimpleNamespace(chat_providers={provider_name: SimpleNamespace(stream_chat=stream_chat)}),
        route_resolver=SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(route,)))),
        key_pool=SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[("k", "k-id")]), mark_key_error=AsyncMock()),
        telemetry=telemetry,
    )
    return runner, telemetry, sent


async def run(runner, **request):
    chunks = [c async for c in runner.run_combo(provider=None, model="m", messages=MESSAGES, **request)]
    await asyncio.gather(*list(runner._log_writers))  # the final log is written by a task of its own
    return chunks


def logged_request(telemetry) -> dict:
    return json.loads(telemetry.log_usage.await_args.kwargs["request_json"])


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_log_is_the_body_sent_with_the_models_settings_in_it(self):
        route = ResolvedRoute(provider="gemini", model="gemini-test", temperature=0.7)
        runner, telemetry, sent = chat_runner(route, "gemini")
        await run(runner)
        self.assertEqual(sent["temperature"], 0.7)
        self.assertEqual(logged_request(telemetry), sent["_body"])
        self.assertEqual(telemetry.update_processing_request.await_args.args, (3, sent["_body"]))

    async def test_a_model_with_nothing_set_gets_nothing_added(self):
        runner, telemetry, sent = chat_runner(ResolvedRoute(provider="gemini", model="gemini-test"), "gemini")
        await run(runner)
        self.assertNotIn("temperature", sent)
        self.assertNotIn("temperature", logged_request(telemetry))

    async def test_the_callers_own_values_win(self):
        route = ResolvedRoute(provider="gemini", model="gemini-test", temperature=0.7)
        runner, telemetry, sent = chat_runner(route, "gemini")
        await run(runner, temperature=0.2)
        self.assertEqual(logged_request(telemetry)["temperature"], 0.2)

    async def test_a_local_model_gets_only_its_saved_sampling(self):
        # No catalog values put in behind the page's back: what the model saved (top_k here) goes, the rest is the
        # local server's own.
        route = ResolvedRoute(provider="local", model="local-chat", default_config={"local_sampling": {"top_k": 20}})
        runner, telemetry, sent = chat_runner(route, "local")
        await run(runner)
        self.assertEqual(sent.get("top_k"), 20)
        for key in ("top_p", "min_p", "repeat_penalty", "temperature"):
            self.assertNotIn(key, sent)
        self.assertEqual(logged_request(telemetry), sent["_body"])


    async def test_a_request_refused_before_any_answer_still_shows_what_was_sent(self):
        # DeepSeek with a wrong key: the request leaves, the answer is an error before any part of a reply.
        body = {"model": "deepseek-flash", "messages": MESSAGES, "stream": True}

        async def refused(**kwargs):
            record(body)
            raise RuntimeError("DeepSeek HTTP Error 401: Authentication Fails")
            yield  # an async generator, as providers are

        telemetry = SimpleNamespace(create_processing_log=AsyncMock(return_value=3), finish_processing_log=AsyncMock(),
                                    log_usage=AsyncMock(), update_processing_request=AsyncMock())
        runner = ChatRunner(
            registry=SimpleNamespace(chat_providers={"deepseek": SimpleNamespace(stream_chat=refused)}),
            route_resolver=SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(
                ResolvedRoute(provider="deepseek", model="deepseek-flash"),)))),
            key_pool=SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[("k", "k-id")]),
                                     mark_key_error=AsyncMock()),
            telemetry=telemetry,
        )
        await run(runner)
        self.assertIn(((3, body),), [c.args and (c.args,) for c in telemetry.update_processing_request.await_args_list])


class LocalTtsPayloadTests(unittest.TestCase):
    def test_only_given_values_go_to_the_local_tts_service(self):
        from providers.local.tts import LocalTTSProvider
        payload = LocalTTSProvider()._payload("local-tts", "Merhaba.", None, {"response_format": "pcm"})
        for key in ("speed", "seed", "language", "steps", "creativity", "guidance_scale"):
            self.assertNotIn(key, payload)
        given = LocalTTSProvider()._payload("local-tts", "Merhaba.", None,
                                            {"speed": "1.2", "seed": 32, "language": "Turkish"})
        self.assertEqual((given["speed"], given["seed"], given["language"]), (1.2, 32, "Turkish"))


class RealBodyTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_log_is_exactly_what_the_provider_api_received(self):
        # The real OpenAI provider, its HTTP client recording as the shared one does, against a stand-in server.
        from core.router.runners.tts import TTSRunner
        from providers.openai.tts import OpenAITTSProvider
        received = []

        def server(request):
            received.append(json.loads(request.content))
            return httpx.Response(200, content=b"RIFF0000WAVEfmt ", headers={"content-type": "audio/wav"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(server),
                                   event_hooks={"request": [record_httpx_request]})
        telemetry = SimpleNamespace(create_processing_log=AsyncMock(return_value=4), log_usage=AsyncMock(),
                                    finish_processing_log=AsyncMock(), update_processing_request=AsyncMock())
        runner = TTSRunner(
            SimpleNamespace(tts_providers={"openai": OpenAITTSProvider()}),
            SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(
                ResolvedRoute(provider="openai", model="tts-1"),)))),
            SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[("sk-test", "k-id")]), mark_key_error=AsyncMock()),
            telemetry,
        )

        class NoArchive:  # the real one starts a writer thread that the closed log call would leave running
            metadata = {}
            error = None
            def set_metadata(self, meta): pass
            def feed(self, chunk): pass

        with patch("providers.openai.tts.get_http_client", lambda timeout=None: client), \
                patch("core.router.runners.tts.background", lambda coro: coro.close()), \
                patch("core.router.runners.tts.ArchiveSession", NoArchive):
            await runner.run_speech("openai", "tts-1", "Merhaba.", speed=1.1)
        self.assertEqual(len(received), 1)
        _, logged = telemetry.update_processing_request.await_args.args
        self.assertEqual(logged, received[0])  # the very body the API got, nothing added or left out
        self.assertNotIn("sk-test", json.dumps(logged))  # the key travels in a header, never in the log


if __name__ == "__main__":
    unittest.main()
