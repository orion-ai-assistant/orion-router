import asyncio
import io
import struct
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI

from api.tts_archives import audio_response, router
from core.security import hash_secret
from core.tts_archive import ArchiveSession, _active, check_runtime, _command, binary
from core.router.runners.tts import TTSRunner
from core.router.route_types import RoutePlan
from database import db_manager


def wav(rate=24000, seconds=1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
        stream.writeframes(bytes(int(rate * seconds) * 2))
    return output.getvalue()


class RangeTests(unittest.TestCase):
    def test_byte_ranges_and_head(self):
        for header, code, body in [(None, 200, b'0123456789'), ('bytes=2-4', 206, b'234'),
                ('bytes=7-', 206, b'789'), ('bytes=-3', 206, b'789'), ('bytes=0-999', 206, b'0123456789'),
                ('bytes=10-', 416, b''), ('bytes=4-2', 416, b''), ('bytes=-0', 416, b''),
                ('bytes=1-2,4-5', 200, b'0123456789'), ('invalid', 200, b'0123456789')]:
            with self.subTest(header=header):
                response = audio_response(b'0123456789', 'audio/ogg; codecs=opus', 'GET', header)
                self.assertEqual(response.status_code, code); self.assertEqual(response.body, body)
                self.assertEqual(int(response.headers['content-length']), len(body))
                if code == 416: self.assertEqual(response.headers['content-range'], 'bytes */10')
        response = audio_response(b'0123', 'audio/mpeg', 'HEAD', 'bytes=1-2')
        self.assertEqual(response.status_code, 200); self.assertEqual(response.body, b'')
        self.assertEqual(response.headers['content-length'], '4')
        self.assertEqual(audio_response(b'0123', 'audio/mpeg', 'GET', 'bytes=1-2', '"a"', '"b"').status_code, 200)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_get_head_and_orphan_discovery(self):
        app = FastAPI(); app.include_router(router)
        with patch.object(db_manager, 'get_config', AsyncMock(return_value=hash_secret('test-key'))), \
                patch.object(db_manager, 'fetchrow', AsyncMock(return_value={'audio': b'012345', 'mime_type': 'audio/ogg; codecs=opus'})) as row, \
                patch.object(db_manager, 'fetch', AsyncMock(return_value=[{'id': 1, 'log_id': None}])) as listing, \
                patch.object(db_manager, 'fetchval', AsyncMock(return_value=1)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                for method in ('GET', 'HEAD'):
                    self.assertEqual((await client.request(method, '/dashboard/api/audio-archives/1/audio')).status_code, 401)
                row.assert_not_awaited()
                headers = {'X-Admin-Key': 'test-key', 'Range': 'bytes=2-3'}
                response = await client.get('/dashboard/api/audio-archives/1/audio', headers=headers)
                self.assertEqual(response.status_code, 206); self.assertEqual(response.content, b'23')
                self.assertEqual(response.headers['content-type'], 'audio/ogg; codecs=opus')
                self.assertEqual((await client.head('/dashboard/api/audio-archives/1/audio', headers=headers)).content, b'')
                response = await client.get('/dashboard/api/audio-archives', headers=headers)
                self.assertIsNone(response.json()['archives'][0]['log_id'])
                self.assertNotIn('audio,', listing.call_args.args[0])
                row.return_value = None
                self.assertEqual((await client.get('/dashboard/api/audio-archives/999/audio', headers=headers)).status_code, 404)


class EncoderTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try: check_runtime()
        except Exception as exc: raise unittest.SkipTest(f'Native FFmpeg unavailable: {exc}')

    async def finish(self, session, status='completed'):
        with patch('core.tts_archive.save_archive', AsyncMock(return_value=71)) as save:
            result = await session.finish(log_id=1, provider='test', requested_model='alias', resolved_model='actual', text='hello', status=status)
            return result, save

    async def feed(self, session, data):
        for offset in range(0, len(data), 16000):
            while session.queued_bytes > 1000000 and not session.error: await asyncio.sleep(.01)
            session.feed(data[offset:offset + 16000]); await asyncio.sleep(0)

    async def test_empty_failed_attempt_is_not_an_archive_error(self):
        session = ArchiveSession()
        with patch('core.tts_archive.logger.error') as error:
            result, save = await self.finish(session, 'interrupted')
        self.assertEqual(result, {})
        self.assertIsNone(session.error)
        error.assert_not_called()
        save.assert_not_awaited()
        self.assertNotIn(session, _active)

    async def test_empty_success_and_partial_header_still_report_corruption(self):
        for data, status in [(b'', 'completed'), (b'RIFF', 'interrupted')]:
            session = ArchiveSession()
            session.feed(data)
            result, save = await self.finish(session, status)
            self.assertIn('archive_error', result)
            save.assert_not_awaited()

    async def test_wav_rates_split_header_and_unknown_sizes(self):
        for rate in (24000, 48000):
            session = ArchiveSession()
            data = bytearray(wav(rate)); struct.pack_into('<I', data, 4, 0xffffffff); struct.pack_into('<I', data, 40, 0xffffffff)
            for byte in data[:44]: session.feed(bytes([byte])); await asyncio.sleep(0)
            await self.feed(session, data[44:])
            result, save = await self.finish(session)
            self.assertEqual(result['audio_archive_id'], 71)
            info = result['audio_archive']
            self.assertEqual(info['source_sample_rate'], rate); self.assertEqual(info['sample_rate'], 48000)
            self.assertEqual(info['codec'], 'opus'); self.assertAlmostEqual(info['duration_seconds'], 1, delta=.05)
            self.assertLess(len(save.call_args.args[0]), len(data))

    async def test_raw_interrupted_and_over_5mb(self):
        session = ArchiveSession(); session.set_metadata({'format':'s16le','sample_rate':48000,'channels':1,'sample_width':2})
        await self.feed(session, bytes(6000000))
        result, save = await self.finish(session, 'interrupted')
        self.assertEqual(save.call_args.kwargs['status'], 'interrupted')
        self.assertEqual(result['audio_archive']['source_size_bytes'], 6000000)
        self.assertAlmostEqual(result['audio_archive']['duration_seconds'], 62.5, delta=.05)

    async def test_long_audio_has_no_30_minute_cutoff(self):
        # Low rate keeps the test small while covering >30 minutes of audio.
        session = ArchiveSession(); session.set_metadata({'format':'s16le','sample_rate':8000,'channels':1,'sample_width':2})
        for _ in range(1801): await self.feed(session, bytes(16000))
        result, save = await self.finish(session)
        self.assertTrue(save.called)
        self.assertAlmostEqual(result['audio_archive']['duration_seconds'], 1801, delta=.05)

    async def test_truncated_finite_wav_and_partial_pcm_frame(self):
        session = ArchiveSession(); await self.feed(session,wav()[:-1])
        result, save = await self.finish(session); self.assertIn('archive_error',result); save.assert_not_awaited()
        session = ArchiveSession(); await self.feed(session,wav()[:-1])
        result, save = await self.finish(session,'interrupted')
        self.assertTrue(save.called); self.assertAlmostEqual(result['audio_archive']['duration_seconds'],1,delta=.05)

    async def test_compressed_binary_is_preserved_and_ogg_codec_identified(self):
        for codec, container, expected in [('libopus','ogg','opus'), ('libvorbis','ogg','vorbis'), ('libmp3lame','mp3','mp3'), ('aac','adts','aac')]:
            original = await _command(wav(), binary('ffmpeg'), '-v', 'error', '-i', 'pipe:0', '-c:a', codec, '-f', container, 'pipe:1')
            session = ArchiveSession(); await self.feed(session, original)
            result, save = await self.finish(session)
            self.assertEqual(save.call_args.args[0], original)
            self.assertEqual(result['audio_archive']['codec'], expected)

    async def test_unknown_pcm_encoder_failure_caps_and_database_failure(self):
        session = ArchiveSession(); session.feed(b'unknown PCM audio data')
        result, save = await self.finish(session); self.assertIn('archive_error', result); save.assert_not_awaited()
        with patch('core.tts_archive.binary', return_value='missing-ffmpeg-test.exe'):
            session = ArchiveSession(); session.feed(wav())
            result, save = await self.finish(session); self.assertIn('archive_error', result); save.assert_not_awaited()
        with patch('core.tts_archive.MAX_QUEUE_BYTES', 16):
            session = ArchiveSession(); session.feed(wav())
            result, save = await self.finish(session); self.assertIn('queue', result['archive_error']); save.assert_not_awaited()
        with patch('core.tts_archive.MAX_ARCHIVE_BYTES', 16):
            session = ArchiveSession(); await self.feed(session, wav())
            result, save = await self.finish(session); self.assertIn('ceiling', result['archive_error']); save.assert_not_awaited()
        with patch('core.tts_archive.MAX_ENCODERS', 0):
            session = ArchiveSession(); result, save = await self.finish(session)
            self.assertIn('concurrency', result['archive_error']); save.assert_not_awaited()
        session = ArchiveSession(); await self.feed(session, wav())
        with patch('core.tts_archive.save_archive', AsyncMock(side_effect=OSError('disk full'))):
            result = await session.finish(log_id=1, provider='test', requested_model='test', resolved_model='test', text='x', status='completed')
            self.assertIn('disk full', result['archive_error'])
        self.assertFalse(_active)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def runner(self, plugin):
        telemetry = SimpleNamespace(create_processing_log=AsyncMock(return_value=1), log_usage=AsyncMock(), finish_processing_log=AsyncMock())
        runner = TTSRunner(SimpleNamespace(tts_providers={'test':plugin}),
            SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan.direct('model','test'))),
            SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[('key',None)]),mark_key_error=AsyncMock()), telemetry)
        return runner, telemetry

    async def test_nonstream_returns_live_bytes_before_background_archive(self):
        data=wav()
        runner,telemetry=self.runner(SimpleNamespace(generate_speech=AsyncMock(return_value=(data,'audio/wav',{}))))
        archive=SimpleNamespace(feed=Mock(),set_metadata=Mock(),error=None,queued_bytes=0,
            finish=AsyncMock(return_value={'audio_archive_id':1}))
        with patch('core.router.runners.tts.ArchiveSession',return_value=archive), patch('core.router.runners.tts.authorize_attempt',AsyncMock()):
            result=await runner.run_speech('test','model','hello')
            self.assertEqual(result[0],data); archive.finish.assert_not_awaited()
            from core.tts_archive import _background
            await asyncio.gather(*list(_background))
            self.assertEqual(archive.finish.call_args.kwargs['status'],'completed')
            self.assertIn('audio_archive_id',telemetry.log_usage.call_args.kwargs['response_json'])
            self.assertNotIn('audio_base64',telemetry.log_usage.call_args.kwargs['response_json'])

    async def test_live_stream_survives_archive_failure_and_generator_close(self):
        async def stream(**kwargs):
            yield b'first'; yield b'second'
        plugin = SimpleNamespace(generate_speech_stream=stream)
        runner, telemetry = self.runner(plugin)
        archive = SimpleNamespace(feed=lambda data:None, set_metadata=lambda data:None, metadata={}, finish=AsyncMock(return_value={'archive_error':'encoder failed'}))
        with patch('core.router.runners.tts.ArchiveSession', return_value=archive), patch('core.router.runners.tts.authorize_attempt', AsyncMock()):
            output = [chunk async for chunk in runner.run_speech_stream('test','model','hello')]
            self.assertEqual(output,[b'first',b'second'])
            await asyncio.sleep(0); await asyncio.sleep(0)
            self.assertIn('archive_error',telemetry.log_usage.call_args.kwargs['response_json'])
            self.assertNotIn('audio_base64',telemetry.log_usage.call_args.kwargs['response_json'])
            gen=runner.run_speech_stream('test','model','hello'); await anext(gen); await gen.aclose()
            await asyncio.sleep(0); await asyncio.sleep(0)
            self.assertEqual(archive.finish.call_args.kwargs['status'],'interrupted')


if __name__ == '__main__': unittest.main()
