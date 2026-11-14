"""A provider connection that drops before any output (httpx ReadError has no message) must reach the user as a
readable message, and must not stop the key/fallback attempts like a request error would."""
import asyncio
import unittest

import httpx

from core.router.runners.chat import describe_failure, is_connection_failure


class ConnectionFailureTests(unittest.TestCase):
    def test_a_read_error_without_message_gets_a_readable_one(self):
        error = httpx.ReadError('')
        self.assertTrue(is_connection_failure(error))
        message = describe_failure(error, 'openrouter')
        self.assertIn('openrouter', message)
        self.assertIn('ReadError', message)

    def test_timeouts_and_resets_count_as_connection_failures(self):
        for error in (httpx.ConnectTimeout(''), ConnectionResetError(), asyncio.TimeoutError()):
            self.assertTrue(is_connection_failure(error))

    def test_a_provider_answer_is_not_a_connection_failure(self):
        self.assertFalse(is_connection_failure(ValueError('model does not support audio input')))
        self.assertIn('ValueError', describe_failure(ValueError(), 'openrouter'))


if __name__ == '__main__':
    unittest.main()
