import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app
from core.dependencies import authenticate_websocket

class MockBackendWS:
    def __init__(self):
        self.sent = []
        self.queue = asyncio.Queue()

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


class MockConnectCM:
    def __init__(self, backend):
        self.backend = backend
    async def __aenter__(self):
        return self.backend
    async def __aexit__(self, *args):
        pass

class TestSTTStreaming(unittest.TestCase):
    def test_websocket_stream_unauthorized(self):
        """Token olmadan veya geçersiz tokenla bağlanıldığında bağlantı reddedilmeli."""
        app.dependency_overrides.pop(authenticate_websocket, None)
        client = TestClient(app)
        try:
            with client.websocket_connect("/v1/audio/transcriptions/stream") as ws:
                self.fail("Bağlantı token olmadan kabul edilmemeliydi.")
        except Exception:
            pass  # Beklenen davranış: WebSocketDisconnect / 1008

    def test_websocket_stream_full_duplex_proxy(self):
        """Yetkili istemci bağlandığında backend'e PCM gönderip live/final mesajları almalı."""
        from fastapi import WebSocket
        async def mock_auth(websocket: WebSocket):
            return {"source": "system", "key_id": None}
        app.dependency_overrides[authenticate_websocket] = mock_auth
        mock_backend = MockBackendWS()

        mock_backend.queue.put_nowait(json.dumps({"type": "live", "text": "merhaba"}))
        mock_backend.queue.put_nowait(json.dumps({"type": "final", "text": "merhaba nasılsın"}))

        with patch("api.transcriptions.websockets.connect", side_effect=lambda url: MockConnectCM(mock_backend)):
            client = TestClient(app)
            with client.websocket_connect("/v1/audio/transcriptions/stream?token=test") as ws:
                # 1. Backend'den live mesajı al
                msg1 = ws.receive_json()
                self.assertEqual(msg1["type"], "live")
                self.assertEqual(msg1["text"], "merhaba")

                # 2. İstemciden sahte PCM baytları gönder
                pcm_payload = b"\x00\x01\x02\x03" * 100
                ws.send_bytes(pcm_payload)

                # 3. Backend'den final mesajı al
                msg2 = ws.receive_json()
                self.assertEqual(msg2["type"], "final")
                self.assertEqual(msg2["text"], "merhaba nasılsın")

                # End backend stream
                mock_backend.queue.put_nowait(None)

        # Backend'e gönderilen baytları doğrula
        self.assertIn(pcm_payload, mock_backend.sent)
        print("  [PASS] WebSocket STT full-duplex proxy (live & final) verified!")

    def test_websocket_stream_session_logging(self):
        """Streaming STT oturumunun başında create_streaming_log, final segmentlerde ve bitişte update_streaming_log çağrılmalı."""
        from fastapi import WebSocket
        async def mock_auth(websocket: WebSocket):
            return {"source": "virtual_key", "key_id": "key-test-123", "name": "Test Key"}
        app.dependency_overrides[authenticate_websocket] = mock_auth

        mock_backend = MockBackendWS()
        mock_backend.queue.put_nowait(json.dumps({"type": "live", "text": "test"}))
        mock_backend.queue.put_nowait(json.dumps({"type": "final", "text": "birinci cümle", "duration": 1.5, "language": "tr"}))

        created_logs = []
        updated_logs = []

        async def mock_create(**kwargs):
            created_logs.append(kwargs)
            return 999

        async def mock_update(**kwargs):
            updated_logs.append(kwargs)

        with patch("api.transcriptions.db_manager.create_streaming_log", side_effect=mock_create), \
             patch("api.transcriptions.db_manager.update_streaming_log", side_effect=mock_update), \
             patch("api.transcriptions.websockets.connect", side_effect=lambda url: MockConnectCM(mock_backend)):

            client = TestClient(app)
            with client.websocket_connect("/v1/audio/transcriptions/stream?token=test") as ws:
                _ = ws.receive_json()  # live
                ws.send_bytes(b"\x00" * 3200)
                _ = ws.receive_json()  # final
                mock_backend.queue.put_nowait(None)

        # 1. create_streaming_log kontrolü
        self.assertEqual(len(created_logs), 1)
        self.assertEqual(created_logs[0]["key_id"], "key-test-123")
        self.assertEqual(created_logs[0]["model"], "local-stt")
        self.assertEqual(created_logs[0]["status"], "streaming")
        self.assertEqual(created_logs[0]["capability"], "stt")

        # 2. update_streaming_log kontrolü (final segment + finalize)
        self.assertGreaterEqual(len(updated_logs), 1)
        final_call = updated_logs[-1]
        self.assertEqual(final_call["log_id"], 999)
        self.assertEqual(final_call["status"], "success")
        self.assertEqual(final_call["success"], True)

        resp = json.loads(final_call["response_json"])
        self.assertEqual(resp["text"], "birinci cümle")
        self.assertEqual(resp["total_segments"], 1)
        self.assertEqual(resp["segments"][0]["text"], "birinci cümle")
        self.assertEqual(resp["segments"][0]["duration"], 1.5)
        print("  [PASS] Streaming STT session logging with segments verified!")

if __name__ == "__main__":
    unittest.main()
