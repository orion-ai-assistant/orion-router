"""A Router-only "Şimdi Kur" waits for running API work and never cuts it."""
import asyncio
import unittest

from core.update_activity import Activity, ActivityTracker


def run(coroutine):
    return asyncio.run(coroutine)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Drain(unittest.TestCase):
    def test_idle_router_drains_at_once_and_refuses_new_api_requests_meanwhile(self):
        clock = Clock()
        activity = Activity(clock)
        self.assertTrue(run(activity.drain(timeout=5)))
        self.assertTrue(activity.draining)
        clock.now = 500.0
        self.assertFalse(activity.draining)  # The hold ends by itself.

    def test_running_work_is_waited_for(self):
        clock = Clock()
        activity = Activity(clock)
        activity.active = 1

        async def sleeper(seconds):
            clock.now += seconds
            if clock.now >= 2:
                activity.active = 0

        self.assertTrue(run(activity.drain(timeout=60, sleep=sleeper)))

    def test_work_that_does_not_end_is_not_cut_and_the_hold_is_lifted(self):
        clock = Clock()
        activity = Activity(clock)
        activity.active = 1

        async def sleeper(seconds):
            clock.now += seconds

        self.assertFalse(run(activity.drain(timeout=3, sleep=sleeper)))
        self.assertFalse(activity.draining)
        self.assertEqual(activity.active, 1)

    def test_work_that_outlives_its_request_is_waited_for_too(self):
        clock = Clock()
        activity = Activity(clock)
        left = [2]

        async def sleeper(seconds):
            clock.now += seconds
            left[0] = max(0, left[0] - 1)

        self.assertTrue(run(activity.drain(timeout=60, sleep=sleeper, extra=lambda: left[0])))
        self.assertEqual(left[0], 0)


class Tracker(unittest.TestCase):
    def call(self, tracker, scope):
        sent = []

        async def app(scope, receive, send):
            sent.append(('app', tracker.active))

        async def send(message):
            sent.append(message)
        wrapped = ActivityTracker(app, tracker)
        run(wrapped(scope, None, send))
        return sent

    def test_v1_requests_count_while_they_run(self):
        activity = Activity()
        sent = self.call(activity, {'type': 'http', 'path': '/v1/chat/completions'})
        self.assertEqual(sent, [('app', 1)])
        self.assertEqual(activity.active, 0)

    def test_panel_and_health_requests_are_not_work(self):
        activity = Activity()
        sent = self.call(activity, {'type': 'http', 'path': '/dashboard/api/system/update-status'})
        self.assertEqual(sent, [('app', 0)])

    def test_draining_answers_new_api_requests_with_503(self):
        activity = Activity()
        run(activity.drain(timeout=1))
        sent = self.call(activity, {'type': 'http', 'path': '/v1/chat/completions'})
        self.assertEqual(sent[0]['status'], 503)
        self.assertEqual(activity.active, 0)
        sent = self.call(activity, {'type': 'http', 'path': '/dashboard/api/system/update-status'})
        self.assertEqual(sent, [('app', 0)])

    def test_a_websocket_counts_and_is_refused_while_draining(self):
        activity = Activity()
        sent = self.call(activity, {'type': 'websocket', 'path': '/v1/audio/transcriptions/stream'})
        self.assertEqual(sent, [('app', 1)])
        run(activity.drain(timeout=1))
        sent = self.call(activity, {'type': 'websocket', 'path': '/v1/audio/transcriptions/stream'})
        self.assertEqual(sent, [{'type': 'websocket.close', 'code': 1013}])


class EndToEnd(unittest.TestCase):
    """A real FastAPI app behind the middleware, driven through raw ASGI (httpx buffers a whole response)."""

    @staticmethod
    def scope(path, method='POST'):
        return {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method, 'path': path,
                'raw_path': path.encode(), 'query_string': b'', 'headers': [], 'scheme': 'http',
                'server': ('test', 80), 'client': ('127.0.0.1', 1)}

    def test_a_streaming_response_holds_the_drain_until_it_ends(self):
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse

        async def scenario():
            activity = Activity()
            release = asyncio.Event()
            first_chunk = asyncio.Event()
            app = FastAPI()

            @app.post('/v1/chat/completions')
            async def chat():
                async def body():
                    yield b'data: first\n\n'
                    first_chunk.set()
                    await release.wait()
                    yield b'data: last\n\n'
                return StreamingResponse(body(), media_type='text/event-stream')

            @app.get('/dashboard/api/system/update-status')
            async def status():
                return {'ok': True}
            app.add_middleware(ActivityTracker, tracker=activity)

            async def call(path, method='POST'):
                messages = []
                delivered = []

                async def receive():
                    if not delivered:
                        delivered.append(True)
                        return {'type': 'http.request', 'body': b'', 'more_body': False}
                    await asyncio.Event().wait()  # The client stays connected: no disconnect is ever signalled.

                async def send(message):
                    messages.append(message)
                await app(self.scope(path, method), receive, send)
                return messages

            running = asyncio.create_task(call('/v1/chat/completions'))
            await asyncio.wait_for(first_chunk.wait(), 5)
            self.assertEqual(activity.active, 1)
            drain = asyncio.create_task(activity.drain(timeout=30))
            await asyncio.sleep(0.6)
            self.assertFalse(drain.done())  # The running stream is waited for, not cut.
            refused = await call('/v1/chat/completions')
            self.assertEqual(refused[0]['status'], 503)
            ok = await call('/dashboard/api/system/update-status', 'GET')
            self.assertEqual(ok[0]['status'], 200)
            release.set()
            messages = await asyncio.wait_for(running, 5)
            bodies = [m.get('body') for m in messages if m['type'] == 'http.response.body']
            self.assertEqual(bodies[:2], [b'data: first\n\n', b'data: last\n\n'])
            self.assertTrue(await asyncio.wait_for(drain, 5))
            self.assertEqual(activity.active, 0)
        run(scenario())


if __name__ == '__main__':
    unittest.main()
