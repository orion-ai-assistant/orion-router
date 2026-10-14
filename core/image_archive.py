"""Lossless, content-addressed images for chat logs only.

Call on serialized log copies, never on the provider's live request objects.
Any failed image stays inline, so archiving cannot discard the original log.
"""
import asyncio
import base64
import hashlib
import io
import json
import logging
from core.media_names import media_filename, label_filename

logger = logging.getLogger("service-router.image-archive")
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_JOBS = 4
_active_jobs = 0


def image_fields(node):
    """Yield image payload locations only; never interpret arbitrary text as Base64."""
    if not isinstance(node, dict):
        return
    kind = node.get("type")
    image_url = node.get("image_url")
    if kind in ("image_url", "input_image"):
        if "url" in node:
            yield node, "url"
        if isinstance(image_url, dict):
            yield image_url, "url"
        elif isinstance(image_url, str):
            yield node, "image_url"
        image = node.get("input_image")
        if isinstance(image, dict):
            yield image, "data"
    if kind == "image" and isinstance(node.get("source"), dict):
        source = node["source"]
        if source.get("type") == "base64":
            yield source, "data"
    for key in ("inline_data", "inlineData"):
        inline = node.get(key)
        if isinstance(inline, dict) and str(inline.get("mime_type", inline.get("mimeType", ""))).lower().startswith("image/"):
            yield inline, "data"
    # Hub/legacy clients may include image arrays or attachment metadata in the log.
    if isinstance(node.get("images"), list):
        for index in range(len(node["images"])):
            yield node["images"], index
    if (str(node.get("mime_type", node.get("mimeType", ""))).lower().startswith("image/")
            and node.get("isText") is not True):
        yield node, "data"
    for key in ("b64_json", "image_base64"):
        if key in node:
            yield node, key


def _decode_image(value):
    from PIL import Image
    if len(value) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 1024:
        raise ValueError("Image archive safety ceiling exceeded")
    if value.startswith("data:"):
        header, separator, value = value.partition(",")
        if not separator or not header.lower().startswith("data:image/") or not header.lower().endswith(";base64"):
            raise ValueError("Expected a Base64 image data URL")
    # Standard MIME Base64 can contain whitespace; missing final padding is accepted.
    value = "".join(value.split())
    data = base64.b64decode(value + "=" * (-len(value) % 4), validate=True)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Empty or oversized image")
    # Header inspection only. No load(), resize(), save() or re-encoding.
    with Image.open(io.BytesIO(data), formats=("JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "ICO", "AVIF")) as image:
        width, height = image.size
        mime = Image.MIME.get(image.format)
        fmt = image.format.lower()
    if not mime or width <= 0 or height <= 0:
        raise ValueError("Image header has no valid format/dimensions")
    return data, {"sha256": hashlib.sha256(data).hexdigest(), "mime_type": mime, "format": fmt,
                  "size_bytes": len(data), "width": width, "height": height}


async def save_image(manager, data, metadata):
    pool = await manager.get_db_pool()
    async with pool.acquire() as conn:
        # Keep conflict handling and lookup as separate statements: a concurrently
        # inserted winner becomes visible to the second READ COMMITTED snapshot.
        archive_id = await conn.fetchval("""
            INSERT INTO router_image_archives (sha256, image, mime_type, format, size_bytes, width, height, filename)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (sha256) DO NOTHING RETURNING id
            """, metadata["sha256"], data, metadata["mime_type"], metadata["format"],
            metadata["size_bytes"], metadata["width"], metadata["height"], metadata.get("filename"))
        if archive_id is None:
            archive_id = await conn.fetchval("SELECT id FROM router_image_archives WHERE sha256=$1", metadata["sha256"])
        if archive_id is None:
            raise RuntimeError("Image archive conflict lookup returned no row")
        return {"image_archive_id": archive_id, **metadata}


async def archive_images_json(value, manager):
    """Best-effort transformation of an independent serialized log snapshot."""
    if value is None:
        return value
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return value
    changed = False
    # Only successful references are cached, with bounded keys (never Base64 strings).
    references = {}
    visited = set()

    async def replace(container, key, filename=None):
        nonlocal changed
        global _active_jobs
        location = (id(container), key)
        if location in visited:
            return
        visited.add(location)
        raw = container.get(key) if isinstance(container, dict) else container[key]
        if not isinstance(raw, str) or raw.startswith(("http://", "https://")):
            return
        if _active_jobs >= MAX_IMAGE_JOBS:
            logger.warning("Image archive busy; preserving inline image in request log")
            return
        _active_jobs += 1
        try:
            data, metadata = await asyncio.to_thread(_decode_image, raw)
            if filename:
                metadata["filename"] = filename
            digest = metadata["sha256"]
            reference = references.get(digest)
            if reference is None:
                reference = await save_image(manager, data, metadata)
                if len(references) < 256:
                    references[digest] = reference
            container[key] = {**{k: v for k, v in reference.items() if k != "filename"}, **({"filename": filename} if filename else {})}
            changed = True
        except Exception as exc:
            # Do not include the payload, SQL arguments, or DB exception text (it may
            # contain binary data). The original Base64 stays exactly where it was.
            logger.warning("Image archiving failed (%s); preserving inline image in request log", type(exc).__name__)
        finally:
            _active_jobs -= 1

    async def walk(node, filename=None):
        if isinstance(node, dict):
            filename = media_filename(node) or filename
            for container, key in image_fields(node):
                if not isinstance(container, dict) or key in container:
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
        logger.warning("Image log transformation failed (%s); preserving original log", type(exc).__name__)
        return value
