"""
dev/test-orion-router/test_stt.py
---------------------------------
Orion Router Whisper STT Yetenek Test Paketi.
Router keşfi, LocalSTTProvider implementasyonu ve FastAPI /v1/audio/transcriptions endpoint'i test edilir.
"""
import io
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi.testclient import TestClient

from providers.base import BaseSTT
from providers.local.stt import LocalSTTProvider
from providers.gemini.stt import GeminiSTTProvider
from dynamic_router import DynamicLLMRouter
from main import app


class TestWhisperSTTIntegration(unittest.TestCase):

    def test_01_base_stt_and_provider_inheritance(self):
        """BaseSTT sınıf hiyerarşisi, LocalSTTProvider ve GeminiSTTProvider uyumluluğu."""
        local_p = LocalSTTProvider()
        self.assertIsInstance(local_p, BaseSTT)
        local_codes = [l["code"] for l in local_p.get_languages() if isinstance(l, dict)]
        self.assertIn("tr", local_codes)
        self.assertIn("en", local_codes)

        gemini_p = GeminiSTTProvider()
        self.assertIsInstance(gemini_p, BaseSTT)
        self.assertEqual(gemini_p.provider_name, "gemini")
        gemini_codes = [l["code"] for l in gemini_p.get_languages() if isinstance(l, dict)]
        self.assertTrue(any(c.startswith("tr") for c in gemini_codes))
        self.assertTrue(any(c.startswith("en") for c in gemini_codes))
        print("  [PASS] BaseSTT, LocalSTTProvider, and GeminiSTTProvider inheritance verified.")

    def test_02_dynamic_router_discovery(self):
        """DynamicLLMRouter'ın LocalSTTProvider ve GeminiSTTProvider'ı otomatik keşfedip kaydetmesi."""
        router = DynamicLLMRouter()
        self.assertIn("local", router.stt_providers)
        self.assertIsInstance(router.stt_providers["local"], LocalSTTProvider)
        self.assertIn("gemini", router.stt_providers)
        self.assertIsInstance(router.stt_providers["gemini"], GeminiSTTProvider)

        caps = router.get_capabilities()
        self.assertIn("local", caps)
        self.assertTrue(caps["local"]["stt"])
        self.assertIn("gemini", caps)
        self.assertTrue(caps["gemini"]["stt"])
        print("  [PASS] DynamicLLMRouter automatically discovered and registered Local and Gemini STT capabilities.")

    @patch("providers.local.stt.httpx.AsyncClient")
    def test_03_local_stt_provider_call(self, mock_client_cls):
        """LocalSTTProvider'ın HTTP POST isteğini doğru parametrelerle göndermesi."""
        import asyncio

        from unittest.mock import MagicMock
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "text": "Merhaba bu bir testtir.",
            "language": "tr",
            "duration": 0.45
        })

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client_cls.return_value = mock_client

        provider = LocalSTTProvider()
        result = asyncio.run(
            provider.generate_transcription(
                model="whisper-small-finetuned-tr",
                file_bytes=b"RIFF\x00\x00\x00\x00WAVEfmt ",
                filename="test.wav",
                language="tr"
            )
        )

        self.assertEqual(result["text"], "Merhaba bu bir testtir.")
        self.assertEqual(result["language"], "tr")
        self.assertEqual(result["duration"], 0.45)
        print("  [PASS] LocalSTTProvider generates valid transcription payload.")

    def test_04_api_transcriptions_endpoint(self):
        """FastAPI POST /v1/audio/transcriptions endpoint testi."""
        from core.dependencies import authenticate_request

        app.dependency_overrides[authenticate_request] = lambda: {"source": "system", "key_id": None}
        mock_router = AsyncMock()
        mock_router.run_transcription.return_value = {
            "text": "Ses dosyası başarıyla çözümlendi.",
            "language": "tr",
            "duration": 0.85
        }
        app.state.dynamic_router = mock_router

        try:
            client = TestClient(app)
            dummy_audio = io.BytesIO(b"FAKE_AUDIO_DATA_FOR_UNIT_TESTING")

            response = client.post(
                "/v1/audio/transcriptions",
                files={"file": ("speech.wav", dummy_audio, "audio/wav")},
                data={"model": "whisper-small-finetuned-tr", "language": "tr"},
                headers={"Authorization": "Bearer test-secret"}
            )

            self.assertEqual(response.status_code, 200)
            json_data = response.json()
            self.assertEqual(json_data["text"], "Ses dosyası başarıyla çözümlendi.")
            self.assertEqual(json_data["language"], "tr")
            print("  [PASS] POST /v1/audio/transcriptions endpoint verified.")
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    print("=" * 50)
    print("   Orion Router Whisper STT Test Suite")
    print("=" * 50)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWhisperSTTIntegration)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if result.wasSuccessful():
        print("=" * 50)
        print("   ALL STT TESTS PASSED SUCCESSFULLY (100% OK)")
        print("=" * 50)
        sys.exit(0)
    else:
        sys.exit(1)
