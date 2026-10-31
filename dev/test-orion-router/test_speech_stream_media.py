"""A speech stream is labelled by what the caller asked for, not by a guess from its first sample."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import speech
from core.audio_container import stream_media
from core.dependencies import authenticate_request

WAVE = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(20)
MP3_FRAME = bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes(40)
# Raw PCM whose first samples are small negative numbers: FF FF, FE FF, F0 FF ...
PCM_LOOKING_LIKE_A_FRAME = [bytes([0xFF, 0xFF, 0x00, 0x00]), bytes([0xFF, 0xF1, 0x50, 0x80]), bytes([0xFF, 0xFE, 0x10, 0x20])]


class StreamMedia(unittest.TestCase):
    def test_pcm_that_looks_like_an_mp3_frame_stays_pcm_when_pcm_was_requested(self):
        # This used to label a Gemini sentence audio/mpeg now and then, and the Hub dropped that part.
        for chunk in PCM_LOOKING_LIKE_A_FRAME:
            for requested in ("pcm", "PCM", "s16le"):
                with self.subTest(chunk=chunk.hex(), requested=requested):
                    media, headers = stream_media(chunk + bytes(100), requested)
                    self.assertEqual(media, "audio/pcm")
                    self.assertEqual(headers["X-Audio-Sample-Rate"], "24000")

    def test_ordinary_pcm_is_pcm(self):
        self.assertEqual(stream_media(bytes(range(64)), None)[0], "audio/pcm")
        self.assertEqual(stream_media(None, "pcm")[0], "audio/pcm")
        self.assertEqual(stream_media(b"", None)[0], "audio/pcm")

    def test_wave_is_wave_whatever_was_requested(self):
        for requested in (None, "pcm", "wav"):
            media, headers = stream_media(WAVE, requested)
            self.assertEqual(media, "audio/wav")
            self.assertNotIn("X-Audio-Sample-Rate", headers)

    def test_mp3_is_still_found_when_the_caller_did_not_ask_for_pcm(self):
        for requested in (None, "mp3", "wav"):
            self.assertEqual(stream_media(MP3_FRAME, requested)[0], "audio/mpeg")
            self.assertEqual(stream_media(b"ID3\x04\x00" + bytes(40), requested)[0], "audio/mpeg")

    def test_frame_header_with_reserved_fields_is_not_mp3(self):
        for header in (bytes([0xFF, 0xE9, 0x90, 0x00]),   # reserved version
                       bytes([0xFF, 0xF9, 0x90, 0x00]),   # reserved layer
                       bytes([0xFF, 0xFB, 0xF0, 0x00]),   # invalid bitrate
                       bytes([0xFF, 0xFB, 0x9C, 0x00])):  # reserved sample rate
            with self.subTest(header=header.hex()):
                self.assertEqual(stream_media(header + bytes(40), None)[0], "audio/pcm")


class SpeechEndpoint(unittest.TestCase):
    def post(self, first, requested):
        async def run_speech_stream(**kwargs):
            yield first + bytes(200)
            yield bytes(200)

        app = FastAPI()
        app.include_router(speech.router)
        app.dependency_overrides[authenticate_request] = lambda: {}
        app.state.dynamic_router = SimpleNamespace(run_speech_stream=run_speech_stream)
        body = {"model": "m", "input": "merhaba", "stream": True}
        if requested:
            body["response_format"] = requested
        return TestClient(app).post("/v1/audio/speech", json=body)

    def test_gemini_style_request_gets_pcm_even_when_the_first_sample_looks_like_mp3(self):
        for first in PCM_LOOKING_LIKE_A_FRAME:
            with self.subTest(first=first.hex()):
                response = self.post(first, "pcm")
                self.assertEqual(response.headers["content-type"], "audio/pcm")
                self.assertEqual(response.headers["x-audio-sample-rate"], "24000")
                self.assertEqual(len(response.content), 404)

    def test_mp3_stream_requested_as_mp3_is_still_labelled_mp3(self):
        response = self.post(MP3_FRAME, "mp3")
        self.assertEqual(response.headers["content-type"], "audio/mpeg")


if __name__ == "__main__":
    unittest.main()
