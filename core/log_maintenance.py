"""Keeps the request log light for a Router that runs for weeks.

Each row keeps its summary (model, tokens, cost, time) for good. The request and response bodies, which can
be large, are kept PAYLOAD_DAYS and then replaced by a short note: the table, the log page and the backups
stay small however long the Router runs. Totals and the stats page read only the summary columns.

Older rows kept their thinking token count only inside the response body; it is copied to its column once,
before any body is pruned, so the log list never has to open a body.
"""
import asyncio
import json
import logging

from database import db_manager

logger = logging.getLogger(__name__)

PAYLOAD_DAYS = 30
EVERY_SECONDS = 6 * 3600
BATCH = 500
PAUSE = 0.2  # Between batches: requests being served keep the database.
BACKFILL_DONE = 'maintenance.thoughts_tokens_backfilled'
PRUNED = json.dumps({'note': f'Gövde {PAYLOAD_DAYS} günden eski olduğu için silindi; özet satırı duruyor.'})


async def backfill_thoughts_tokens() -> int:
    """Copy thoughts_tokens from older response bodies to the column, once."""
    if await db_manager.get_config(BACKFILL_DONE):
        return 0
    filled, last_id = 0, 0
    while True:
        rows = await db_manager.fetch(
            """
            WITH batch AS (
                SELECT id FROM router_request_logs WHERE id > $1 ORDER BY id LIMIT $2
            ), updated AS (
                UPDATE router_request_logs l
                SET thoughts_tokens = (l.response_json->'usage'->>'thoughts_tokens')::INTEGER
                FROM batch
                WHERE l.id = batch.id AND COALESCE(l.thoughts_tokens, 0) = 0
                  AND l.response_json->'usage'->>'thoughts_tokens' ~ '^[0-9]+$'
                RETURNING l.id
            )
            SELECT (SELECT max(id) FROM batch) AS last_id, (SELECT count(*) FROM updated) AS filled
            """,
            last_id, BATCH,
        )
        if not rows or rows[0]['last_id'] is None:
            break
        last_id, filled = rows[0]['last_id'], filled + rows[0]['filled']
        await asyncio.sleep(PAUSE)
    await db_manager.upsert_config(BACKFILL_DONE, 'true')
    return filled


async def prune_old_payloads() -> int:
    """Replace the bodies of rows older than PAYLOAD_DAYS with a short note, a batch at a time."""
    pruned, last_id = 0, 0
    while True:
        rows = await db_manager.fetch(
            """
            WITH batch AS (
                SELECT id FROM router_request_logs
                WHERE id > $1 AND created_at < NOW() - make_interval(days => $2)
                ORDER BY id LIMIT $3
            ), updated AS (
                UPDATE router_request_logs l SET request_json = $4::jsonb, response_json = $4::jsonb
                FROM batch
                WHERE l.id = batch.id AND l.status IS DISTINCT FROM 'processing'
                  AND (l.request_json IS DISTINCT FROM $4::jsonb OR l.response_json IS DISTINCT FROM $4::jsonb)
                RETURNING l.id
            )
            SELECT (SELECT max(id) FROM batch) AS last_id, (SELECT count(*) FROM updated) AS pruned
            """,
            last_id, PAYLOAD_DAYS, BATCH, PRUNED,
        )
        if not rows or rows[0]['last_id'] is None:
            return pruned
        last_id, pruned = rows[0]['last_id'], pruned + rows[0]['pruned']
        await asyncio.sleep(PAUSE)


async def run_forever() -> None:
    while True:
        try:
            filled = await backfill_thoughts_tokens()
            if filled:
                logger.info('Copied thinking token counts of %d older request log(s) to their column.', filled)
            pruned = await prune_old_payloads()
            if pruned:
                logger.info('Removed the bodies of %d request log(s) older than %d days.', pruned, PAYLOAD_DAYS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Maintenance waits for the next round; serving never depends on it.
            logger.warning('Request log maintenance skipped this round: %s', exc)
        await asyncio.sleep(EVERY_SECONDS)
