"""
dev/test-orion-router/test_chat_logging.py
------------------------------------------
Chat logging düzenlemesi ve güvenlik testleri:
1. INFO seviyesinde tam kwargs, prompt ve tool şemalarının gizlenmesi
2. DEBUG seviyesinde teknik özetleme (büyük içerik dökülmemesi)
3. Hassas anahtarların ve bilinmeyen parametrelerin engellenmesi (allowlist kontrolü)
4. Model çağrıları, streaming ve telemetry akışının bozulmadığının doğrulanması
"""
import asyncio
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.logging_utils import (
    SAFE_CHAT_PARAM_KEYS,
    SAFE_TTS_PARAM_KEYS,
    format_chat_stream_info,
    format_chat_stream_debug,
    log_chat_stream_start,
    format_tts_kwargs_summary,
)
from core.router.runners.chat import ChatRunner
from core.router.telemetry import TelemetryService


class ChatLoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 100k tokenlık hissi veren devasa bir prompt ve karmaşık tool listesi
        self.huge_prompt = "Bu çok gizli ve devasa bir prompt metnidir. " * 5000  # ~225.000 karakter
        self.huge_tools = [
            {
                "type": "function",
                "function": {
                    "name": f"test_tool_{i}",
                    "description": f"Detailed tool schema description {i} with huge documentation " * 50,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "arg1": {"type": "string", "description": "some argument " * 20},
                            "arg2": {"type": "integer"},
                        },
                        "required": ["arg1"],
                    },
                },
            }
            for i in range(12)
        ]
        self.messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": self.huge_prompt},
            {"role": "assistant", "content": "Previous answer"},
            {"role": "user", "content": "Tell me more"},
        ]
        self.kwargs = {
            "tools": self.huge_tools,
            "tool_choice": "auto",
            "temperature": 0.7,
            "thinking": "low",
            "max_tokens": 4096,
            "api_key": "sk-secret-key-1234567890",
            "auth_header": "Bearer token-xyz",
            "unknown_custom_arg": "unauthorized_data_leak",
            "user_private_email": "alice@example.com",
        }

    def test_info_log_is_concise_and_never_leaks_prompts_or_schemas(self):
        """INFO logunda devasa prompt, mesaj içerikleri ve tool şemaları ASLA yer almamalıdır."""
        info_str = format_chat_stream_info(
            provider="openai",
            model="gpt-5-mini",
            messages=self.messages,
            kwargs=self.kwargs,
        )

        # Temel özet bilgilerin varlığı
        self.assertIn("provider=openai", info_str)
        self.assertIn("model=gpt-5-mini", info_str)
        self.assertIn("messages=4", info_str)
        self.assertIn("tools=12 (auto)", info_str)
        self.assertIn("temperature", info_str)
        self.assertIn("thinking", info_str)
        self.assertIn("max_tokens", info_str)

        # Büyük içeriklerin ve şemaların KESİNLİKLE OLMADIĞI
        self.assertNotIn(self.huge_prompt, info_str)
        self.assertNotIn("Detailed tool schema description", info_str)
        self.assertNotIn("properties", info_str)
        self.assertNotIn("You are a helpful assistant", info_str)

        # Hassas anahtarların ve bilinmeyen parametrelerin KESİNLİKLE OLMADIĞI
        self.assertNotIn("sk-secret-key", info_str)
        self.assertNotIn("Bearer token-xyz", info_str)
        self.assertNotIn("unknown_custom_arg", info_str)
        self.assertNotIn("unauthorized_data_leak", info_str)
        self.assertNotIn("alice@example.com", info_str)

        # Log çıktısının çok kısa (örneğin < 300 karakter) olduğunu doğrula
        self.assertLess(len(info_str), 300, f"INFO log unexpectedly long: {len(info_str)} chars")

    def test_debug_log_summarizes_technicals_without_dumping_payloads(self):
        """DEBUG logunda bile ham promptlar ve bütün şemalar dökülmemelidir."""
        debug_str = format_chat_stream_debug(
            messages=self.messages,
            kwargs=self.kwargs,
        )

        # Teknik özet metrikleri
        self.assertIn("roles=[system:1, user:2, assistant:1]", debug_str)
        self.assertIn("approx_chars=", debug_str)
        self.assertIn("tool_names=[test_tool_0", debug_str)
        self.assertIn("keys=", debug_str)

        # Ham prompt ve şema dökümü KESİNLİKLE OLMAMALI
        self.assertNotIn(self.huge_prompt, debug_str)
        self.assertNotIn("Detailed tool schema description", debug_str)
        self.assertNotIn("properties", debug_str)

        # Hassas veriler
        self.assertNotIn("sk-secret-key", debug_str)
        self.assertNotIn("Bearer token-xyz", debug_str)
        self.assertNotIn("alice@example.com", debug_str)

        # DEBUG logu da makul bir sınırda kalmalı (< 1000 karakter)
        self.assertLess(len(debug_str), 1000, f"DEBUG log unexpectedly long: {len(debug_str)} chars")

    def test_log_chat_stream_start_emits_expected_levels(self):
        """log_chat_stream_start INFO ve DEBUG seviyelerinde doğru kayıtları üretmeli."""
        test_logger = logging.getLogger("test.chat.logger")
        test_logger.setLevel(logging.DEBUG)

        with self.assertLogs(test_logger, level=logging.DEBUG) as captured:
            log_chat_stream_start(
                test_logger,
                provider="gemini",
                model="gemini-2.5-flash",
                messages=self.messages,
                kwargs=self.kwargs,
            )

        self.assertEqual(len(captured.records), 2)
        info_record = captured.records[0]
        debug_record = captured.records[1]

        self.assertEqual(info_record.levelname, "INFO")
        self.assertEqual(debug_record.levelname, "DEBUG")

        self.assertIn("provider=gemini", info_record.getMessage())
        self.assertNotIn("sk-secret-key", info_record.getMessage())
        self.assertNotIn(self.huge_prompt, info_record.getMessage())

        self.assertIn("roles=", debug_record.getMessage())
        self.assertNotIn(self.huge_prompt, debug_record.getMessage())

    def test_tts_kwargs_summary_allowlist(self):
        """TTS parametre özetinde yalnızca allowlist'teki alanlar yer almalı."""
        raw_tts_kwargs = {
            "speed": 1.2,
            "language": "tr",
            "pitch": 0.5,
            "secret_token": "shh",
            "api_key": "secret",
            "untrusted": "payload",
        }
        summary = format_tts_kwargs_summary(raw_tts_kwargs)
        self.assertEqual(summary, {"speed": 1.2, "language": "tr", "pitch": 0.5})
        self.assertNotIn("secret_token", summary)
        self.assertNotIn("api_key", summary)
        self.assertNotIn("untrusted", summary)

    async def test_chat_runner_stream_executes_unaffected_with_concise_logging(self):
        """ChatRunner.stream çalıştığında logların kısaldığı ve streaming'in/kwargs'ın değişmediği doğrulanmalı."""
        yielded_chunks = [
            'data: {"choices": [{"delta": {"content": "Hello world"}}]}\n\n',
            {"internal_usage": {"prompt_tokens": 15, "completion_tokens": 5}},
        ]
        received_kwargs = {}

        class MockPlugin:
            async def stream_chat(self, model, messages, api_key=None, auth_header=None, **kwargs):
                nonlocal received_kwargs
                received_kwargs = dict(kwargs)
                for chunk in yielded_chunks:
                    yield chunk

        runner = ChatRunner(
            registry=SimpleNamespace(chat_providers={"test_provider": MockPlugin()}),
            route_resolver=SimpleNamespace(),
            key_pool=SimpleNamespace(),
            telemetry=TelemetryService(),
        )

        test_kwargs = dict(self.kwargs)
        runner_logger = logging.getLogger("service-router.dynamic")

        with self.assertLogs(runner_logger, level=logging.INFO) as logs:
            chunks = []
            async for chunk in runner.stream(
                plugin=MockPlugin(),
                key_id="test_key",
                provider="test_provider",
                model="test-model",
                messages=self.messages,
                **test_kwargs,
            ):
                chunks.append(chunk)

        # 1. Logging kontrolü: "Starting chat stream" logunda prompt ve tool şeması olmamalı
        stream_start_logs = [l for l in logs.output if "Starting chat stream" in l]
        self.assertEqual(len(stream_start_logs), 1)
        self.assertIn("provider=test_provider", stream_start_logs[0])
        self.assertIn("model=test-model", stream_start_logs[0])
        self.assertIn("messages=4", stream_start_logs[0])
        self.assertIn("tools=12", stream_start_logs[0])
        self.assertNotIn(self.huge_prompt, stream_start_logs[0])
        self.assertNotIn("Detailed tool schema description", stream_start_logs[0])

        # 2. Model çağrısı kontrolü: plugin.stream_chat tam ve orijinal kwargs'ı eksiksiz almış olmalı!
        self.assertEqual(len(received_kwargs["tools"]), 12)
        self.assertEqual(received_kwargs["temperature"], 0.7)
        self.assertEqual(received_kwargs["thinking"], "low")
        self.assertEqual(received_kwargs["unknown_custom_arg"], "unauthorized_data_leak")

        # 3. Streaming kontrolü: yield edilen chunk'lar eksiksiz dönmeli
        self.assertTrue(any("Hello world" in str(c) for c in chunks))
        self.assertTrue(any("[DONE]" in str(c) for c in chunks))


if __name__ == "__main__":
    unittest.main()
