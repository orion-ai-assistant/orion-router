import unittest
from unittest.mock import patch
from providers.gemini.tts import GeminiTTSProvider, MODEL_VOICE_GROUPS

class VoiceTests(unittest.TestCase):
    def test_each_declared_model_uses_its_group(self):
        provider = GeminiTTSProvider()
        for group in MODEL_VOICE_GROUPS:
            for model in group['models']:
                with self.subTest(model=model):
                    self.assertEqual(provider.get_voices(model), group['voices'])
                    self.assertEqual(provider.resolve_voice(model, None), group['voices'][0])
                    self.assertEqual(provider.resolve_voice(model, group['voices'][-1].lower()), group['voices'][-1])

    def test_exact_model_takes_priority_over_another_group_pattern(self):
        groups = [
            {'models': [], 'match_patterns': ['shared'], 'voices': ['A']},
            {'models': ['shared-model'], 'voices': ['B']},
        ]
        with patch('providers.gemini.tts.MODEL_VOICE_GROUPS', groups):
            provider = GeminiTTSProvider()
            self.assertEqual(provider.get_voices('SHARED-MODEL'), ['B'])
            self.assertEqual(provider.get_voices('shared-other'), ['A'])
            with self.assertRaises(ValueError):
                provider.resolve_voice('shared-model', 'A')


class LanguageCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_catalog_lists_languages_only_for_providers_that_take_one(self):
        from types import SimpleNamespace
        from api.admin import get_admin_voices
        from providers.local.tts import LocalTTSProvider
        local = LocalTTSProvider()
        router = SimpleNamespace(tts_providers={'gemini': GeminiTTSProvider(), 'local': local})
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dynamic_router=router)))
        with patch.object(local, 'get_voices', return_value=[]), \
                patch.object(local, 'get_languages', return_value=['Auto', 'Turkish']):
            data = await get_admin_voices(request)
        self.assertEqual(data['languages'], {'gemini': [], 'local': ['Auto', 'Turkish']})
