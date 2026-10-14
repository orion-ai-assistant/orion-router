"""Original video bytes, content-addressed in log copies. No transcoding."""
import asyncio
import base64
import hashlib
import json
import logging
import math
import os
import subprocess

from core.media_names import media_filename, label_filename
from core.tts_archive import binary
from core.video import MAX_VIDEO_BYTES, DEMUXERS

logger = logging.getLogger('service-router.video-archive')
_active_jobs = 0
MAX_VIDEO_JOBS = 2


def video_fields(node):
    if node.get('type') in ('input_video', 'video_url', 'video'):
        for key in ('input_video', 'video_url', 'video'):
            media = node.get(key)
            if isinstance(media, dict):
                yield media, 'data' if 'data' in media else 'url'
            elif isinstance(media, str):
                yield node, key
    if str(node.get('mime_type', node.get('mimeType', node.get('media_type', '')))).lower().startswith('video/') and node.get('isText') is not True:
        yield node, 'data'
    if 'video_base64' in node:
        yield node, 'video_base64'


def decode_video(value):
    if len(value) > (MAX_VIDEO_BYTES + 2) // 3 * 4 + 1024:
        raise ValueError('Video archive safety ceiling exceeded')
    if value.startswith('data:'):
        header, separator, value = value.partition(',')
        if not separator or not header.lower().startswith('data:video/') or not header.lower().endswith(';base64'):
            raise ValueError('Expected a Base64 video data URL')
    value = ''.join(value.split())
    data = base64.b64decode(value + '=' * (-len(value) % 4), validate=True)
    if not data or len(data) > MAX_VIDEO_BYTES:
        raise ValueError('Empty or oversized video')
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    result = subprocess.run([binary('ffprobe'), '-v', 'error', '-protocol_whitelist', 'pipe',
        '-format_whitelist', DEMUXERS, '-i', 'pipe:0', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,codec_name,duration:format=format_name,duration',
        '-of', 'json'], input=data, capture_output=True, timeout=25, check=True, **options)
    info = json.loads(result.stdout)
    stream = info['streams'][0]
    width, height = int(stream['width']), int(stream['height'])
    if width <= 0 or height <= 0:
        raise ValueError('Video has no dimensions')
    container = info['format']['format_name']
    if 'mov' in container:
        fmt, mime = ('mov', 'video/quicktime') if data[8:12] == b'qt  ' else ('mp4', 'video/mp4')
    elif 'webm' in container:
        fmt, mime = ('webm', 'video/webm') if b'webm' in data[:4096] else ('mkv', 'video/x-matroska')
    else:
        fmt = container.split(',')[0]
        mime = {'avi': 'video/x-msvideo', 'mpegts': 'video/mp2t', 'ogg': 'video/ogg', 'flv': 'video/x-flv'}.get(fmt, 'video/mpeg')
    try:
        duration = float(stream.get('duration', info.get('format', {}).get('duration')))
        if not math.isfinite(duration) or duration < 0:
            duration = None
    except (TypeError, ValueError):
        duration = None
    return data, dict(sha256=hashlib.sha256(data).hexdigest(), mime_type=mime, format=fmt,
        size_bytes=len(data), width=width, height=height, duration_seconds=duration)


async def save_video(manager, data, metadata):
    pool = await manager.get_db_pool()
    async with pool.acquire() as conn:
        archive_id = await conn.fetchval('''INSERT INTO router_video_archives
            (sha256, video, mime_type, format, size_bytes, width, height, duration_seconds, filename)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (sha256) DO NOTHING RETURNING id''',
            metadata['sha256'], data, metadata['mime_type'], metadata['format'], metadata['size_bytes'],
            metadata['width'], metadata['height'], metadata['duration_seconds'], metadata.get('filename'))
        if archive_id is None:
            archive_id = await conn.fetchval('SELECT id FROM router_video_archives WHERE sha256=$1', metadata['sha256'])
        if archive_id is None:
            raise RuntimeError('Video archive conflict lookup returned no row')
        return {'video_archive_id': archive_id, **metadata}


async def archive_videos_json(value, manager):
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return value
    changed, visited, references = False, set(), {}

    async def replace(container, key, filename):
        nonlocal changed
        global _active_jobs
        location = (id(container), key)
        if location in visited or key not in container:
            return
        visited.add(location)
        raw = container[key]
        if not isinstance(raw, str) or raw.lower().startswith(('http://', 'https://')) or _active_jobs >= MAX_VIDEO_JOBS:
            return
        _active_jobs += 1
        try:
            data, metadata = await asyncio.to_thread(decode_video, raw)
            if filename:
                metadata['filename'] = filename
            reference = references.get(metadata['sha256'])
            if reference is None:
                reference = await save_video(manager, data, metadata)
                if len(references) < 256:
                    references[metadata['sha256']] = reference
            container[key] = {**{k: v for k, v in reference.items() if k != 'filename'}, **({'filename': filename} if filename else {})}
            changed = True
        except Exception as exc:
            logger.warning('Video archiving failed (%s); preserving inline video in log', type(exc).__name__)
        finally:
            _active_jobs -= 1

    async def walk(node, filename=None):
        if isinstance(node, dict):
            filename = media_filename(node) or filename
            for container, key in video_fields(node):
                await replace(container, key, media_filename(container) or filename)
            for child in node.values():
                if isinstance(child, (dict, list)):
                    await walk(child, filename)
        elif isinstance(node, list):
            pending = None
            for child in node:
                label = label_filename(child)
                await walk(child, label or pending or filename)
                pending = label
    try:
        await walk(payload)
        return json.dumps(payload, ensure_ascii=False) if changed else value
    except Exception as exc:
        logger.warning('Video log transformation failed (%s); preserving original log', type(exc).__name__)
        return value


async def archive_log_media_json(value, manager):
    from core.image_archive import archive_images_json
    return await archive_videos_json(await archive_images_json(value, manager), manager)
