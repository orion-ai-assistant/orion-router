"""Offline regression checks for catalog rates and billable usage."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.model_catalog import load_model_catalog, unit_pricing
from core.router.telemetry import TelemetryService
from core.router.route_types import RoutePlan
from core.router.runners.stt import STTRunner
from core.router.runners.embeddings import EmbeddingsRunner
from providers.openai.tts import OpenAITTSProvider
import httpx


class PricingTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_to_logged_cost(self):
        models = {m['name']: m for m in load_model_catalog()['models']}
        cases = [
            ('gpt-4o-mini', 'chat', 1_000_000, 1_000_000, 1_000_000, 1.35),
            ('gemini-3.1-flash-tts-preview', 'tts', 1_000_000, 1_000_000, 0, 21),
            ('tts-1', 'tts', 1_000_000, 0, 0, 15),
            ('local-embed', 'embed', 100, 0, 0, 0),
            ('local-stt', 'stt', 100, 20, 0, 0),
        ]
        for name, capability, p, c, t, expected in cases:
            with self.subTest(name=name):
                state = SimpleNamespace(pricing_cache={name: unit_pricing(models[name])})
                with patch('core.router.telemetry.db_manager.log_request', new_callable=AsyncMock) as log:
                    await TelemetryService(state).log_usage(
                        None, models[name]['provider'], name,
                        {'prompt_tokens': p, 'completion_tokens': c, 'thoughts_tokens': t},
                        capability=capability,
                    )
                    self.assertAlmostEqual(log.call_args.kwargs['cost'], expected)

    def test_unknown_free_and_partial_prices(self):
        self.assertIsNone(unit_pricing({}))
        self.assertEqual(unit_pricing({'pricing': {'input': 0}}),
                         {'input': 0, 'output': None, 'think': None})
        # unit_pricing returns per-million values as-is (no division)
        self.assertEqual(unit_pricing({'pricing': {'input': 0.15}})['input'], 0.15)
        with self.assertRaises(ValueError):
            unit_pricing({'pricing_unit': 'per_minute', 'pricing': {'input': 1}})

    async def test_openai_tts_returns_character_usage(self):
        client = SimpleNamespace(post=AsyncMock(return_value=httpx.Response(
            200, content=b'audio', headers={'content-type': 'audio/mpeg'})))
        with patch('providers.openai.tts.get_http_client', return_value=client):
            audio, _, usage = await OpenAITTSProvider().generate_speech(
                'tts-1', 'Merhaba!', api_key='test')
        self.assertEqual(audio, b'audio')
        self.assertEqual(usage, {'prompt_tokens': 8, 'completion_tokens': 0})

    async def test_runners_use_billable_counts(self):
        for capability in ('stt', 'embed'):
            with self.subTest(capability=capability):
                resolver = SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan.direct('test', 'test')))
                keys = SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[('key', None)]))
                telemetry = SimpleNamespace(create_processing_log=AsyncMock(return_value=1),
                                            log_usage=AsyncMock())
                if capability == 'stt':
                    plugin = SimpleNamespace(generate_transcription=AsyncMock(return_value={
                        'text': 'one word', 'duration': 999,
                        'usage': {'prompt_tokens': 1234, 'completion_tokens': 56}}))
                    runner = STTRunner(SimpleNamespace(stt_providers={'test': plugin}), resolver, keys, telemetry)
                    await runner.run_transcription('test', 'test', b'audio')
                    expected = {'prompt_tokens': 1234, 'completion_tokens': 56, 'thoughts_tokens': 0}
                else:
                    plugin = SimpleNamespace(generate_embeddings=AsyncMock(return_value={
                        'data': [{'embedding': [0.1] * 768}], 'usage': {'prompt_tokens': 1234}}))
                    runner = EmbeddingsRunner(SimpleNamespace(embed_providers={'test': plugin}), resolver, keys, telemetry)
                    await runner.run_embeddings('test', 'test', 'hello')
                    expected = {'prompt_tokens': 1234, 'completion_tokens': 0, 'thoughts_tokens': 0}
                await asyncio.sleep(0)  # Let the scheduled telemetry call run.
                self.assertEqual(telemetry.log_usage.call_args.args[3], expected)


if __name__ == '__main__':
    unittest.main()
