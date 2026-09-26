"""Local, silent-video frame extraction for chat adapters."""

import asyncio
import base64
import binascii
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from core.config import FFMPEG_DIR

MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_FRAMES = 32
MAX_EDGE = 768
VIDEO_TYPES = {"input_video", "video_url"}
# Only self-contained video containers; do not let uploaded playlists read files/URLs.
DEMUXERS = "mov,matroska,webm,avi,mpeg,mpegts,flv,ogg"


async def _run(tool: str, *args: str) -> bytes:
    binary = tool + ".exe" if os.name == "nt" else tool
    executable = str(Path(FFMPEG_DIR) / binary) if FFMPEG_DIR else binary
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
    try:
        process = await asyncio.create_subprocess_exec(
            executable, *args, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, **options,
        )
    except FileNotFoundError as exc:
        raise ValueError("Video requires local ffmpeg and ffprobe. Install FFmpeg or set FFMPEG_DIR.") from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        raise ValueError(f"Video processing failed ({tool}): {stderr.decode(errors='replace')[-800:]}")
    return stdout


def _video_bytes(part: dict) -> bytes:
    media = part.get(part["type"])
    if not isinstance(media, dict):
        raise ValueError("Video content requires an object with base64 data.")
    encoded = media.get("data") or media.get("url")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Video requires base64 data or a video data URL.")
    if encoded.startswith("data:"):
        header, separator, encoded = encoded.partition(",")
        if not separator or not header.startswith("data:video/") or not header.endswith(";base64"):
            raise ValueError("Expected a base64 video data URL.")
    elif "url" in media and not media.get("data"):
        raise ValueError("Upload the video as base64; remote URLs and local paths are not read by the video adapter.")
    if len(encoded) > 4 * ((MAX_VIDEO_BYTES + 2) // 3):
        raise ValueError("Video exceeds the 100 MiB local processing limit.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid video base64 data.") from exc
    if not data or len(data) > MAX_VIDEO_BYTES:
        raise ValueError("Video must contain between 1 byte and 100 MiB.")
    return data


def _sample_times(duration: float) -> list[float]:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video has no valid duration.")
    interval = max(1.0, duration / MAX_FRAMES)
    return [i * interval for i in range(min(MAX_FRAMES, math.ceil(duration / interval)))]


async def _frames(part: dict) -> list[dict]:
    data = _video_bytes(part)
    with tempfile.TemporaryDirectory(prefix="orion-video-") as folder:
        source = Path(folder) / "input.video"
        source.write_bytes(data)
        del data
        input_options = ("-protocol_whitelist", "file,pipe", "-format_whitelist", DEMUXERS)
        probe = await _run(
            "ffprobe", "-v", "error", *input_options, "-select_streams", "v:0",
            "-show_entries", "stream=codec_type,duration:format=duration", "-of", "json", str(source),
        )
        metadata = json.loads(probe)
        streams = metadata.get("streams", [])
        if not streams:
            raise ValueError("The attachment has no video stream.")
        raw_duration = streams[0].get("duration")
        if not raw_duration or raw_duration == "N/A":
            raw_duration = metadata.get("format", {}).get("duration")
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError) as exc:
            raise ValueError("Cannot determine the video duration.") from exc
        times = _sample_times(duration)
        parts = [{"type": "text", "text": (
            f"[Video: {duration:.2f}s; {len(times)} sampled frames in time order. "
            "Visual content only; audio was not processed.]"
        )}]
        for index, timestamp in enumerate(times):
            frame = Path(folder) / f"frame-{index}.jpg"
            await _run(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *input_options,
                "-ss", f"{timestamp:.6f}", "-i", str(source), "-map", "0:v:0", "-an",
                "-frames:v", "1", "-vf",
                f"scale=w='min({MAX_EDGE},iw)':h='min({MAX_EDGE},ih)':force_original_aspect_ratio=decrease",
                "-q:v", "3", "-y", str(frame),
            )
            if not frame.exists() or not frame.stat().st_size:
                raise ValueError(f"Cannot decode video frame near {timestamp:.2f}s.")
            parts.append({"type": "text", "text": f"[Video frame near {timestamp:.2f}s]"})
            parts.append({"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode("ascii"),
            }})
        parts.append({"type": "text", "text": "[End of video]"})
        return parts


async def prepare_video_frames(messages: list[dict]) -> list[dict]:
    """Expand videos in place in content order, without mutating stored history."""
    prepared = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list) or not any(p.get("type") in VIDEO_TYPES for p in content):
            prepared.append(message)
            continue
        expanded = []
        for part in content:
            if part.get("type") in VIDEO_TYPES:
                expanded.extend(await _frames(part))
            else:
                expanded.append(part)
        prepared.append({**message, "content": expanded})
    return prepared


# Retain the existing import for the OpenAI adapter and its callers.
prepare_openai_videos = prepare_video_frames
