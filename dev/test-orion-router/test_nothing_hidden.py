"""The Router sends only what the request or the model's own saved settings give, and logs what it put in itself
("added_by_router"): no hidden defaults."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.router.route_types import ResolvedRoute, RoutePlan
from core.router.runners.chat import ChatRunner

MESSAGES = [{"role": "user", "content": "merhaba"}]


def chat_runner(route, provider_name):
    sent = {}

    async def stream_chat(**kwargs):
        sent.update(kwargs)
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
    async def test_what_the_model_sets_is_sent_and_logged_as_added(self):
        route = ResolvedRoute(provider="gemini", model="gemini-test", temperature=0.7, system_prompt="Kısa yaz.",
                              thinking_level="low")
        runner, telemetry, sent = chat_runner(route, "gemini")
        await run(runner)
        self.assertEqual(sent["temperature"], 0.7)
        self.assertEqual(logged_request(telemetry)["added_by_router"],
                         {"temperature": 0.7, "system_prompt": "Kısa yaz.", "thinking": "low"})

    async def test_a_model_with_nothing_set_gets_nothing_added(self):
        runner, telemetry, sent = chat_runner(ResolvedRoute(provider="gemini", model="gemini-test"), "gemini")
        await run(runner)
        self.assertNotIn("temperature", sent)
        self.assertNotIn("added_by_router", logged_request(telemetry))

    async def test_the_callers_own_values_are_not_listed_as_added(self):
        route = ResolvedRoute(provider="gemini", model="gemini-test", temperature=0.7)
        runner, telemetry, sent = chat_runner(route, "gemini")
        await run(runner, temperature=0.2)
        self.assertEqual(sent["temperature"], 0.2)
        self.assertNotIn("added_by_router", logged_request(telemetry))

    async def test_a_local_model_gets_only_its_saved_sampling(self):
        # No catalog values put in behind the page's back: what the model saved (top_k here) goes, the rest is the
        # local server's own.
        route = ResolvedRoute(provider="local", model="local-chat", default_config={"local_sampling": {"top_k": 20}})
        runner, telemetry, sent = chat_runner(route, "local")
        await run(runner)
        self.assertEqual(sent.get("top_k"), 20)
        for key in ("top_p", "min_p", "repeat_penalty", "temperature"):
            self.assertNotIn(key, sent)
        self.assertEqual(logged_request(telemetry)["added_by_router"], {"top_k": 20})


class LocalTtsPayloadTests(unittest.TestCase):
    def test_only_given_values_go_to_the_local_tts_service(self):
        from providers.local.tts import LocalTTSProvider
        payload = LocalTTSProvider()._payload("local-tts", "Merhaba.", None, {"response_format": "pcm"})
        for key in ("speed", "seed", "language", "steps", "creativity", "guidance_scale"):
            self.assertNotIn(key, payload)
        given = LocalTTSProvider()._payload("local-tts", "Merhaba.", None,
                                            {"speed": "1.2", "seed": 32, "language": "Turkish"})
        self.assertEqual((given["speed"], given["seed"], given["language"]), (1.2, 32, "Turkish"))


class CloudTtsVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_voice_a_provider_needs_is_named_and_logged(self):
        from core.router.runners.tts import TTSRunner
        from providers.openai.tts import OpenAITTSProvider
        plugin = OpenAITTSProvider()
        plugin.generate_speech = AsyncMock(return_value=(b"wav", "audio/wav", {}))
        telemetry = SimpleNamespace(create_processing_log=AsyncMock(return_value=4), log_usage=AsyncMock(),
                                    finish_processing_log=AsyncMock(), update_processing_request=AsyncMock())
        runner = TTSRunner(
            SimpleNamespace(tts_providers={"openai": plugin}),
            SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(
                ResolvedRoute(provider="openai", model="tts-1"),)))),
            SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[("k", "k-id")]), mark_key_error=AsyncMock()),
            telemetry,
        )
        class NoArchive:  # the real one starts a writer thread that the closed log call would leave running
            metadata = {}
            error = None
            def set_metadata(self, meta): pass
            def feed(self, chunk): pass

        with patch("core.router.runners.tts.background", lambda coro: coro.close()),                 patch("core.router.runners.tts.ArchiveSession", NoArchive):
            await runner.run_speech("openai", "tts-1", "Merhaba.")
        self.assertEqual(plugin.generate_speech.await_args.kwargs["voice"], "alloy")
        _, logged = telemetry.update_processing_request.await_args.args
        self.assertEqual(logged["added_by_router"], {"voice": "alloy"})


if __name__ == "__main__":
    unittest.main()
