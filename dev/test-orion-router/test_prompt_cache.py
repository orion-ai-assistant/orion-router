"""Offline checks for prompt caching: usage shapes, billing, conversation keys and provider hooks."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.model_catalog import load_model_catalog, unit_pricing
from core.prompt_cache import (
    CacheRequest, CacheUsage, derive_cache_key, extract_cache_usage, normalize_usage, prompt_cost,
)
from core.router.runners.chat import ChatRunner
from core.router.telemetry import TelemetryService
from providers.base import BaseChat
from providers.deepseek.chat import DeepSeekChatProvider
from providers.gemini.chat import GeminiChatProvider
from providers.openai.chat import OpenAIChatProvider
from providers.openrouter.chat import OpenRouterChatProvider


class UsageShapeTests(unittest.TestCase):
    def test_every_known_shape(self):
        cases = {
            'openai chat': {'prompt_tokens': 100, 'prompt_tokens_details': {'cached_tokens': 60}},
            'responses api': {'prompt_tokens': 100, 'input_tokens_details': {'cached_tokens': 60}},
            'deepseek': {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 60, 'prompt_cache_miss_tokens': 40},
            'gemini sdk keys': {'prompt_tokens': 100, 'cached_content_token_count': 60},
            'flat': {'prompt_tokens': 100, 'cached_tokens': 60},
        }
        for name, usage in cases.items():
            with self.subTest(name):
                self.assertEqual(extract_cache_usage(usage), CacheUsage(60, 0))

    def test_writes_and_clamping(self):
        usage = {'prompt_tokens': 100, 'prompt_tokens_details': {'cached_tokens': 70, 'cache_write_tokens': 50}}
        self.assertEqual(extract_cache_usage(usage), CacheUsage(70, 30))  # never more than the prompt
        self.assertEqual(extract_cache_usage({'prompt_tokens': 10, 'cached_tokens': 99}), CacheUsage(10, 0))

    def test_garbage_means_no_cache(self):
        for usage in (None, {}, {'prompt_tokens': 5}, {'prompt_tokens': 5, 'cached_tokens': 'x'},
                      {'prompt_tokens': 5, 'cached_tokens': -3}, {'prompt_tokens': 5, 'cached_tokens': float('nan')},
                      {'prompt_tokens': 5, 'cached_tokens': True}, {'prompt_tokens': 5, 'prompt_tokens_details': None}):
            with self.subTest(usage=usage):
                self.assertEqual(extract_cache_usage(usage), CacheUsage())

    def test_normalize_writes_openai_form(self):
        usage = normalize_usage({'prompt_tokens': 100, 'prompt_cache_hit_tokens': 60})
        self.assertEqual(usage['prompt_tokens_details'], {'cached_tokens': 60})
        self.assertEqual(normalize_usage({'prompt_tokens': 3}), {'prompt_tokens': 3})  # untouched without a hit
        self.assertIsNone(normalize_usage(None))


class PromptCostTests(unittest.TestCase):
    PRICES = {'input': 1.0, 'cache_read': 0.1, 'cache_write': 1.25}

    def test_no_cache_is_the_plain_input_price(self):
        cost = prompt_cost(2_000_000, CacheUsage(), self.PRICES)
        self.assertEqual((cost.cost, cost.known, cost.saved), (2.0, True, 0.0))

    def test_hits_use_the_cache_read_price(self):
        cost = prompt_cost(1_000_000, CacheUsage(900_000), self.PRICES)
        self.assertAlmostEqual(cost.cost, 0.1 + 0.09)
        self.assertAlmostEqual(cost.saved, 1.0 - 0.19)

    def test_writes_use_the_cache_write_price(self):
        cost = prompt_cost(1_000_000, CacheUsage(0, 400_000), self.PRICES)
        self.assertAlmostEqual(cost.cost, 0.6 + 0.5)
        self.assertAlmostEqual(cost.saved, -0.1)  # a write that nothing hit yet costs more than it saves

    def test_unset_cache_prices_fall_back_to_input(self):
        cost = prompt_cost(1_000_000, CacheUsage(900_000, 50_000), {'input': 2.0})
        self.assertAlmostEqual(cost.cost, 2.0)
        self.assertAlmostEqual(cost.saved, 0.0)

    def test_free_cache_reads_are_not_unknown(self):
        cost = prompt_cost(1_000_000, CacheUsage(1_000_000), {'input': 1.0, 'cache_read': 0})
        self.assertEqual((cost.cost, cost.known, cost.saved), (0.0, True, 1.0))

    def test_unknown_input_price(self):
        self.assertFalse(prompt_cost(10, CacheUsage(), {'input': None}).known)
        self.assertFalse(prompt_cost(10, CacheUsage(4), {'cache_read': 0.1}).known)  # fresh tokens have no price
        self.assertTrue(prompt_cost(10, CacheUsage(10), {'cache_read': 0.1}).known)  # only cache hits: priced
        self.assertTrue(prompt_cost(0, CacheUsage(), {}).known)


class ConversationKeyTests(unittest.TestCase):
    def test_none_when_the_client_names_no_conversation(self):
        self.assertIsNone(derive_cache_key({}, {}, 'key-1'))
        self.assertIsNone(derive_cache_key({'session_id': '  '}, {}, 'key-1'))

    def test_body_fields_and_headers_are_equivalent(self):
        key = derive_cache_key({'prompt_cache_key': 'chat-1'}, {}, 'key-1')
        self.assertEqual(key, derive_cache_key({'session_id': 'chat-1'}, {}, 'key-1'))
        self.assertEqual(key, derive_cache_key({}, {'x-orion-session': 'chat-1'}, 'key-1'))
        self.assertEqual(len(key), 32)
        self.assertNotIn('chat-1', key)

    def test_callers_never_share_a_cache(self):
        self.assertNotEqual(derive_cache_key({'session_id': 'c'}, {}, 'key-1'),
                            derive_cache_key({'session_id': 'c'}, {}, 'key-2'))
        self.assertNotEqual(derive_cache_key({'session_id': 'a'}, {}, 'key-1'),
                            derive_cache_key({'session_id': 'b'}, {}, 'key-1'))


class ProviderHookTests(unittest.TestCase):
    CACHE = CacheRequest('abc')

    def test_default_hook_adds_nothing(self):
        for provider in (GeminiChatProvider(), DeepSeekChatProvider()):
            payload = {}
            provider.apply_cache(payload, 'm', self.CACHE)
            self.assertEqual(payload, {}, type(provider).__name__)

    def test_openai_sends_prompt_cache_key(self):
        payload = {}
        OpenAIChatProvider().apply_cache(payload, 'gpt-4o-mini', self.CACHE)
        self.assertEqual(payload, {'prompt_cache_key': 'abc'})
        payload = {}
        OpenAIChatProvider().apply_cache(payload, 'gpt-4o-mini', CacheRequest())
        self.assertEqual(payload, {})

    def test_openrouter_sends_session_and_claude_breakpoint(self):
        payload = {}
        OpenRouterChatProvider().apply_cache(payload, 'openai/gpt-4o', self.CACHE)
        self.assertEqual(payload, {'session_id': 'abc'})
        payload = {}
        OpenRouterChatProvider().apply_cache(payload, 'anthropic/claude-sonnet-4.6', self.CACHE)
        self.assertEqual(payload, {'session_id': 'abc', 'cache_control': {'type': 'ephemeral'}})

    def test_kwargs_carry_the_key(self):
        self.assertEqual(BaseChat.extract_cache_request({'cache_key': 'abc'}), self.CACHE)
        self.assertEqual(BaseChat.extract_cache_request({}), CacheRequest())

    def test_openai_responses_payload_carries_key_and_usage_reports_hits(self):
        provider = OpenAIChatProvider()
        payload = provider._responses_payload('o3-mini', [{'role': 'user', 'content': 'hi'}], {'cache_key': 'abc'})
        self.assertEqual(payload['prompt_cache_key'], 'abc')


class BillingFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_prices_to_logged_cost_and_savings(self):
        models = {m['name']: m for m in load_model_catalog()['models']}
        state = SimpleNamespace(pricing_cache={'gpt-4o-mini': unit_pricing(models['gpt-4o-mini'])})
        usage = {'prompt_tokens': 1_000_000, 'completion_tokens': 0, 'thoughts_tokens': 0,
                 'prompt_tokens_details': {'cached_tokens': 800_000}}
        with patch('core.router.telemetry.db_manager.log_request', new_callable=AsyncMock) as log:
            await TelemetryService(state).log_usage(None, 'openai', 'gpt-4o-mini', usage, capability='chat')
        kwargs = log.call_args.kwargs
        self.assertAlmostEqual(kwargs['cost'], 0.03 + 0.06)  # 200k fresh at 0.15, 800k cached at 0.075
        self.assertAlmostEqual(kwargs['prompt_cost'], 0.09)
        self.assertEqual(kwargs['cached_tokens'], 800_000)
        self.assertEqual(kwargs['cache_write_tokens'], 0)
        self.assertAlmostEqual(kwargs['cache_saved_cost'], 0.15 - 0.09)

    async def test_non_chat_and_failed_requests_record_no_cache_numbers(self):
        state = SimpleNamespace(pricing_cache={'tts-1': {'input': 15, 'output': 0, 'think': 0}})
        with patch('core.router.telemetry.db_manager.log_request', new_callable=AsyncMock) as log:
            await TelemetryService(state).log_usage(None, 'openai', 'tts-1', {'prompt_tokens': 10}, capability='tts')
            self.assertIsNone(log.call_args.kwargs['cached_tokens'])
            await TelemetryService(state).log_usage(None, 'openai', 'x', None, capability='chat', success=False)
            self.assertIsNone(log.call_args.kwargs['cached_tokens'])

    async def test_runner_normalizes_provider_usage_for_billing_and_clients(self):
        class Plugin:
            async def stream_chat(self, **kwargs):
                yield 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                yield {'internal_usage': {'prompt_tokens': 100, 'completion_tokens': 5,
                                          'prompt_cache_hit_tokens': 60, 'prompt_cache_miss_tokens': 40}}

        telemetry = SimpleNamespace(log_usage=AsyncMock(), update_processing_request=AsyncMock())
        runner = ChatRunner(SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), telemetry)
        chunks = [c async for c in runner.stream(Plugin(), None, 'deepseek', 'm', [{'role': 'user', 'content': 'x'}], 'k', None)]
        await asyncio.sleep(0)  # let the scheduled telemetry task run
        final = json.loads(next(c for c in chunks if '"usage"' in c)[len('data:'):])
        self.assertEqual(final['usage']['prompt_tokens_details'], {'cached_tokens': 60})
        self.assertEqual(telemetry.log_usage.call_args.args[3]['prompt_tokens_details'], {'cached_tokens': 60})


if __name__ == '__main__':
    unittest.main()
