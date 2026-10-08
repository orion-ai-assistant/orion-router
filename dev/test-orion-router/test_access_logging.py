"""Real Uvicorn access formatting must coexist with request secret redaction."""
import asyncio
import io
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import httpx
import uvicorn
from starlette.responses import JSONResponse
from uvicorn.logging import AccessFormatter, DefaultFormatter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import secret_guard
from core.tls_server import _LoopbackApplication, _Server

ACCESS_MESSAGE = '%s - "%s %s HTTP/%s" %d'
ACCESS_FORMAT = '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'
SECRET = 'upstream-access-log-fixture'


class CapturingHandler(logging.StreamHandler):
    def __init__(self, formatter):
        super().__init__(io.StringIO())
        self.setFormatter(formatter)
        self.errors = []

    def handleError(self, record):
        self.errors.append(sys.exc_info()[1])


class AccessLoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        token = secret_guard._secrets.set(())
        self.addCleanup(secret_guard._secrets.reset, token)

    def record(self, name, message, args, exc_info=None, extra=None):
        return logging.getLogger(name).makeRecord(name, logging.INFO, __file__, 1, message, args, exc_info, extra=extra)

    def test_colored_startup_messages_keep_their_arguments(self):
        secret_guard.remember(SECRET)
        record = self.record('uvicorn.error', 'Uvicorn running on %s://%s:%d',
            ('https', SECRET, 9443), extra={'color_message': 'Uvicorn running on \x1b[1m%s://%s:%d\x1b[0m'})
        rendered = DefaultFormatter('%(levelprefix)s %(message)s', use_colors=True).format(record)
        self.assertIn('https://[REDACTED]:9443', rendered)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn('%s', rendered)
        process = self.record('uvicorn.error', 'Started server process [%d]', (12345,),
            extra={'color_message': 'Started server process [\x1b[36m%d\x1b[0m]'})
        self.assertIn('12345', DefaultFormatter('%(message)s', use_colors=True).format(process))

    def test_companion_listener_has_a_distinct_banner_with_bound_port(self):
        server = _Server(uvicorn.Config(Mock(), host='127.0.0.1', port=0, log_config=None))
        server.config.load()
        socket = Mock()
        socket.getsockname.return_value = ('127.0.0.1', 20128)
        with self.assertLogs('service-router', level='INFO') as logs:
            server._log_started_message([socket])
        self.assertEqual(len(logs.output), 1)
        self.assertIn('Router local HTTP listener running on http://127.0.0.1:20128', logs.output[0])

    def test_access_formatter_retains_five_arguments_and_numeric_status(self):
        secret_guard.remember(SECRET)
        record = self.record('uvicorn.access', ACCESS_MESSAGE,
            ('127.0.0.1:64038', 'GET', '/dashboard/api/stats?key=' + SECRET, '1.1', 200))
        rendered = AccessFormatter(ACCESS_FORMAT, use_colors=False).format(record)
        self.assertEqual(len(record.args), 5)
        self.assertEqual(record.args[-1], 200)
        self.assertIn('GET /dashboard/api/stats?key=[REDACTED] HTTP/1.1', rendered)
        self.assertIn('200 OK', rendered)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn(SECRET, logging.Formatter('%(message)s').format(record))

    def test_other_messages_and_exceptions_keep_their_existing_redaction(self):
        secret_guard.remember(SECRET)
        record = self.record('service-router', 'Upstream %s returned %d', (SECRET, 503))
        self.assertEqual(record.getMessage(), 'Upstream [REDACTED] returned 503')
        self.assertEqual(record.args, ())
        mapped = self.record('service-router', 'Upstream %(key)s', ({'key': SECRET},))
        self.assertEqual(mapped.getMessage(), 'Upstream [REDACTED]')
        try:
            raise ValueError('Failed with ' + SECRET)
        except ValueError:
            error = self.record('service-router', 'Failed: %s', (SECRET,), sys.exc_info())
        rendered = logging.Formatter('%(message)s').format(error)
        self.assertIn('ValueError: Failed with [REDACTED]', rendered)
        self.assertNotIn(SECRET, rendered)

    async def test_repeated_successful_http_requests_produce_access_logs_without_errors(self):
        access = logging.getLogger('uvicorn.access')
        old = access.handlers, access.level, access.propagate, access.disabled
        handler = CapturingHandler(AccessFormatter(ACCESS_FORMAT, use_colors=False))
        access.handlers = [handler]
        access.setLevel(logging.INFO)
        access.propagate = False
        access.disabled = False
        def restore():
            access.handlers, access.level, access.propagate, access.disabled = old
            handler.close()
        self.addCleanup(restore)

        async def app(scope, receive, send):
            secret_guard.remember(SECRET)
            await JSONResponse({'ok': True})(scope, receive, send)

        server = _Server(uvicorn.Config(_LoopbackApplication(app), host='127.0.0.1', port=0,
            lifespan='off', log_config=None, access_log=True, proxy_headers=False))
        task = asyncio.create_task(server.serve())
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        self.fail('Uvicorn exited before starting')
                    await asyncio.sleep(0.01)
            port = server.servers[0].sockets[0].getsockname()[1]
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                for _ in range(2):
                    responses = await asyncio.gather(*[
                        client.get('/dashboard/api/stats', params={'key': SECRET}) for _ in range(10)])
                    self.assertTrue(all(response.status_code == 200 for response in responses))
            self.assertEqual(handler.errors, [])
            lines = handler.stream.getvalue().splitlines()
            self.assertEqual(len(lines), 20)
            self.assertTrue(all('200 OK' in line and '[REDACTED]' in line for line in lines))
            self.assertNotIn(SECRET, handler.stream.getvalue())
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=10)


if __name__ == '__main__':
    unittest.main()
