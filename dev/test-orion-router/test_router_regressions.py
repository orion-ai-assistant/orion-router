"""Offline regressions for dashboard keys, OpenRouter credentials and video URLs."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.admin import update_provider_key_pool_item
from core.router.route_types import ResolvedRoute, RoutePlan
from core.router.routing_services import ProviderKeyPool
from core.router.runners.chat import ChatRunner
from core.router.telemetry import TelemetryService
from providers.local.chat import LocalChatProvider
from core.security import decrypt, encrypt
from providers.openrouter.chat import OpenRouterChatProvider, transform_openrouter_messages


class RouterRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_logs_actual_model_provider_and_payload(self):
        async def failed_local(**kwargs):
            yield 'data: {"error": {"message": "connection refused"}}\n\n'

        async def successful_chat(**kwargs):
            yield 'data: {"choices": [{"delta": {"content": "hello"}}]}\n\n'
            yield {"internal_usage": {"prompt_tokens": 12, "completion_tokens": 3}}

        local = LocalChatProvider()
        local.stream_chat = failed_local
        resolver = SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan(routes=(
            ResolvedRoute(provider="local", model="local-chat"),
            ResolvedRoute(provider="gemini", model="gemini-test", temperature=0.5),
        ))))
        runner = ChatRunner(
            registry=SimpleNamespace(chat_providers={
                "local": local, "gemini": SimpleNamespace(stream_chat=successful_chat),
            }),
            route_resolver=resolver,
            key_pool=SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[(None, None)]),
                                     mark_key_error=AsyncMock()),
            telemetry=TelemetryService(),
        )
        tasks = []
        create_task = asyncio.create_task

        def track_task(coro):
            task = create_task(coro)
            tasks.append(task)
            return task

        with patch("core.router.telemetry.db_manager.create_streaming_log", AsyncMock(return_value=42)) as create, patch(
            "core.router.telemetry.db_manager.update_streaming_log", AsyncMock()
        ) as update, patch("core.router.telemetry.db_manager.update_streaming_request", AsyncMock()), patch(
            "core.router.runners.chat.asyncio.create_task", side_effect=track_task
        ):
            chunks = [chunk async for chunk in runner.run_combo(
                provider=None, model="sdf", messages=[{"role": "user", "content": "hello"}],
            )]
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.gather(*tasks)
            self.assertIn("hello", "".join(chunks))
            self.assertNotIn("connection refused", "".join(chunks))
            self.assertEqual(create.await_args.kwargs["model"], "sdf")
            result = next(call.kwargs for call in update.await_args_list if call.kwargs["success"] is True)
            self.assertEqual(result["log_id"], 42)
            self.assertEqual(result["provider"], "gemini")
            self.assertEqual(result["model"], "gemini-test")
            payload = json.loads(result["request_json"])
            self.assertEqual(payload["model"], "gemini-test")
            self.assertEqual(payload["temperature"], 0.5)
            self.assertNotIn("repeat_penalty", payload)

    async def test_local_log_keeps_exact_upstream_payload(self):
        local = LocalChatProvider()

        async def successful_chat(**kwargs):
            yield 'data: {"choices": [{"delta": {"content": "hello"}}]}\n\n'

        local.stream_chat = successful_chat
        telemetry = AsyncMock()
        runner = ChatRunner(None, None, None, telemetry)
        messages = [{"role": "user", "content": "hello"}]
        _ = [chunk async for chunk in runner.stream(
            local, None, "local", "local-chat", messages, None, None,
            log_id=1, thinking_level="none", temperature=0.5,
        )]
        await asyncio.sleep(0)
        payload = json.loads(telemetry.log_usage.await_args.kwargs["request_json"])
        self.assertEqual(payload, local.build_payload(
            "local-chat", messages, thinking_level="none", temperature=0.5,
        ))

    async def test_dashboard_replace_and_toggle_key(self):
        stored = encrypt("old-provider-key")
        existing = dict(provider="openrouter", label="test", api_key=stored,
                        priority=100, is_active=True)
        for body in ({"api_key": "new-provider-key"}, {"is_active": False},
                     {"is_active": True}, {"api_key": "", "label": "renamed"}):
            with self.subTest(body=body):
                request = SimpleNamespace(json=AsyncMock(return_value=body))
                fetch = AsyncMock(side_effect=[existing, {"id": "key-id"}])
                with patch("api.admin.db_manager.fetchrow", fetch):
                    result = await update_provider_key_pool_item("key-id", request)
                self.assertEqual(result, {"id": "key-id"})
                args = fetch.await_args_list[1].args
                replaced = bool(body.get("api_key"))
                self.assertEqual(decrypt(args[4]), "new-provider-key" if replaced else "old-provider-key")
                self.assertEqual(args[6], body.get("is_active", True))
                self.assertEqual(args[7], replaced)

    async def test_missing_pool_never_uses_incoming_credentials(self):
        pool = ProviderKeyPool()
        for token in ("orion", "Bearer orion", "Bearer custom-admin-secret", "sk-orion-test", None):
            with self.subTest(token=token), patch(
                "core.router.routing_services.db_manager.get_active_provider_keys",
                AsyncMock(return_value=[]),
            ):
                self.assertEqual(await pool.get_keys_for_provider("openrouter", token), [(None, None)])

    async def test_configured_provider_keys_still_work(self):
        pool = ProviderKeyPool(SimpleNamespace(provider_keys={"openrouter": "configured-key"}))
        with patch("core.router.routing_services.db_manager.get_active_provider_keys",
                   AsyncMock(return_value=[])):
            self.assertEqual(await pool.get_keys_for_provider("openrouter", "orion"), [("configured-key", None)])
        with patch("core.router.routing_services.db_manager.get_active_provider_keys",
                   AsyncMock(return_value=[{"api_key": "pool-key", "id": "pool-id"}])):
            self.assertEqual(await pool.get_keys_for_provider("openrouter", "orion"), [("pool-key", "pool-id")])

    async def test_runner_missing_keys_fails_before_network(self):
        for routes in ((ResolvedRoute(provider="openrouter", model="test-model"),), ()):
            with self.subTest(routes=routes):
                resolver = AsyncMock()
                resolver.resolve.return_value = RoutePlan(routes=routes, requested_provider="openrouter")
                runner = ChatRunner(
                    registry=SimpleNamespace(chat_providers={"openrouter": OpenRouterChatProvider()}),
                    route_resolver=resolver, key_pool=ProviderKeyPool(), telemetry=AsyncMock(),
                )
                with patch("core.router.routing_services.db_manager.get_active_provider_keys", AsyncMock(return_value=[])), patch(
                    "providers.openrouter.chat.get_http_client"
                ) as network:
                    chunks = [chunk async for chunk in runner.run_combo(
                        provider="openrouter", model="test-model", api_key="orion",
                        auth_header="Bearer orion", messages=[{"role": "user", "content": "hello"}],
                    )]
                self.assertIn("No API key provided", "".join(chunks))
                network.assert_not_called()

    def test_video_url_is_preserved(self):
        for url in ("https://example.com/video.mp4", "data:video/mp4;base64,YWJj"):
            messages = [{"role": "user", "content": [
                {"type": "text", "text": "before"},
                {"type": "input_video", "input_video": {"url": url}},
                {"type": "text", "text": "after"},
            ]}]
            content = transform_openrouter_messages(messages)[0]["content"]
            self.assertEqual(content[1], {"type": "video_url", "video_url": {"url": url}})
            self.assertEqual(content[0], messages[0]["content"][0])
            self.assertEqual(content[2], messages[0]["content"][2])
            self.assertIn("input_video", messages[0]["content"][1])

    def test_empty_video_is_rejected(self):
        for video in ({}, {"url": ""}, {"data": ""}, {"url": "  "}, {"data": 123}):
            with self.subTest(video=video), self.assertRaisesRegex(ValueError, "non-empty data or url"):
                transform_openrouter_messages([{"role": "user", "content": [
                    {"type": "input_video", "input_video": video},
                ]}])


if __name__ == "__main__":
    unittest.main()
