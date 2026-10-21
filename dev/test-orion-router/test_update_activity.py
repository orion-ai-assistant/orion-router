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


if __name__ == '__main__':
    unittest.main()
