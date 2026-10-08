"""Dashboard pagination and local-day reporting contracts, without production DB access."""
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from api import admin, key_management
from database import db_manager

class DashboardReportingTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_count_includes_records_beyond_current_page(self):
        with patch.object(db_manager, 'fetch', AsyncMock(return_value=[{'id':101}])) as fetch, patch.object(db_manager, 'fetchval', AsyncMock(return_value=2000)):
            result = await admin.get_admin_logs(limit=100, offset=100)
        self.assertEqual(result, {'logs':[{'id':101}], 'limit':100, 'offset':100, 'total':2000})
        self.assertEqual(fetch.await_args.args[1:], (100,100))
        self.assertIn('l.created_at DESC, l.id DESC', fetch.await_args.args[0])

    async def test_invalid_pagination_never_queries_database(self):
        with patch.object(db_manager, 'fetch', AsyncMock()) as fetch:
            for limit,offset in [(0,0),(501,0),(100,-1)]:
                with self.assertRaises(HTTPException) as caught:
                    await admin.get_admin_logs(limit,offset)
                self.assertEqual(caught.exception.status_code,422)
        fetch.assert_not_awaited()

    async def test_usage_preserves_local_boundaries_and_unknown_values(self):
        start=datetime.fromisoformat('2026-10-06T21:00:00+00:00')
        end=datetime.fromisoformat('2026-10-07T21:00:00+00:00')
        bucket={'cost':None,'total':0,'usage_unit':'second','usage_amount':12}
        with patch.object(db_manager,'fetchval',AsyncMock(return_value=True)), patch.object(db_manager,'fetch',AsyncMock(side_effect=[[bucket],[dict(bucket,day='2026-10-07')]])) as fetch:
            result=await key_management.usage(start=start,end=end,timezone='Europe/Istanbul')
        self.assertEqual(result['timezone'],'Europe/Istanbul')
        self.assertIsNone(result['totals'][0]['cost'])
        self.assertEqual(result['totals'][0]['total'],0)
        daily=fetch.await_args_list[1].args
        self.assertEqual(daily[1:3],(start,end))
        self.assertEqual(daily[-1],'Europe/Istanbul')
        self.assertIn('AT TIME ZONE $8',daily[0])

    async def test_invalid_timezone_and_date_range_are_rejected(self):
        with patch.object(db_manager,'fetchval',AsyncMock(return_value=False)), patch.object(db_manager,'fetch',AsyncMock()) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await key_management.usage(timezone='invalid-zone')
            self.assertEqual(caught.exception.status_code,422)
        fetch.assert_not_awaited()
        with patch.object(db_manager,'fetchval',AsyncMock(return_value=True)):
            for start,end in [(datetime(2026,10,7),None),(datetime(2026,10,7,tzinfo=timezone.utc),datetime(2026,10,7,tzinfo=timezone.utc))]:
                with self.assertRaises(HTTPException):
                    await key_management.usage(start=start,end=end)

if __name__ == '__main__': unittest.main()
