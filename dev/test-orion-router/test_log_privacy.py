"""
dev/test-orion-router/test_log_privacy.py
-----------------------------------------
The Hub's log label headers (x-orion-memory-profile, x-orion-purpose): the request log keeps EVERYTHING
(full messages, memory profile block, answer) and only gains an extra label; nothing reaches a provider.
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import chat as chat_api
from core.dependencies import authenticate_request
from core.log_privacy import LogPolicy, policy_from_headers, scrub_request, set_policy
from core.router.telemetry import TelemetryService

PROFILE = (
    "What you know about the user (a profile built from their memory; use it quietly where it helps, "
    "never recite it):\n- Name is Ayse\n- Lives in Izmir"
)
SYSTEM = "You are Orion.\n\n" + PROFILE
PROFILE_HEADER = "tokens=42; facts=1,2,3"


class PolicyTests(unittest.TestCase):
    def tearDown(self):
        set_policy(None)

    def test_headers_to_policy(self):
        self.assertEqual(policy_from_headers({"x-orion-purpose": "memory-extraction"}),
                         LogPolicy(purpose="memory-extraction"))
        self.assertEqual(policy_from_headers({"x-orion-memory-profile": PROFILE_HEADER}),
                         LogPolicy(profile=PROFILE_HEADER))
        # x-orion-log-content has no effect any more: hidden does not hide, show changes nothing.
        self.assertIsNone(policy_from_headers({"x-orion-log-content": "hidden"}))
        self.assertEqual(policy_from_headers({"x-orion-log-content": "show", "x-orion-memory-profile": PROFILE_HEADER}),
                         LogPolicy(profile=PROFILE_HEADER))
        # Malformed values are ignored.
        self.assertIsNone(policy_from_headers({"x-orion-memory-profile": "tokens=abc; facts=<script>"}))
        self.assertIsNone(policy_from_headers({"x-orion-memory-profile": "x" * 100000}))
        self.assertIsNone(policy_from_headers({"x-orion-purpose": "bad purpose!"}))
        self.assertIsNone(policy_from_headers(None))

    def test_content_stays_in_full_and_labels_are_added(self):
        request = {"model": "m", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hi"}]}
        set_policy(LogPolicy(profile=PROFILE_HEADER, purpose="memory-extraction"))
        logged = scrub_request(request)
        self.assertEqual(logged["messages"], request["messages"])  # profile block and all text untouched
        self.assertIn("Ayse", json.dumps(logged))
        self.assertEqual(logged["orion_log"]["etiketler"], ["hafıza profili: 42 token", "amaç: hafıza çıkarımı"])
        self.assertEqual(logged["orion_log"]["memory_profile"], PROFILE_HEADER)
        self.assertNotIn("orion_log", request)  # the sent request is untouched
        as_text = json.loads(scrub_request(json.dumps(request)))
        self.assertEqual(as_text["messages"], request["messages"])
        self.assertIn("amaç: hafıza çıkarımı", as_text["orion_log"]["etiketler"])
        self.assertNotIn("[içerik gizli]", json.dumps(logged, ensure_ascii=False))

    def test_unknown_purpose_label_and_no_policy(self):
        set_policy(LogPolicy(purpose="chat-title"))
        self.assertEqual(scrub_request({"a": 1})["orion_log"]["etiketler"], ["amaç: chat-title"])
        set_policy(None)
        request = {"messages": [{"role": "system", "content": SYSTEM}]}
        self.assertIs(scrub_request(request), request)


class TelemetryTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        set_policy(None)

    async def test_telemetry_logs_full_content_with_label(self):
        set_policy(LogPolicy(profile=PROFILE_HEADER, purpose="memory-extraction"))
        db = SimpleNamespace(
            create_streaming_log=AsyncMock(return_value=7), update_streaming_log=AsyncMock(),
            update_streaming_request=AsyncMock(), log_request=AsyncMock())
        answer = {"choices": [{"message": {"content": "the answer"}}]}
        with patch("core.router.telemetry.db_manager", db):
            service = TelemetryService(SimpleNamespace(pricing_cache={}))
            req = {"model": "m", "messages": [{"role": "user", "content": "secret"}]}
            await service.create_processing_log("k", "openai", "m", "chat", req)
            await service.update_processing_request(7, req)
            await service.finish_processing_log(7, answer, "success", True)
            await service.log_usage("k", "openai", "m", {"prompt_tokens": 1, "completion_tokens": 2}, log_id=7,
                                    request_json=json.dumps(req), response_json=json.dumps(answer))
        written = json.dumps([db.create_streaming_log.await_args.kwargs, db.update_streaming_request.await_args.args,
                              db.update_streaming_log.await_args_list[0].kwargs, db.update_streaming_log.await_args_list[1].kwargs], ensure_ascii=False)
        self.assertIn("secret", written)
        self.assertIn("the answer", written)
        self.assertNotIn("içerik gizli", written)
        self.assertIn("amaç: hafıza çıkarımı", written)
        self.assertEqual(db.update_streaming_log.await_args_list[1].kwargs["prompt_tokens"], 1)


class EndpointTests(unittest.TestCase):
    """The labels set by the endpoint reach the log writes of streaming and non-streaming requests."""

    def _client(self, seen):
        async def run_combo(**kwargs):
            seen.update(kwargs)
            telemetry = TelemetryService(SimpleNamespace(pricing_cache={}))
            db = SimpleNamespace(create_streaming_log=AsyncMock(return_value=1), update_streaming_log=AsyncMock(),
                                 update_streaming_request=AsyncMock(), log_request=AsyncMock())
            with patch("core.router.telemetry.db_manager", db):
                await telemetry.create_processing_log("k", "openai", kwargs["model"], "chat",
                                                      {"model": kwargs["model"], "messages": kwargs["messages"]})
            seen["logged"] = db.create_streaming_log.await_args.kwargs["request_json"]
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            yield "data: [DONE]\n\n"

        app = FastAPI()
        app.include_router(chat_api.router)
        app.dependency_overrides[authenticate_request] = lambda: {"key_id": "k"}
        app.state.dynamic_router = SimpleNamespace(run_combo=run_combo)
        return TestClient(app)

    def _post(self, headers, stream):
        seen: dict = {}
        body = {"model": "m", "stream": stream,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "secret"}]}
        response = self._client(seen).post("/v1/chat/completions", json=body, headers=headers)
        self.assertEqual(response.status_code, 200)
        return seen

    def test_purpose_label_full_content(self):
        for stream in (True, False):
            # Even the old "hidden" value hides nothing now.
            seen = self._post({"x-orion-log-content": "hidden", "x-orion-purpose": "memory-extraction"}, stream)
            self.assertIn("secret", seen["logged"])
            self.assertNotIn("içerik gizli", seen["logged"])
            self.assertIn("amaç: hafıza çıkarımı", seen["logged"])
            # The provider path got the real messages and no header-derived argument.
            self.assertEqual(seen["messages"][1]["content"], "secret")
            self.assertFalse([k for k in seen if "orion" in k or "purpose" in k or "log_content" in k])

    def test_profile_block_stays_with_label(self):
        for stream in (True, False):
            seen = self._post({"x-orion-memory-profile": PROFILE_HEADER}, stream)
            self.assertIn("Ayse", seen["logged"])
            self.assertIn("secret", seen["logged"])
            self.assertNotIn("[hafıza profili: tokens=", seen["logged"])
            self.assertIn("hafıza profili: 42 token", seen["logged"])
            self.assertIn("Ayse", seen["messages"][0]["content"])

    def test_malformed_headers_never_break_the_request(self):
        seen = self._post({"x-orion-memory-profile": "tokens=;;; facts=\x7f", "x-orion-log-content": "???"}, False)
        self.assertIn("Ayse", seen["logged"])
        self.assertNotIn("orion_log", seen["logged"])


if __name__ == "__main__":
    unittest.main()
