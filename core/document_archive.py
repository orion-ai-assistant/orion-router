"""Content-addressed document attachments in independent CHAT log copies."""
import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import re

from core.media_names import clean_filename, media_filename

logger = logging.getLogger('service-router.document-archive')
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_JOBS = 4
_active_jobs = 0
TEXT_ATTACHMENT = re.compile(r'\A(?:Ek|Attachment)\s+\d+\s*[—–-]\s*(?:Metin dosyası|Text file|Not|Note)\s*:\s*(?P<name>[^\r\n]+)\r?\n<file_content>(?P<separator>\r?\n)(?P<content>[\s\S]*)(?P=separator)</file_content>\Z', re.IGNORECASE)


def text_attachment(value):
    match = TEXT_ATTACHMENT.fullmatch(value) if isinstance(value, str) else None
    return (clean_filename(match['name']), match['content']) if match else None


def document_mime(value):
    return isinstance(value, str) and value.lower().startswith(('text/', 'application/'))


def document_fields(node):
    name = media_filename(node)
    declared_mime = node.get('mime_type',node.get('mimeType'))
    if node.get('type') == 'text' and text_attachment(node.get('text')):
        yield node, 'text', 'wrapped', None, None
    if node.get('isText') is True and isinstance(node.get('data'), str) and (not declared_mime or document_mime(declared_mime)):
        yield node, 'data', 'text', node.get('mime_type', node.get('mimeType', 'text/plain')), name
    elif document_mime(node.get('mime_type', node.get('mimeType', node.get('media_type')))):
        yield node, 'data', 'base64', node.get('mime_type', node.get('mimeType', node.get('media_type'))), name
    for key in ('file', 'input_file'):
        file = node.get(key)
        if isinstance(file, dict):
            yield file, 'file_data' if 'file_data' in file else 'data', 'base64', file.get('mime_type'), media_filename(file) or name
    if node.get('type') in ('file', 'input_file') or ('file_data' in node and name):
        yield node, 'file_data', 'base64', node.get('mime_type'), name
    if node.get('type') == 'document' and isinstance(node.get('source'), dict):
        source = node['source']
        if source.get('type') == 'base64':
            yield source, 'data', 'base64', source.get('media_type'), media_filename(source) or name
    for key in ('inline_data', 'inlineData'):
        inline = node.get(key)
        if isinstance(inline, dict):
            mime = inline.get('mime_type', inline.get('mimeType'))
            if document_mime(mime):
                yield inline, 'data', 'base64', mime, media_filename(inline) or name


def decode_document(value, encoding, mime=None, filename=None):
    if encoding == 'wrapped':
        filename, value = text_attachment(value)
        encoding = 'text'
    if encoding == 'text':
        if len(value) > MAX_DOCUMENT_BYTES:
            raise ValueError('Document safety ceiling exceeded')
        data = value.encode('utf-8')
        guessed = mimetypes.guess_type(filename or '')[0]
        mime = mime if document_mime(mime) and mime != 'application/pdf' else guessed
        if not mime or not mime.startswith('text/') and mime not in ('application/json','application/xml'):
            mime = 'text/plain'
        representation = 'text'
    else:
        if encoding == 'binary':
            data = value
        else:
            if len(value) > (MAX_DOCUMENT_BYTES + 2) // 3 * 4 + 1024:
                raise ValueError('Document safety ceiling exceeded')
            if value.startswith('data:'):
                header, separator, value = value.partition(',')
                if not separator or not header.lower().endswith(';base64'):
                    raise ValueError('Expected a Base64 document data URL')
                mime = header[5:].split(';',1)[0].lower()
            value = ''.join(value.split())
            data = base64.b64decode(value + '=' * (-len(value) % 4), validate=True)
        mime = mime or mimetypes.guess_type(filename or '')[0] or 'application/octet-stream'
        if data.lstrip().startswith(b'%PDF-'):
            mime = 'application/pdf'
        elif mime == 'application/pdf':
            raise ValueError('PDF header missing')
        representation = 'binary'
    if len(data) > MAX_DOCUMENT_BYTES or not document_mime(mime):
        raise ValueError('Unsupported or oversized document')
    mime = mime.split(';',1)[0].lower()
    if not re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+', mime):
        raise ValueError('Invalid document MIME')
    fmt = (mimetypes.guess_extension(mime) or '.bin').lstrip('.')
    fmt = {'text/plain':'txt', 'text/markdown':'md', 'application/json':'json'}.get(mime,fmt)
    return data, dict(sha256=hashlib.sha256(data).hexdigest(), mime_type=mime, format=fmt,
        size_bytes=len(data), representation=representation, **({'filename':filename} if filename else {}))


async def save_document(manager, data, metadata):
    pool = await manager.get_db_pool()
    async with pool.acquire() as conn:
        archive_id = await conn.fetchval('''INSERT INTO router_document_archives
            (sha256, document, mime_type, format, size_bytes, filename, representation)
            VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (sha256) DO NOTHING RETURNING id''',
            metadata['sha256'], data, metadata['mime_type'], metadata['format'], metadata['size_bytes'],
            metadata.get('filename'), metadata['representation'])
        if archive_id is None:
            archive_id = await conn.fetchval('SELECT id FROM router_document_archives WHERE sha256=$1',metadata['sha256'])
        if archive_id is None:
            raise RuntimeError('Document archive conflict lookup returned no row')
        return {'document_archive_id':archive_id, **metadata}


async def archive_documents_json(value, manager):
    try:
        payload = json.loads(value)
    except (TypeError,ValueError):
        return value
    changed, visited, references = False, set(), {}

    async def walk(node):
        nonlocal changed
        global _active_jobs
        if isinstance(node, dict):
            for container, key, encoding, mime, filename in document_fields(node):
                location = (id(container),key)
                raw = container.get(key)
                if location in visited or not isinstance(raw,str) or _active_jobs >= MAX_DOCUMENT_JOBS:
                    continue
                visited.add(location)
                if encoding == 'base64' and raw.lower().startswith(('http://','https://')):
                    continue
                _active_jobs += 1
                try:
                    data, metadata = await asyncio.to_thread(decode_document,raw,encoding,mime,filename)
                    reference = references.get(metadata['sha256'])
                    if reference is None:
                        reference = await save_document(manager,data,metadata)
                        if len(references) < 256:
                            references[metadata['sha256']] = reference
                    container[key] = {**{key: value for key,value in reference.items() if key != 'filename'}, **metadata}
                    changed = True
                except Exception as exc:
                    logger.warning('Document archiving failed (%s); preserving inline attachment',type(exc).__name__)
                finally:
                    _active_jobs -= 1
            for child in node.values():
                if isinstance(child,(dict,list)):
                    await walk(child)
        elif isinstance(node,list):
            for child in node:
                await walk(child)
    try:
        await walk(payload)
        return json.dumps(payload,ensure_ascii=False) if changed else value
    except Exception as exc:
        logger.warning('Document log transformation failed (%s); preserving original log',type(exc).__name__)
        return value


async def archive_uploaded_document(data, mime, filename, manager):
    """Best effort for original PDFs/text sent through the multipart upload API."""
    global _active_jobs
    if not document_mime(mime) or len(data) > MAX_DOCUMENT_BYTES or _active_jobs >= MAX_DOCUMENT_JOBS:
        return
    _active_jobs += 1
    try:
        # This path receives original binary bytes; do not interpret them as text.
        original, metadata = await asyncio.to_thread(decode_document,data,'binary',mime,clean_filename(filename))
        await save_document(manager,original,metadata)
    except Exception as exc:
        logger.warning('Uploaded document archiving failed (%s); provider result preserved',type(exc).__name__)
    finally:
        _active_jobs -= 1
