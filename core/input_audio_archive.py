"""Original audio bytes sent TO a chat provider, content-addressed in log copies (one row per sha256, no transcoding).

Separate from the TTS archive, which holds audio the Router generated. Covers OpenAI/OpenRouter/DeepSeek
`input_audio {data, format}` and any node declaring an audio/* MIME type (Gemini inlineData, generic parts).
"""
import asyncio
import base64
import hashlib
import json
import logging

from core.media_names import media_filename, label_filename

logger = logging.getLogger('service-router.input-audio-archive')
MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_AUDIO_JOBS = 4
_active_jobs = 0
FORMAT_MIME = {'wav': 'audio/wav', 'mp3': 'audio/mpeg', 'mpeg': 'audio/mpeg', 'ogg': 'audio/ogg', 'flac': 'audio/flac',
               'aac': 'audio/aac', 'm4a': 'audio/mp4', 'mp4': 'audio/mp4', 'webm': 'audio/webm', 'opus': 'audio/opus',
               'aiff': 'audio/aiff', 'pcm': 'audio/pcm'}


def audio_fields(node):
    """Yield (container, key, mime) locations of audio payloads; never interpret arbitrary text as Base64."""
    if node.get('type') == 'input_audio' and isinstance(node.get('input_audio'), dict):
        media = node['input_audio']
        fmt = str(media.get('format', '')).lower()
        yield media, 'data', fmt if fmt.startswith('audio/') else FORMAT_MIME.get(fmt)
    mime = node.get('mime_type', node.get('mimeType', node.get('media_type')))
    # Gemini inlineData is itself a node with mimeType + data, so it is reached when the walk descends.
    if isinstance(mime, str) and mime.lower().startswith('audio/') and node.get('isText') is not True:
        yield node, 'data', mime.lower()


def decode_audio(value, mime=None):
    if len(value) > (MAX_AUDIO_BYTES + 2) // 3 * 4 + 1024:
        raise ValueError('Audio archive safety ceiling exceeded')
    if value.startswith('data:'):
        header, separator, value = value.partition(',')
        if not separator or not header.lower().startswith('data:audio/') or not header.lower().endswith(';base64'):
            raise ValueError('Expected a Base64 audio data URL')
        mime = header[5:].split(';', 1)[0].lower()
    value = ''.join(value.split())
    # The Gemini SDK sends URL-safe Base64 (- and _): normalise to the standard alphabet.
    value = value.replace('-', '+').replace('_', '/')
    data = base64.b64decode(value + '=' * (-len(value) % 4), validate=True)
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise ValueError('Empty or oversized audio')
    if not mime:
        raise ValueError('Audio MIME type unknown')
    mime = mime.split(';', 1)[0]
    return data, dict(sha256=hashlib.sha256(data).hexdigest(), mime_type=mime, format=mime.split('/', 1)[1],
                      size_bytes=len(data))


async def save_input_audio(manager, data, metadata):
    pool = await manager.get_db_pool()
    async with pool.acquire() as conn:
        archive_id = await conn.fetchval('''INSERT INTO router_input_audio_archives
            (sha256, audio, mime_type, format, size_bytes, filename) VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (sha256) DO NOTHING RETURNING id''',
            metadata['sha256'], data, metadata['mime_type'], metadata['format'], metadata['size_bytes'], metadata.get('filename'))
        if archive_id is None:
            archive_id = await conn.fetchval('SELECT id FROM router_input_audio_archives WHERE sha256=$1', metadata['sha256'])
        if archive_id is None:
            raise RuntimeError('Input audio archive conflict lookup returned no row')
        return {'input_audio_archive_id': archive_id, **metadata}


async def archive_input_audio_json(value, manager):
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return value
    changed, visited, references = False, set(), {}

    async def replace(container, key, mime, filename):
        nonlocal changed
        global _active_jobs
        location = (id(container), key)
        if location in visited or key not in container:
            return
        visited.add(location)
        raw = container[key]
        if not isinstance(raw, str) or raw.lower().startswith(('http://', 'https://')) or _active_jobs >= MAX_AUDIO_JOBS:
            return
        _active_jobs += 1
        try:
            data, metadata = await asyncio.to_thread(decode_audio, raw, mime)
            if filename:
                metadata['filename'] = filename
            reference = references.get(metadata['sha256'])
            if reference is None:
                reference = await save_input_audio(manager, data, metadata)
                if len(references) < 256:
                    references[metadata['sha256']] = reference
            container[key] = {**{k: v for k, v in reference.items() if k != 'filename'}, **({'filename': filename} if filename else {})}
            changed = True
        except Exception as exc:
            logger.warning('Input audio archiving failed (%s); preserving inline audio in log', type(exc).__name__)
        finally:
            _active_jobs -= 1

    async def walk(node, filename=None):
        if isinstance(node, dict):
            filename = media_filename(node) or filename
            for container, key, mime in audio_fields(node):
                await replace(container, key, mime, media_filename(container) or filename)
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
        logger.warning('Input audio log transformation failed (%s); preserving original log', type(exc).__name__)
        return value
