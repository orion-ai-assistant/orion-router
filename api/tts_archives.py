"""Admin-only playback and discovery, independent of request log lifetime."""
import re
import asyncio
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from core.dependencies import verify_admin
from database import db_manager
from core.tts_archive import runtime_status

router = APIRouter(prefix="/dashboard/api/audio-archives", dependencies=[Depends(verify_admin)], tags=["Dashboard"])


@router.get("/status")
async def archive_status():
    status = runtime_status()
    try:
        row = await asyncio.wait_for(db_manager.fetchrow("""SELECT
            pg_total_relation_size('router_tts_audio_archives') AS archive_relation_bytes,
            pg_database_size(current_database()) AS database_bytes,
            (SELECT count(*) FROM router_request_logs WHERE response_json ? 'archive_error') AS logged_archive_errors
            """), 5)
        status.update(dict(row))
        from core.config import POSTGRES_HOST
        status["database_disk"] = None
        if POSTGRES_HOST in ("localhost", "127.0.0.1", "::1"):
            try:
                path = await asyncio.wait_for(db_manager.fetchval("SHOW data_directory"), 5)
                disk = await asyncio.to_thread(shutil.disk_usage, path)
                status["database_disk"] = {"free_bytes": disk.free, "total_bytes": disk.total,
                    "low_space": disk.free < max(1024**3, disk.total * .05)}
            except (OSError, PermissionError):
                pass
    except Exception as exc:
        # SQL and disk errors are operational information; no audio is deleted.
        from core.secret_guard import redact
        status["database_error"] = redact(str(exc) or type(exc).__name__)
    return status


def audio_response(data, mime, method, range_header=None, etag=None, if_range=None):
    size = len(data)
    headers = {"Accept-Ranges": "bytes", "Content-Type": mime,
               "Cache-Control": "private, no-store", "Content-Length": str(size)}
    if etag:
        headers["ETag"] = etag
    start, end, status = 0, size - 1, 200
    # HEAD describes the full GET representation; RFC Range applies to GET only.
    if method == "GET" and range_header and (not if_range or if_range == etag):
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip()) if len(range_header) < 128 else None
        if match and any(match.groups()):
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                suffix = int(last)
                start = max(0, size - suffix)
            if start >= size or start > end or (not first and int(last) == 0):
                return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}", "Content-Length": "0"})
            status = 206
            headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
        # Malformed / multiple ranges are ignored: send the complete representation.
    return Response(content=b"" if method == "HEAD" else data[start:end+1], status_code=status, headers=headers)


@router.get("")
async def list_archives(limit: int = 50, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    rows = await db_manager.fetch("""
        SELECT id, log_id, provider, requested_model, resolved_model, created_at,
               codec, container, mime_type, duration_seconds, channels, sample_rate,
               source_sample_rate, source_channels, source_format, source_size_bytes,
               archive_size_bytes, generation_status
        FROM router_tts_audio_archives ORDER BY created_at DESC, id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    return {"archives": [dict(row) for row in rows], "total": await db_manager.fetchval("SELECT count(*) FROM router_tts_audio_archives")}


@router.api_route("/{archive_id}/audio", methods=["GET", "HEAD"])
async def get_archive_audio(archive_id: int, request: Request):
    row = await db_manager.fetchrow("SELECT audio, mime_type FROM router_tts_audio_archives WHERE id=$1", archive_id)
    if not row:
        raise HTTPException(404, "Audio archive not found")
    return audio_response(bytes(row["audio"]), row["mime_type"], request.method,
        request.headers.get("range"), f'"tts-{archive_id}"', request.headers.get("if-range"))
