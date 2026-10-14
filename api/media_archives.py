"""Admin media library. Explicit deletion affects every log using the file."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.tts_archives import audio_response
from core.dependencies import verify_admin
from database import db_manager

router = APIRouter(prefix='/dashboard/api/media-archives', dependencies=[Depends(verify_admin)], tags=['Dashboard'])
video_router = APIRouter(prefix='/dashboard/api/video-archives', dependencies=[Depends(verify_admin)], tags=['Dashboard'])
MediaKind = Literal['image', 'audio', 'video']
TABLES = {'image': ('router_image_archives', 'image', 'size_bytes'),
          'audio': ('router_tts_audio_archives', 'audio', 'archive_size_bytes'),
          'video': ('router_video_archives', 'video', 'size_bytes')}


@router.get('/{kind}')
async def list_media(kind: MediaKind, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                     start: datetime | None = None, end: datetime | None = None):
    if any(value is not None and value.tzinfo is None for value in (start, end)):
        raise HTTPException(422, 'Dates must include a timezone')
    if start and end and end <= start:
        raise HTTPException(422, 'End must be after start')
    table, _, size = TABLES[kind]
    fields = ('id, created_at, mime_type, filename, format, size_bytes, width, height' if kind != 'audio'
              else 'id, created_at, mime_type, container AS format, archive_size_bytes AS size_bytes, duration_seconds')
    if kind == 'video':
        fields += ', duration_seconds'
    where = 'WHERE ($1::timestamptz IS NULL OR created_at >= $1) AND ($2::timestamptz IS NULL OR created_at < $2)'
    rows = await db_manager.fetch(f'SELECT {fields} FROM {table} {where} ORDER BY created_at DESC, id DESC LIMIT $3 OFFSET $4', start, end, limit, offset)
    totals = await db_manager.fetchrow(f'SELECT count(*) AS total, COALESCE(sum({size}),0)::bigint AS total_bytes FROM {table} {where}', start, end)
    return {'items': [dict(row) for row in rows], **dict(totals)}


@router.delete('/{kind}/{archive_id}')
async def delete_media(kind: MediaKind, archive_id: int):
    table = TABLES[kind][0]
    deleted = await db_manager.fetchval(f'DELETE FROM {table} WHERE id=$1 RETURNING id', archive_id)
    if deleted is None:
        raise HTTPException(404, 'Archived file not found')
    return {'deleted': True}


@video_router.api_route('/{archive_id}/video', methods=['GET', 'HEAD'])
async def get_video(archive_id: int, request: Request):
    if request.method == 'HEAD':
        row = await db_manager.fetchrow('SELECT mime_type, size_bytes FROM router_video_archives WHERE id=$1', archive_id)
        if not row:
            raise HTTPException(404, 'Video archive not found')
        from fastapi.responses import Response
        return Response(headers={'Content-Type': row['mime_type'], 'Content-Length': str(row['size_bytes']),
            'Accept-Ranges': 'bytes', 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    row = await db_manager.fetchrow('SELECT video, mime_type FROM router_video_archives WHERE id=$1', archive_id)
    if not row:
        raise HTTPException(404, 'Video archive not found')
    response = audio_response(bytes(row['video']), row['mime_type'], request.method,
        request.headers.get('range'), f'"video-{archive_id}"', request.headers.get('if-range'))
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
