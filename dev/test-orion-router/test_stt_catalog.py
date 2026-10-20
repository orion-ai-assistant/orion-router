import ast
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from core import availability


def authenticate():
    raise HTTPException(401, 'Not authenticated')


class SttCatalogProxyTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / 'api/transcriptions.py'
        node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == 'audio_languages')
        self.app = FastAPI()
        self.client = AsyncMock()
        namespace = dict(router=self.app, Depends=Depends, authenticate_request=authenticate,
                         get_http_client=lambda: self.client, STT_HOST='stt', STT_PORT=8800,
                         httpx=httpx, HTTPException=HTTPException, STT_SERVICE='STT',
                         ServiceUnavailable=availability.ServiceUnavailable,
                         available=availability.available, unavailable=availability.unavailable)
        availability._down.clear()
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)

    def test_authentication_required(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get('/v1/audio/languages').status_code, 401)
        self.client.get.assert_not_called()

    def test_only_metadata_is_forwarded_from_stt(self):
        self.app.dependency_overrides[authenticate] = lambda: {'key_id': 1}
        self.client.get.return_value = httpx.Response(200, request=httpx.Request('GET', 'http://stt'),
            json={'aliases': {'nb': 'no'}, 'languages': {'tr': {'name': 'Turkish', 'prompt': 'private'}}})
        with TestClient(self.app) as client:
            response = client.get('/v1/audio/languages')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'aliases': {'nb': 'no'}, 'languages': {'tr': {'name': 'Turkish'}}})
        self.client.get.assert_awaited_once_with('http://stt:8800/v1/audio/language-catalog', timeout=4)

    def test_offline_stt_returns_503(self):
        self.app.dependency_overrides[authenticate] = lambda: {'key_id': 1}
        self.client.get.side_effect = httpx.ConnectError('offline')
        with TestClient(self.app) as client:
            self.assertEqual(client.get('/v1/audio/languages').status_code, 503)

    def test_a_stopped_stt_is_a_state_logged_once_and_tried_again_every_time(self):
        self.app.dependency_overrides[authenticate] = lambda: {'key_id': 1}
        self.client.get.side_effect = httpx.ConnectError('offline')
        with TestClient(self.app) as client, self.assertLogs('service-router.availability', 'INFO') as logs:
            for _ in range(3):
                response = client.get('/v1/audio/languages')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers['Retry-After'], '5')
            self.assertEqual(3, self.client.get.await_count)  # Never cached as down: every request tries.
            self.client.get.side_effect = None
            self.client.get.return_value = httpx.Response(200, request=httpx.Request('GET', 'http://stt'),
                json={'aliases': {}, 'languages': {'tr': {'name': 'Turkish'}}})
            self.assertEqual(client.get('/v1/audio/languages').status_code, 200)
            client.get('/v1/audio/languages')
        self.assertEqual(2, len(logs.output))  # "not available" once, "available again" once.
        self.assertIn('STT is not available', logs.output[0])
        self.assertIn('STT is available again', logs.output[1])
