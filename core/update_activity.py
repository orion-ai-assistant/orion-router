"""Work in flight, so "Şimdi Kur" on a Router-only installation never cuts a running request.

The Hub waits for its own idle moment before an update (chats, voice, transfers). A standalone Router has no Hub
to ask, so it counts its own API traffic: every /v1 request and every websocket counts while it runs. The panel's
apply asks `drain()` first: new API requests are answered 503 + Retry-After for a short while, running ones finish,
and only then is the update handed to the retained watcher. If work does not end in time nothing is stopped.
"""
import asyncio
import time

DRAIN_TIMEOUT = 60.0      # how long the panel waits for running work to finish
DRAIN_HOLD = 120.0        # new API requests are held off at most this long after a drain started
POLL = 0.25


class Activity:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.active = 0
        self.hold_until = 0.0

    @property
    def draining(self):
        return self.clock() < self.hold_until

    def release(self):
        self.hold_until = 0.0

    async def drain(self, timeout=DRAIN_TIMEOUT, hold=DRAIN_HOLD, sleep=asyncio.sleep, extra=lambda: 0):
        """True when no request is running any more (new ones are refused meanwhile) and `extra()` - work that
        outlives its request, like archive encoding - is zero; False on timeout, with the hold lifted again so
        nothing is left refused."""
        self.hold_until = self.clock() + hold
        deadline = self.clock() + timeout
        while self.active > 0 or extra() > 0:
            if self.clock() >= deadline:
                self.release()
                return False
            await sleep(POLL)
        return True


activity = Activity()


def counted(scope):
    """API traffic: /v1 requests (chat, speech, embeddings ...) and every websocket. The panel's own status polls,
    health probes and static files are not work."""
    if scope['type'] == 'websocket':
        return True
    return scope['type'] == 'http' and scope.get('path', '').startswith('/v1/')


class ActivityTracker:
    def __init__(self, app, tracker=None):
        self.app = app
        self.tracker = tracker or activity

    async def __call__(self, scope, receive, send):
        if not counted(scope):
            await self.app(scope, receive, send)
            return
        if self.tracker.draining and scope['type'] == 'http':
            await send({'type': 'http.response.start', 'status': 503,
                        'headers': [(b'retry-after', b'5'), (b'content-type', b'application/json')]})
            await send({'type': 'http.response.body', 'body': b'{"detail":"Router is being updated"}'})
            return
        if self.tracker.draining:
            await send({'type': 'websocket.close', 'code': 1013})
            return
        self.tracker.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.tracker.active -= 1
