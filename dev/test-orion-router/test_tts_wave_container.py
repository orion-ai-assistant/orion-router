import struct
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from api.speech import audio_speech
from core.audio_container import finalize_buffered_wav
from providers.gemini.tts import _pcm_to_wav
from providers.openai.tts import OpenAITTSProvider


class ContainerTests(unittest.TestCase):
    def test_unknown_stream_sizes_become_finite_without_changing_pcm(self):
        pcm = b'\x00\x00\x01\x00' * 16
        original = _pcm_to_wav(pcm)
        streamed = bytearray(original)
        struct.pack_into('<I', streamed, 4, 0xFFFFFFFF)
        struct.pack_into('<I', streamed, 40, 0xFFFFFFFF)
        self.assertEqual(finalize_buffered_wav(bytes(streamed)), original)

    def test_extra_odd_chunk_does_not_assume_fixed_44_byte_header(self):
        original = _pcm_to_wav(b'\x00\x00' * 16)
        extended = bytearray(original[:36] + b'JUNK' + struct.pack('<I', 3) + b'abc\x00' + original[36:])
        struct.pack_into('<I', extended, 4, 0xFFFFFFFF)
        struct.pack_into('<I', extended, 52, 0xFFFFFFFF)
        repaired = finalize_buffered_wav(bytes(extended))
        self.assertEqual(struct.unpack_from('<I', repaired, 4)[0], len(repaired) - 8)
        self.assertEqual(struct.unpack_from('<I', repaired, 52)[0], 32)
        self.assertEqual(repaired[56:], original[44:])

    def test_valid_gemini_wav_and_mp3_are_unchanged(self):
        for audio in (_pcm_to_wav(b'\x00\x00' * 16), b'ID3some mp3 bytes'):
            self.assertIs(finalize_buffered_wav(audio), audio)

    def test_truncated_finite_wave_and_empty_data_are_not_guessed(self):
        truncated = _pcm_to_wav(b'\x00\x00' * 16)[:-4]
        empty = _pcm_to_wav(b'')
        self.assertIs(finalize_buffered_wav(truncated), truncated)
        self.assertIs(finalize_buffered_wav(empty), empty)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_provider_finalizes_wav_and_sets_actual_container_mime(self):
        original = _pcm_to_wav(b'\x00\x00' * 16)
        streamed = bytearray(original)
        struct.pack_into('<I', streamed, 4, 0xFFFFFFFF)
        struct.pack_into('<I', streamed, 40, 0xFFFFFFFF)
        client = AsyncMock()
        client.post.return_value = httpx.Response(200, content=bytes(streamed), headers={'Content-Type': 'application/octet-stream'})
        with patch('providers.openai.tts.get_http_client', return_value=client):
            result, mime, _ = await OpenAITTSProvider().generate_speech('tts-1', 'hello', api_key='test-key', response_format='wav')
        self.assertEqual(result, original)
        self.assertEqual(mime, 'audio/wav')


class SpeechEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_finalizes_streamed_wav_for_every_provider_and_mime(self):
        original = _pcm_to_wav(b'\x00\x00' * 16)
        streamed = bytearray(original)
        struct.pack_into('<I', streamed, 4, 0xFFFFFFFF)
        struct.pack_into('<I', streamed, 40, 0xFFFFFFFF)
        for provider in ('local', 'gemini', 'openai'):
            for mime in ('audio/wav', 'audio/x-wav', 'application/octet-stream'):
                with self.subTest(provider=provider, mime=mime):
                    response = await self._speech_response(provider, bytes(streamed), mime)
                    self.assertEqual(response.body, original)
                    self.assertEqual(response.headers['content-length'], str(len(original)))
                    self.assertEqual(response.headers['content-type'], mime)
                    self.assertEqual(response.headers['x-orion-metrics'], '{"latency": 1}')

    async def test_endpoint_preserves_valid_wav_and_non_wav_audio(self):
        for audio, mime in ((_pcm_to_wav(b'\x00\x00' * 16), 'audio/wav'),
                            (b'ID3some mp3 bytes', 'audio/mpeg')):
            with self.subTest(mime=mime):
                response = await self._speech_response('local', audio, mime)
                self.assertEqual(response.body, audio)

    async def test_endpoint_streaming_speech(self):
        async def dummy_stream(*args, **kwargs):
            yield b"chunk1"
            yield b"chunk2"

        request = SimpleNamespace(
            headers={'x-orion-provider': 'gemini'},
            json=AsyncMock(return_value={'input': 'hello', 'stream': True}),
            is_disconnected=AsyncMock(return_value=False),
            app=SimpleNamespace(state=SimpleNamespace(dynamic_router=SimpleNamespace(
                run_speech_stream=dummy_stream,
            ))),
        )
        response = await audio_speech(request, auth={})
        self.assertEqual(response.media_type, 'audio/pcm')
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        self.assertEqual(b"".join(chunks), b"chunk1chunk2")

    async def _speech_response(self, provider, audio, mime):
        request = SimpleNamespace(
            headers={'x-orion-provider': provider},
            json=AsyncMock(return_value={'input': 'hello'}),
            is_disconnected=AsyncMock(return_value=False),
            app=SimpleNamespace(state=SimpleNamespace(dynamic_router=SimpleNamespace(
                run_speech=AsyncMock(return_value=(audio, mime, {'latency': 1})),
            ))),
        )
        return await audio_speech(request, auth={})


class TTSRunnerKwargsCollisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_tts_runner_cleans_voice_and_explicit_kwargs(self):
        from core.router.runners.tts import TTSRunner
        from core.router.route_types import RoutePlan, ResolvedRoute

        mock_plugin = SimpleNamespace(
            generate_speech=AsyncMock(return_value=(b"wav_bytes", "audio/wav", {"prompt_tokens": 10, "completion_tokens": 20}))
        )
        registry = SimpleNamespace(tts_providers={"gemini": mock_plugin})
        route_resolver = SimpleNamespace(
            resolve=AsyncMock(return_value=RoutePlan(
                routes=(ResolvedRoute(provider="gemini", model="gemini-3.8-flash-lite-tts", default_config={"voice": "Achernar", "engine": "omnivoice"}),),
                requested_provider="gemini",
            ))
        )
        key_pool = SimpleNamespace(
            get_keys_for_provider=AsyncMock(return_value=[("test-key", "test-key-id")]),
            mark_key_error=AsyncMock(),
        )
        telemetry = SimpleNamespace(
            create_processing_log=AsyncMock(return_value="log-1"),
            log_usage=AsyncMock(),
            finish_processing_log=AsyncMock(),
        )

        runner = TTSRunner(registry, route_resolver, key_pool, telemetry)
        audio, mime, meta = await runner.run_speech(
            provider="gemini",
            model="gemini-3.8-flash-lite-tts",
            input_text="hello",
            voice="Achernar",
        )

        self.assertEqual(audio, b"wav_bytes")
        mock_plugin.generate_speech.assert_awaited_once()
        _, call_kwargs = mock_plugin.generate_speech.call_args
        self.assertEqual(call_kwargs["voice"], "Achernar")
        self.assertNotIn("voice", call_kwargs.get("kwargs", {}))
        self.assertEqual(call_kwargs.get("engine"), "omnivoice")

