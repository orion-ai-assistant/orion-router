import struct
import unittest
from unittest.mock import AsyncMock, patch

import httpx
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
