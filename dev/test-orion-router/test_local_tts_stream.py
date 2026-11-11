"""The local provider streams speech as the local TTS service makes it: PCM pieces go on as they arrive, a
whole WAV from an engine that does not stream goes on as it is. A real HTTP server stands in for the service."""
import asyncio
import json
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import http_client
from providers.local import tts as local_tts

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(20) + b"data\x00\x00\x00\x00"
PIECE_GAP = 0.4


class FakeTTS(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests = []
    streams = True

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeTTS.requests.append(body)
        if body.get("stream") and FakeTTS.streams:
            self.send_response(200)
            self.send_header("Content-Type", "audio/pcm")
            self.send_header("X-Sample-Rate", "24000")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(3):  # Three pieces, PIECE_GAP apart, as an engine speaking a long sentence.
                piece = bytes([i + 1]) * 4800
                self.wfile.write(b"%x\r\n%s\r\n" % (len(piece), piece))
                self.wfile.flush()
                time.sleep(PIECE_GAP)
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(WAV) + 9600))
            self.end_headers()
            self.wfile.write(WAV + bytes(9600))

    def log_message(self, *args):
        pass


class LocalStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTTS)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeTTS.requests, FakeTTS.streams = [], True
        http_client._shared_async_client = None  # A fresh client on this test's event loop.

    def speak(self, **kwargs):
        formats = []

        async def run():
            arrivals, chunks = [], []
            t0 = time.perf_counter()
            async for chunk in local_tts.LocalTTSProvider().generate_speech_stream(
                    "local", "Uzun bir cümle.", None, _archive_metadata=formats.append, **kwargs):
                arrivals.append(time.perf_counter() - t0)
                chunks.append(chunk)
            await http_client.get_http_client().aclose()
            return arrivals, b"".join(chunks)

        with patch.object(local_tts, "TTS_HOST", "127.0.0.1"), patch.object(local_tts, "TTS_PORT", self.server.server_port):
            arrivals, audio = asyncio.run(run())
        return arrivals, audio, formats

    def test_pcm_pieces_go_on_as_they_arrive(self):
        arrivals, audio, formats = self.speak(response_format="pcm", steps=15)
        sent = FakeTTS.requests[0]
        self.assertTrue(sent["stream"])
        self.assertEqual((sent["response_format"], sent["steps"]), ("pcm", 15))
        self.assertEqual(audio, b"\x01" * 4800 + b"\x02" * 4800 + b"\x03" * 4800)
        self.assertLess(arrivals[0], PIECE_GAP)  # The first piece before the service has finished.
        self.assertGreater(arrivals[-1] - arrivals[0], PIECE_GAP)
        self.assertEqual(formats, [{"format": "s16le", "sample_rate": 24000, "channels": 1, "sample_width": 2}])

    def test_an_engine_that_does_not_stream_sends_one_wav_which_goes_on_as_it_is(self):
        FakeTTS.streams = False
        _, audio, formats = self.speak(response_format="pcm")
        self.assertEqual(audio, WAV + bytes(9600))
        self.assertEqual(formats, [{"content_type": "audio/wav"}])

    def test_a_caller_that_wants_another_format_gets_the_whole_file_as_before(self):
        _, audio, _ = self.speak(response_format="wav")
        self.assertFalse(FakeTTS.requests[0]["stream"])
        self.assertEqual(audio, WAV + bytes(9600))


class RefusedVoice(unittest.TestCase):
    """A voice the running engine refuses is dropped and the request made again with the engine's own voice."""

    def test_an_unknown_or_foreign_voice_is_retried_without_it(self):
        retry = local_tts.LocalTTSProvider._foreign_voice
        unknown = "Böyle bir ses klonu bulunamadı: 'zephyr'. Aktif motor (voxcpm2-gguf) için mevcut sesler: nika"
        self.assertTrue(retry({"voice": "zephyr"}, 400, unknown))
        self.assertTrue(retry({"voice": "x"}, 400, "Bu ses bu motorla uyumlu değil"))
        self.assertFalse(retry({"voice": ""}, 400, unknown))  # Already the engine's own voice.
        self.assertFalse(retry({"voice": "zephyr"}, 500, unknown))
        self.assertFalse(retry({"voice": "nika"}, 400, "Metin çok uzun"))


if __name__ == "__main__":
    unittest.main()
