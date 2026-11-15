"""Input audio (and every media kind in one provider-native body) becomes one archive reference per sha256."""
import asyncio
import base64
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image

from core import input_audio_archive, image_archive, document_archive

WAV = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00' + bytes(range(250, 256)) * 9


async def fake_audio(manager, data, metadata):
    fake_audio.saved.append(metadata['sha256'])
    return {'input_audio_archive_id': 21, **metadata}


class InputAudio(unittest.TestCase):
    def run_json(self, body):
        fake_audio.saved = []
        with patch.object(input_audio_archive, 'save_input_audio', fake_audio):
            return json.loads(asyncio.run(input_audio_archive.archive_input_audio_json(json.dumps(body), None)))

    def test_openai_input_audio_and_repeat_saved_once(self):
        part = {'type': 'input_audio', 'input_audio': {'data': base64.b64encode(WAV).decode(), 'format': 'wav'}}
        out = self.run_json({'messages': [{'role': 'user', 'content': [part, json.loads(json.dumps(part))]}]})
        refs = [p['input_audio']['data'] for p in out['messages'][0]['content']]
        self.assertEqual([r['input_audio_archive_id'] for r in refs], [21, 21])
        self.assertEqual(refs[0]['mime_type'], 'audio/wav')
        self.assertEqual(len(fake_audio.saved), 1)

    def test_gemini_urlsafe_inline_data_after_function_response(self):
        data = base64.urlsafe_b64encode(WAV).decode()
        out = self.run_json({'contents': [
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'open', 'response': {'ok': True}}}]},
            {'role': 'user', 'parts': [{'text': 'Hafızadan açılan dosyalar'}, {'inlineData': {'mimeType': 'audio/wav', 'data': data}}]}]})
        ref = out['contents'][1]['parts'][1]['inlineData']['data']
        self.assertEqual(ref['input_audio_archive_id'], 21)
        self.assertEqual(ref['size_bytes'], len(WAV))

    def test_failures_and_urls_keep_the_log_unchanged(self):
        body = {'a': {'mimeType': 'audio/wav', 'data': 'https://x/a.wav'}, 'b': {'mimeType': 'audio/wav', 'data': '!!notbase64!!'},
                'c': {'type': 'input_audio', 'input_audio': {'data': 'AAAA', 'format': 'unknownfmt'}}}
        self.assertEqual(self.run_json(body), body)
        self.assertEqual(fake_audio.saved, [])


class WholeGeminiBody(unittest.TestCase):
    def test_every_media_kind_is_referenced_text_attachment_stays(self):
        buf = io.BytesIO(); Image.new('RGB', (3, 2), 'red').save(buf, 'PNG')
        pdf = b'%PDF-1.4\n' + b'x' * 20
        text = 'Ek 1 — Metin: notlar.txt\n<file_content>\nmerhaba\n</file_content>'
        body = {'contents': [{'role': 'user', 'parts': [{'text': text},
            {'inlineData': {'mimeType': 'image/png', 'data': base64.urlsafe_b64encode(buf.getvalue()).decode()}},
            {'inlineData': {'mimeType': 'audio/wav', 'data': base64.urlsafe_b64encode(WAV).decode()}},
            {'inlineData': {'mimeType': 'application/pdf', 'data': base64.urlsafe_b64encode(pdf).decode()}}]}]}

        async def img(manager, data, md): return {'image_archive_id': 1, **md}
        async def doc(manager, data, md): return {'document_archive_id': 3, **md}
        from core.video_archive import archive_log_media_json
        with patch.object(image_archive, 'save_image', img), patch.object(document_archive, 'save_document', doc), \
                patch.object(input_audio_archive, 'save_input_audio', fake_audio):
            out = json.loads(asyncio.run(archive_log_media_json(json.dumps(body), None)))
        parts = out['contents'][0]['parts']
        self.assertEqual(parts[0]['text'], text)
        self.assertEqual(parts[1]['inlineData']['data']['image_archive_id'], 1)
        self.assertEqual(parts[2]['inlineData']['data']['input_audio_archive_id'], 21)
        self.assertEqual(parts[3]['inlineData']['data']['document_archive_id'], 3)


if __name__ == '__main__':
    unittest.main()
