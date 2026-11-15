"""Provider-native Gemini bodies get image archive references (the SDK sends URL-safe Base64)."""
import asyncio
import base64
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image

from core import image_archive


def png_bytes():
    # Pick a size whose bytes make standard Base64 contain '+' or '/', so URL-safe differs.
    for width in range(1, 200):
        out = io.BytesIO()
        Image.new('RGB', (width, 3), (250, 3, 255)).save(out, 'PNG')
        if {'+', '/'} & set(base64.b64encode(out.getvalue()).decode()):
            return out.getvalue()
    raise AssertionError('no sample with + or /')


class GeminiLogArchive(unittest.TestCase):
    def test_urlsafe_inline_data_after_function_response_is_archived(self):
        raw = png_bytes()
        urlsafe = base64.urlsafe_b64encode(raw).decode()
        self.assertTrue({'-', '_'} & set(urlsafe))
        saved = []

        async def fake_save(manager, data, metadata):
            saved.append(metadata['sha256'])
            return {'image_archive_id': 11, **metadata}

        image = {'inlineData': {'mimeType': 'image/png', 'data': urlsafe}}
        body = {'model': 'm', 'tools': [{}], 'systemInstruction': {'parts': [{'text': 's'}]}, 'contents': [
            {'role': 'model', 'parts': [{'functionCall': {'name': 'open', 'args': {}}}]},
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'open', 'response': {'ok': True}}}]},
            {'role': 'user', 'parts': [{'text': 'Hafızadan açılan dosyalar'}, image]}]}
        with patch.object(image_archive, 'save_image', fake_save):
            out = json.loads(asyncio.run(image_archive.archive_images_json(json.dumps(body), None)))
        data = out['contents'][2]['parts'][1]['inlineData']['data']
        self.assertEqual(data['image_archive_id'], 11)
        self.assertEqual(len(data['sha256']), 64)
        self.assertEqual(len(saved), 1)

    def test_standard_base64_still_works(self):
        raw = png_bytes()
        _, meta = image_archive._decode_image(base64.b64encode(raw).decode())
        self.assertEqual(meta['mime_type'], 'image/png')


if __name__ == '__main__':
    unittest.main()
