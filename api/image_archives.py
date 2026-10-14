"""Admin-only original image bytes, independent of request log deletion."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from core.dependencies import verify_admin
from database import db_manager

router = APIRouter(prefix="/dashboard/api/image-archives", dependencies=[Depends(verify_admin)], tags=["Dashboard"])


@router.get("")
async def list_images(limit: int = 50, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    rows = await db_manager.fetch("""SELECT id, sha256, mime_type, format, size_bytes, width, height, created_at
        FROM router_image_archives ORDER BY id DESC LIMIT $1 OFFSET $2""", limit, offset)
    totals = await db_manager.fetchrow("SELECT count(*) AS total, COALESCE(sum(size_bytes),0)::bigint AS total_bytes FROM router_image_archives")
    return {"images": [dict(row) for row in rows], **dict(totals)}


@router.api_route("/{archive_id}/image", methods=["GET", "HEAD"])
async def get_image(archive_id: int, request: Request):
    if request.method == "HEAD":
        row = await db_manager.fetchrow("SELECT mime_type, size_bytes FROM router_image_archives WHERE id=$1", archive_id)
    else:
        row = await db_manager.fetchrow("SELECT image, mime_type, size_bytes FROM router_image_archives WHERE id=$1", archive_id)
    if not row:
        raise HTTPException(404, "Image archive not found")
    return Response(content=b"" if request.method == "HEAD" else bytes(row["image"]), headers={
        "Content-Type": row["mime_type"], "Content-Length": str(row["size_bytes"]),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })
