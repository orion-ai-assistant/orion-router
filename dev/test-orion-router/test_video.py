"""Run with python -m unittest discover -s dev/test-orion-router -p test_video.py."""
import asyncio
import base64
import copy
import json
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import video
from providers.local.chat import LocalChatProvider
from providers.openai.chat import OpenAIChatProvider


def attachment(data=b"video"):
    return {"type": "input_video", "input_video": {
        "data": base64.b64encode(data).decode(), "format": "mp4",
    }}


class FakeResponse:
    status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def aiter_lines(self):
        yield "data: [DONE]"


class FakeClient:
    def __init__(self):
        self.requests = []

    def stream(self, method, url, **kwargs):
        self.requests.append((url, kwargs["json"]))
        return FakeResponse()


class VideoTests(unittest.IsolatedAsyncioTestCase):
    def test_sampling_covers_long_video_and_short_clip(self):
        self.assertEqual(video._sample_times(0.2), [0])
        self.assertEqual(video._sample_times(10), list(range(10)))
        times = video._sample_times(320)
        self.assertEqual(len(times), 32)
        self.assertEqual(times[-1], 310)
        for duration in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                video._sample_times(duration)

    def test_input_validation(self):
        self.assertEqual(video._video_bytes(attachment()), b"video")
        self.assertEqual(video._video_bytes({"type": "video_url", "video_url": {
            "url": "data:video/mp4;base64,dmlkZW8="}}), b"video")
        for url in ("https://example.org/video.mp4", "file:///secret", "data:text/plain;base64,YQ=="):
            with self.assertRaises(ValueError):
                video._video_bytes({"type": "video_url", "video_url": {"url": url}})
        with self.assertRaises(ValueError):
            video._video_bytes({"type": "input_video", "input_video": {"data": "!!!!"}})
        with patch.object(video, "MAX_VIDEO_BYTES", 2), self.assertRaises(ValueError):
            video._video_bytes(attachment())

    async def test_order_and_history_preserved_for_multiple_videos(self):
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "file.txt"}, attachment(),
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,YQ=="}},
            attachment(), {"type": "text", "text": "question"},
        ]}, {"role": "assistant", "content": "previous answer"}]
        original = copy.deepcopy(messages)
        with patch.object(video, "_frames", AsyncMock(side_effect=[
            [{"type": "text", "text": "first video"}], [{"type": "text", "text": "second video"}],
        ])):
            result = await video.prepare_openai_videos(messages)
        self.assertEqual(messages, original)
        self.assertEqual([p.get("text", "image") for p in result[0]["content"]],
                         ["file.txt", "first video", "image", "second video", "question"])
        self.assertEqual(result[1], original[1])

    async def test_openai_chat_and_responses_receive_images(self):
        frames = [{"type": "text", "text": "frame at 0s"},
                  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YQ=="}}]
        messages = [{"role": "user", "content": [attachment()]}]
        for kwargs, endpoint, image_type in (
            ({}, "/chat/completions", "image_url"),
            ({"thinking_level": "low", "tools": [{"type": "function", "function": {
                "name": "test", "parameters": {"type": "object"}}}]}, "/responses", "input_image"),
        ):
            client = FakeClient()
            with patch.object(video, "_frames", AsyncMock(return_value=frames)), patch(
                "providers.openai.chat.get_http_client", return_value=client
            ):
                _ = [item async for item in OpenAIChatProvider().stream_chat(
                    "vision-model", messages, api_key="test", **kwargs)]
            url, payload = client.requests[0]
            self.assertTrue(url.endswith(endpoint))
            content = (payload.get("messages") or payload["input"])[0]["content"]
            self.assertEqual(content[1]["type"], image_type)
            self.assertNotIn("input_video", json.dumps(payload))

    async def test_local_passes_all_attachments_without_decoding(self):
        audio = {"type": "input_audio", "input_audio": {"data": "YQ==", "format": "wav"}}
        image = {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YQ=="}}
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "before"}, attachment(), image, audio,
            {"type": "text", "text": "after"}]}]
        original = copy.deepcopy(messages)
        client = FakeClient()
        with patch.object(video, "_frames", AsyncMock(side_effect=AssertionError("Local video must stay native"))) as frames, patch(
            "providers.local.chat.get_http_client", return_value=client
        ):
            _ = [item async for item in LocalChatProvider().stream_chat("gemma", messages)]
        content = client.requests[0][1]["messages"][0]["content"]
        self.assertEqual(content, original[0]["content"])
        self.assertEqual(messages, original)
        frames.assert_not_awaited()

    async def test_openai_rejects_audio_in_history_before_decoding_or_network(self):
        from core.router.runners.chat import is_key_specific_error
        messages = [{"role": "user", "content": [attachment(),
            {"type": "input_audio", "input_audio": {"data": "YQ==", "format": "wav"}}]},
            {"role": "assistant", "content": ""}, {"role": "user", "content": "try again"}]
        for model in ("gpt-6-luna", "gpt-4o-mini", "unknown-model"):
            with self.subTest(model=model), patch.object(video, "_frames", AsyncMock()) as frames, patch(
                "providers.openai.chat.get_http_client"
            ) as network:
                with self.assertRaisesRegex(ValueError, "does not support audio input") as error:
                    _ = [item async for item in OpenAIChatProvider().stream_chat(model, messages, api_key="test")]
                self.assertFalse(is_key_specific_error(str(error.exception)))
                frames.assert_not_awaited()
                network.assert_not_called()

    async def test_openai_audio_models_keep_audio_in_chat_completions(self):
        messages = [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": "YQ==", "format": "wav"}}]}]
        for model in ("gpt-audio", "gpt-audio-1.5", "gpt-audio-mini", "gpt-audio-2025-08-28",
                      "gpt-4o-audio-preview", "gpt-4o-mini-audio-preview-2024-12-17"):
            client = FakeClient()
            with self.subTest(model=model), patch("providers.openai.chat.get_http_client", return_value=client):
                _ = [item async for item in OpenAIChatProvider().stream_chat(model, messages, api_key="test")]
            self.assertTrue(client.requests[0][0].endswith("/chat/completions"))
            self.assertEqual(client.requests[0][1]["messages"], messages)

    async def test_missing_ffmpeg_has_actionable_error(self):
        with patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError)):
            with self.assertRaisesRegex(ValueError, "FFMPEG_DIR"):
                await video._run("ffmpeg", "-version")

    async def test_cancellation_kills_child(self):
        class Process:
            returncode = None
            killed = False
            calls = 0

            async def communicate(self):
                self.calls += 1
                if self.calls == 1:
                    raise asyncio.CancelledError
                return b"", b""

            def kill(self):
                self.killed = True
        process = Process()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            with self.assertRaises(asyncio.CancelledError):
                await video._run("ffmpeg")
        self.assertTrue(process.killed)

    async def test_decode_failure_removes_temporary_files(self):
        seen = []

        async def fail(tool, *args):
            seen.append(Path(args[-1]).parent)
            raise ValueError("invalid video")
        with patch.object(video, "_run", side_effect=fail), self.assertRaises(ValueError):
            await video._frames(attachment())
        self.assertTrue(seen)
        self.assertFalse(seen[0].exists())

    async def test_real_ffmpeg_decodes_silent_frames_from_video_with_audio(self):
        binary = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        executable = str(Path(video.FFMPEG_DIR) / binary) if video.FFMPEG_DIR else binary
        if not shutil.which(executable):
            self.skipTest("FFmpeg is not installed")
        with tempfile.TemporaryDirectory() as folder:
            clip = Path(folder) / "clip.mp4"
            await video._run("ffmpeg", "-loglevel", "error", "-nostdin",
                             "-f", "lavfi", "-i", "testsrc2=size=960x540:rate=10",
                             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000",
                             "-t", "2.5", "-c:v", "mpeg4", "-c:a", "aac", "-y", str(clip))
            parts = await video._frames(attachment(clip.read_bytes()))
            images = [p for p in parts if p["type"] == "image_url"]
            self.assertEqual(len(images), 3)
            self.assertIn("audio was not processed", parts[0]["text"])
            for image in images:
                jpeg = base64.b64decode(image["image_url"]["url"].split(",", 1)[1])
                self.assertTrue(jpeg.startswith(b"\xff\xd8"))
            self.assertIn("2.00s", parts[-3]["text"])


if __name__ == "__main__":
    unittest.main()
