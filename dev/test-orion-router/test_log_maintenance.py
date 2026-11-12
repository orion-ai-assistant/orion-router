"""Request log maintenance: one-time thinking-token backfill and 30-day body pruning, with the database mocked."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from core import log_maintenance
from database import db_manager


class LogMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        sleep = patch.object(log_maintenance.asyncio, 'sleep', AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    async def test_backfill_runs_in_batches_then_records_that_it_is_done(self):
        batches = [[{'last_id': 500, 'filled': 3}], [{'last_id': 900, 'filled': 2}], [{'last_id': None, 'filled': 0}]]
        with patch.object(db_manager, 'get_config', AsyncMock(return_value=None)), \
                patch.object(db_manager, 'fetch', AsyncMock(side_effect=batches)) as fetch, \
                patch.object(db_manager, 'upsert_config', AsyncMock()) as save:
            filled = await log_maintenance.backfill_thoughts_tokens()
        self.assertEqual(filled, 5)
        self.assertEqual([call.args[1] for call in fetch.await_args_list], [0, 500, 900])
        save.assert_awaited_once_with(log_maintenance.BACKFILL_DONE, 'true')

    async def test_backfill_does_nothing_once_done(self):
        with patch.object(db_manager, 'get_config', AsyncMock(return_value='true')), \
                patch.object(db_manager, 'fetch', AsyncMock()) as fetch, \
                patch.object(db_manager, 'upsert_config', AsyncMock()) as save:
            self.assertEqual(await log_maintenance.backfill_thoughts_tokens(), 0)
        fetch.assert_not_awaited()
        save.assert_not_awaited()

    async def test_a_failed_backfill_is_not_marked_done(self):
        with patch.object(db_manager, 'get_config', AsyncMock(return_value=None)), \
                patch.object(db_manager, 'fetch', AsyncMock(side_effect=RuntimeError('down'))), \
                patch.object(db_manager, 'upsert_config', AsyncMock()) as save:
            with self.assertRaises(RuntimeError):
                await log_maintenance.backfill_thoughts_tokens()
        save.assert_not_awaited()

    async def test_prune_replaces_old_bodies_with_a_note_and_skips_running_requests(self):
        batches = [[{'last_id': 500, 'pruned': 500}], [{'last_id': 640, 'pruned': 100}], []]
        with patch.object(db_manager, 'fetch', AsyncMock(side_effect=batches)) as fetch:
            pruned = await log_maintenance.prune_old_payloads()
        self.assertEqual(pruned, 600)
        sql = ' '.join(fetch.await_args_list[0].args[0].split())
        self.assertIn("status IS DISTINCT FROM 'processing'", sql)
        self.assertIn('created_at < NOW() - make_interval(days => $2)', sql)
        self.assertEqual(fetch.await_args_list[0].args[1:4], (0, 30, log_maintenance.BATCH))
        self.assertEqual([call.args[1] for call in fetch.await_args_list], [0, 500, 640])
        note = json.loads(fetch.await_args_list[0].args[4])
        self.assertIn('30', note['note'])

    async def test_a_round_that_fails_waits_for_the_next_one_and_cancel_stops_the_loop(self):
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise asyncio.CancelledError

        with patch.object(log_maintenance, 'backfill_thoughts_tokens', AsyncMock(side_effect=[RuntimeError('db'), 0])), \
                patch.object(log_maintenance, 'prune_old_payloads', AsyncMock(return_value=0)) as prune, \
                patch.object(log_maintenance.asyncio, 'sleep', sleep), self.assertLogs(level='WARNING'):
            with self.assertRaises(asyncio.CancelledError):
                await log_maintenance.run_forever()
        self.assertEqual(sleeps, [log_maintenance.EVERY_SECONDS] * 2)
        prune.assert_awaited_once()
