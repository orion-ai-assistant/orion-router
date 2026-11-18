"""
dev/test-orion-router/test_log_privacy.py
-----------------------------------------
The Hub's log-privacy headers (x-orion-log-content, x-orion-memory-profile, x-orion-purpose):
what the request log stores, for streaming and non-streaming requests, and that nothing reaches a provider.
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
from core.log_privacy import HIDDEN_MARKER, LogPolicy, policy_from_headers, scrub_request, scrub_response, set_policy
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
        self.assertEqual(policy_from_headers({"x-orion-log-content": "hidden", "x-orion-purpose": "memory-extraction"}),
                         LogPolicy(hidden=True, purpose="memory-extraction"))
        self.assertEqual(policy_from_headers({"x-orion-memory-profile": PROFILE_HEADER}),
                         LogPolicy(profile=PROFILE_HEADER))
        # "show" is the explicit opt-in: the profile is logged in full.
        self.assertIsNone(policy_from_headers({"x-orion-log-content": "show", "x-orion-memory-profile": PROFILE_HEADER}))
        # Unknown / malformed values behave as absent.
        self.assertIsNone(policy_from_headers({"x-orion-log-content": "maybe"}))
        self.assertIsNone(policy_from_headers({"x-orion-memory-profile": "tokens=abc; facts=<script>"}))
        self.assertIsNone(policy_from_headers({"x-orion-memory-profile": "x" * 100000}))
        self.assertEqual(policy_from_headers({"x-orion-log-content": "hidden", "x-orion-purpose": "bad purpose!"}),
                         LogPolicy(hidden=True))
        self.assertIsNone(policy_from_headers(None))

    def test_profile_block_replaced_in_logged_copy_only(self):
        request = {"model": "m", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hi"}]}
        set_policy(LogPolicy(profile=PROFILE_HEADER))
        logged = scrub_request(request)
        self.assertEqual(logged["messages"][0]["content"], "You are Orion.\n\n[hafıza profili: tokens=42; facts=1,2,3]")
        self.assertEqual(logged["messages"][1]["content"], "hi")
        self.assertIn("Ayse", request["messages"][0]["content"])  # the sent request is untouched
        # Provider-shaped bodies (parts, system field) and JSON strings are handled too.
        gemini = {"systemInstruction": {"parts": [{"text": SYSTEM}]}}
        self.assertNotIn("Ayse", scrub_request(json.dumps(gemini)))
        self.assertIn("[hafıza profili: tokens=42; facts=1,2,3]", scrub_request(json.dumps(gemini)))
        # A profile block alone (empty system prompt) and text after it.
        self.assertEqual(scrub_request({"s": PROFILE})["s"], "[hafıza profili: tokens=42; facts=1,2,3]")
        self.assertEqual(scrub_request({"s": PROFILE + "\n\nAfter."})["s"],
                         "[hafıza profili: tokens=42; facts=1,2,3]\n\nAfter.")

    def test_hidden_keeps_metadata_only(self):
        set_policy(LogPolicy(hidden=True, purpose="memory-extraction"))
        logged = scrub_request({"model": "m", "temperature": 0.1, "messages": [{"role": "user", "content": "secret"}],
                                "tools": [{"function": {"name": "secret_tool"}}]})
        self.assertEqual(logged, {"model": "m", "temperature": 0.1, "messages": HIDDEN_MARKER,
                                  "content_hidden": True, "purpose": "memory-extraction"})
        res = scrub_response({"choices": [{"message": {"content": "secret", "tool_calls": [{"x": "secret"}]}}],
                              "usage": {"prompt_tokens": 5}, "metrics": {"total_duration_ms": 3}})
        self.assertNotIn("secret", json.dumps(res))
        self.assertEqual(res["usage"], {"prompt_tokens": 5})
        self.assertTrue(res["content_hidden"])

    def test_no_policy_changes_nothing(self):
        request = {"messages": [{"role": "system", "content": SYSTEM}]}
        self.assertIs(scrub_request(request), request)
        self.assertEqual(scrub_response({"a": 1}), {"a": 1})


class TelemetryTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        set_policy(None)

    async def test_telemetry_writes_scrubbed_copies(self):
        set_policy(LogPolicy(hidden=True, purpose="memory-extraction"))
        db = SimpleNamespace(
            create_streaming_log=AsyncMock(return_value=7), update_streaming_log=AsyncMock(),
            update_streaming_request=AsyncMock(), log_request=AsyncMock())
        with patch("core.router.telemetry.db_manager", db):
            service = TelemetryService(SimpleNamespace(pricing_cache={}))
            req = {"model": "m", "messages": [{"role": "user", "content": "secret"}]}
            await service.create_processing_log("k", "openai", "m", "chat", req)
            await service.update_processing_request(7, req)
            await service.finish_processing_log(7, {"choices": [{"message": {"content": "secret"}}]}, "success", True)
            await service.log_usage("k", "openai", "m", {"prompt_tokens": 1, "completion_tokens": 2}, log_id=7,
                                    request_json=json.dumps(req), response_json=json.dumps({"choices": [{"message": {"content": "secret"}}]}))
        written = json.dumps([db.create_streaming_log.await_args.kwargs, db.update_streaming_request.await_args.args,
                              db.update_streaming_log.await_args_list[0].kwargs, db.update_streaming_log.await_args_list[1].kwargs], ensure_ascii=False)
        self.assertNotIn("secret", written)
        self.assertIn(HIDDEN_MARKER, written)
        self.assertEqual(db.update_streaming_log.await_args_list[1].kwargs["prompt_tokens"], 1)  # metadata stays


class EndpointTests(unittest.TestCase):
    """The policy set by the endpoint reaches the log writes of streaming and non-streaming requests."""

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

    def test_hidden_streaming_and_not(self):
        for stream in (True, False):
            seen = self._post({"x-orion-log-content": "hidden", "x-orion-purpose": "memory-extraction"}, stream)
            self.assertNotIn("secret", seen["logged"])
            self.assertIn("content_hidden", seen["logged"])
            # The provider path got the real messages and no header-derived argument.
            self.assertEqual(seen["messages"][1]["content"], "secret")
            self.assertFalse([k for k in seen if "orion" in k or "purpose" in k or "log_content" in k])

    def test_profile_replaced_and_show_opt_in(self):
        for stream in (True, False):
            seen = self._post({"x-orion-memory-profile": PROFILE_HEADER}, stream)
            self.assertNotIn("Ayse", seen["logged"])
            self.assertIn("[hafıza profili: tokens=42; facts=1,2,3]", seen["logged"])
            self.assertIn("secret", seen["logged"])
            self.assertIn("Ayse", seen["messages"][0]["content"])
            shown = self._post({"x-orion-memory-profile": PROFILE_HEADER, "x-orion-log-content": "show"}, stream)
            self.assertIn("Ayse", shown["logged"])

    def test_malformed_headers_never_break_the_request(self):
        seen = self._post({"x-orion-memory-profile": "tokens=;;; facts=\x7f", "x-orion-log-content": "???"}, False)
        self.assertIn("Ayse", seen["logged"])


if __name__ == "__main__":
    unittest.main()
