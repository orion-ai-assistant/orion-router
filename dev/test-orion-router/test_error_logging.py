"""Offline checks for readable failures without losing response or debug details."""
import asyncio
import json
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import secret_guard
from core.logging_utils import diagnostic_text, log_http_exception, log_provider_failure
from core.router.runners.chat import ChatRunner, is_error_chunk
from core.router.telemetry import TelemetryService


class ErrorLoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        token = secret_guard._secrets.set(())
        self.addCleanup(secret_guard._secrets.reset, token)

    def test_diagnostics_are_redacted_bounded_and_single_line(self):
        secret_guard.remember("secret-fixture-key")
        value = diagnostic_text("secret-fixture-key\n\r\x1b[31m" + "x" * 2000)
        self.assertNotIn("secret-fixture-key", value)
        self.assertIn("[REDACTED]", value)
        self.assertLessEqual(len(value), 803)
        self.assertFalse(any(ord(char) < 32 for char in value))

    async def stream_failure(self, failure, provider="openrouter"):
        async def stream_chat(**kwargs):
            if isinstance(failure, Exception):
                raise failure
            yield failure

        runner = ChatRunner(None, None, None, AsyncMock())
        with self.assertLogs("service-router.dynamic", level="INFO") as captured:
            chunks = [chunk async for chunk in runner.stream(
                SimpleNamespace(stream_chat=stream_chat), None, provider, "test-model",
                [], None, None, log_id=42)]
            await asyncio.sleep(0)
        failures = [record for record in captured.records if "Chat failed" in record.getMessage()]
        self.assertEqual(len(failures), 1)
        self.assertIn("model=test-model log_id=42", failures[0].getMessage())
        self.assertIn("error", json.loads(chunks[0][5:]))
        return failures[0], "\n".join(captured.output)

    async def test_modality_rejection_is_a_warning_without_traceback(self):
        record, output = await self.stream_failure(ValueError("Model does not support audio, video input"))
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertIn("does not support audio", output)
        self.assertNotIn("Traceback", output)

    async def test_unexpected_bug_retains_traceback(self):
        record, output = await self.stream_failure(KeyError("broken-adapter"))
        self.assertEqual(record.levelno, logging.ERROR)
        self.assertIn("Traceback", output)
        self.assertIn("KeyError", output)

    async def test_openai_http_failures_keep_status_reason_and_code(self):
        for status, reason, code in (
            (400, "Unsupported parameter: temperature", "unsupported_parameter"),
            (401, "Invalid API key", "invalid_api_key"),
            (404, "Model not found", "model_not_found"),
            (429, "Rate limit exceeded", "rate_limit_exceeded"),
            (500, "Upstream unavailable", "server_error"),
        ):
            with self.subTest(status=status):
                body = json.dumps({"error": {"message": reason, "code": code, "unused": "x" * 2000}})
                record, output = await self.stream_failure(RuntimeError(f"OpenAI HTTP Error {status}: {body}"), "openai")
                self.assertIn(f"OpenAI HTTP Error {status}: {reason} (code={code})", output)
                self.assertIn("provider=openai", output)
                self.assertNotIn("unused", output)
                self.assertNotIn("Traceback", output)

    async def test_network_failures_have_types_without_traceback(self):
        for failure in (httpx.ReadTimeout(""), httpx.ConnectError("offline"),
                        RuntimeError("DeepSeek Stream Error: overloaded")):
            with self.subTest(failure=type(failure).__name__):
                _, output = await self.stream_failure(failure)
                self.assertIn(type(failure).__name__, output)
                self.assertNotIn("Traceback", output)

    def test_other_capabilities_keep_original_exception_type_and_traceback(self):
        for capability in ("TTS", "TTS stream", "STT", "Embed"):
            with self.subTest(capability=capability), self.assertLogs("failure-test", level="ERROR") as logs:
                try:
                    raise KeyError("broken-adapter")
                except KeyError as error:
                    log_provider_failure(logging.getLogger("failure-test"), capability, "openai", "test-model", error, 42)
                self.assertIn(f"{capability} failed", logs.output[0])
                self.assertIn("log_id=42", logs.output[0])
                self.assertIn("KeyError", logs.output[0])
                self.assertIn("Traceback", logs.output[0])

    def test_tool_named_error_is_not_a_failed_stream(self):
        self.assertFalse(is_error_chunk('data: {"choices": [{"delta": {"tool_calls": [{"function": {"name": "error"}}]}}]}\n\n'))
        self.assertTrue(is_error_chunk('data: {"error": {"message": "real error"}}\n\n'))
        self.assertFalse(is_error_chunk('data: [DONE]\n\n'))

    async def test_upstream_error_is_parsed_instead_of_dumping_sse(self):
        _, output = await self.stream_failure('data: {"error" : {"message": "quota exceeded"}}\n\n')
        self.assertIn("UpstreamError: quota exceeded", output)
        self.assertNotIn("data:", output)

    def test_http_error_has_cause_and_preserves_response_headers(self):
        app = FastAPI()
        app.add_exception_handler(StarletteHTTPException, log_http_exception)

        @app.get("/v1/audio/languages")
        def languages():
            raise HTTPException(503, "STT language catalog is unavailable", headers={"Retry-After": "4"}) from httpx.ConnectError("offline")

        with TestClient(app) as client, self.assertLogs("service-router.http", level="ERROR") as logs:
            response = client.get("/v1/audio/languages?private=omit-this")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "STT language catalog is unavailable"})
        self.assertEqual(response.headers["Retry-After"], "4")
        self.assertIn("GET /v1/audio/languages", logs.output[0])
        self.assertIn("cause=ConnectError: offline", logs.output[0])
        self.assertNotIn("omit-this", logs.output[0])

    async def test_failed_usage_has_readable_missing_metrics(self):
        with patch("core.router.telemetry.db_manager.log_request", AsyncMock()), self.assertLogs(
            "service-router.dynamic", level="INFO"
        ) as logs:
            await TelemetryService().log_usage(None, "openrouter", "test-model", None,
                                               success=False, duration_ms=12.5)
        self.assertIn("Request failed", logs.output[0])
        self.assertIn("TTFT=- duration=12.50ms", logs.output[0])
        self.assertNotIn("None", logs.output[0])


if __name__ == "__main__":
    unittest.main()
