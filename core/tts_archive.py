"""Bounded, best-effort TTS archives. Never put encoder backpressure on speech.

Only finished, decoded audio is inserted. No temporary files or crash recovery.
"""
import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading

from database import db_manager
from core.secret_guard import redact

logger = logging.getLogger("service-router.tts-archive")
MAX_ENCODERS = 4
MAX_QUEUE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_active = set()
_background = set()
_runtime = {"available": None, "version": None, "error": None}
_last_error = None
_error_count = 0


def background(coro):
    """Keep finalization alive after the response and drain it on clean shutdown."""
    task = asyncio.create_task(coro)
    _background.add(task)
    def done(completed):
        _background.discard(completed)
        if not completed.cancelled() and completed.exception():
            logger.error("TTS archive finalization failed: %s", redact(str(completed.exception())))
    task.add_done_callback(done)
    return task


async def close_archives():
    if _background:
        await asyncio.gather(*list(_background), return_exceptions=True)
    # Requests normally finalize themselves; wake abandoned sessions on clean shutdown.
    for session in list(_active):
        session.fail("Router shutting down before archive finalization")
    await asyncio.gather(*(session.task for session in list(_active) if session.task), return_exceptions=True)
    _active.clear()


def runtime_status():
    return {**_runtime, "active_encoders": len(_active), "encoder_limit": MAX_ENCODERS,
            "errors_since_start": _error_count, "last_error": _last_error}


def binary(name):
    configured = os.getenv(f"ORION_{name.upper()}")
    bundled = Path(__file__).resolve().parents[1] / "tools" / "ffmpeg" / "bin" / (name + (".exe" if os.name == "nt" else ""))
    return configured or (str(bundled) if bundled.is_file() else shutil.which(name) or name)


def _check_runtime():
    """Native installation/startup check, also usable without a database."""
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    version = subprocess.run([binary("ffmpeg"), "-version"], capture_output=True, text=True, timeout=15, check=True, **flags).stdout.splitlines()[0]
    encoders = subprocess.run([binary("ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, check=True, **flags).stdout
    if "libopus" not in encoders:
        raise RuntimeError("FFmpeg was built without libopus")
    subprocess.run([binary("ffprobe"), "-version"], capture_output=True, timeout=15, check=True, **flags)
    return version


def check_runtime():
    try:
        version = _check_runtime()
        _runtime.update(available=True, version=version, error=None)
        return version
    except Exception as exc:
        _runtime.update(available=False, version=None, error=redact(str(exc) or type(exc).__name__))
        raise


async def _spawn(*args):
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    return await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **flags)


async def _read_limited(stream, limit):
    result = bytearray()
    while chunk := await stream.read(65536):
        if len(result) + len(chunk) > limit:
            raise RuntimeError("Archive buffer safety ceiling exceeded")
        result.extend(chunk)
    return bytes(result)


async def _command(data, *args):
    proc = await _spawn(*args)
    async def write():
        try:
            for offset in range(0, len(data), 65536):
                proc.stdin.write(data[offset:offset + 65536])
                await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            # ffprobe may exit successfully once it has read enough stream headers.
            pass
        finally:
            proc.stdin.close()
            try:
                await proc.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
    tasks = [asyncio.create_task(write()), asyncio.create_task(_read_limited(proc.stdout, 256 * 1024)),
             asyncio.create_task(_read_limited(proc.stderr, 64 * 1024))]
    try:
        _, out, err = await asyncio.wait_for(asyncio.gather(*tasks), 300)
        await asyncio.wait_for(proc.wait(), 15)
        if proc.returncode:
            raise RuntimeError(err.decode(errors="replace")[-2000:] or "Audio validation failed")
        return out
    finally:
        for task in tasks:
            task.cancel()
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        await asyncio.gather(*tasks, return_exceptions=True)


async def inspect_audio(data):
    info = json.loads(await _command(data, binary("ffprobe"), "-v", "error", "-protocol_whitelist", "pipe",
        "-i", "pipe:0", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate,channels:format=format_name", "-of", "json"))
    stream = info["streams"][0]
    codec = stream["codec_name"]
    container = info["format"]["format_name"]
    if container == "ogg":
        mime = f"audio/ogg; codecs={codec}" if codec in ("opus", "vorbis") else "audio/ogg"
    else:
        mime = {"mp3": "audio/mpeg", "aac": "audio/aac", "flac": "audio/flac"}.get(container, "audio/mp4" if "mp4" in container else "application/octet-stream")
    # Decode all packets; progress reports the actual playable duration even for pipes.
    progress = await _command(data, binary("ffmpeg"), "-hide_banner", "-v", "error", "-xerror",
        "-protocol_whitelist", "pipe", "-i", "pipe:0", "-map", "0:a:0", "-progress", "pipe:1", "-f", "null", "-")
    times = [int(line.split(b"=", 1)[1]) for line in progress.splitlines() if line.startswith(b"out_time_us=") and line.split(b"=", 1)[1].lstrip(b"-").isdigit()]
    duration = max(times, default=0) / 1_000_000
    if duration <= 0:
        raise RuntimeError("Archive has no playable audio")
    return {"codec": codec, "container": container, "mime_type": mime, "duration_seconds": duration,
            "sample_rate": int(stream["sample_rate"]), "channels": int(stream["channels"])}


def _wav_header(data):
    """Return PCM format and data offset, or None until header is complete."""
    if len(data) < 12:
        return None
    if data[8:12] != b"WAVE":
        raise RuntimeError("Invalid WAV header")
    offset, fmt = 12, None
    while offset + 8 <= len(data):
        tag, size = data[offset:offset+4], struct.unpack_from("<I", data, offset+4)[0]
        if tag == b"data":
            if not fmt:
                raise RuntimeError("WAV has no PCM format")
            return fmt, offset + 8, None if size in (0, 0xffffffff) else size
        if offset + 8 + size > len(data):
            return None
        if tag == b"fmt ":
            if size < 16:
                raise RuntimeError("Invalid WAV format")
            encoding, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", data, offset+8)
            if encoding == 0xFFFE and size >= 40:
                encoding = struct.unpack_from("<H", data, offset+32)[0]
            formats = {(1, 8): "u8", (1, 16): "s16le", (1, 24): "s24le", (1, 32): "s32le", (3, 32): "f32le", (3, 64): "f64le"}
            if (encoding, bits) not in formats or not channels or not rate:
                raise RuntimeError("Unsupported WAV PCM format")
            fmt = {"format": formats[encoding, bits], "sample_rate": rate, "channels": channels, "sample_width": bits // 8}
        offset += 8 + size + (size & 1)
    return None


class ArchiveSession:
    def __init__(self):
        self.created_at = datetime.now(timezone.utc)
        self.metadata = {}
        self.queue = deque()
        self.queued_bytes = 0
        self.source_size = 0
        self.wake = threading.Event()
        self.queue_lock = threading.Lock()
        self.closed = False
        self.error = None
        self.generation_status = "completed"
        self.task = None
        if len(_active) >= MAX_ENCODERS:
            self.fail("Archive encoder concurrency limit reached")
        else:
            _active.add(self)
            # Windows process creation can block even inside create_subprocess_exec.
            # Keep the encoder's event loop off the live speech event loop.
            self.task = asyncio.create_task(asyncio.to_thread(self._encode))

    def _encode(self):
        return asyncio.run(self._run())

    def set_metadata(self, metadata):
        if self.metadata and self.metadata != metadata:
            self.fail("Source audio format changed during streaming")
        self.metadata = dict(metadata)

    def fail(self, error):
        global _error_count, _last_error
        if not self.error:
            self.error = redact(str(error) or type(error).__name__)
            _error_count += 1
            _last_error = self.error
            logger.error("TTS archive failed: %s", self.error)
        with self.queue_lock:
            self.queue.clear()
            self.queued_bytes = 0
        self.wake.set()

    def feed(self, chunk):
        self.source_size += len(chunk)
        if self.error or self.closed:
            return
        if not chunk:
            return
        with self.queue_lock:
            overflow = self.queued_bytes + len(chunk) > MAX_QUEUE_BYTES or len(self.queue) >= 4096
            if not overflow:
                self.queue.append(chunk)
                self.queued_bytes += len(chunk)
        if overflow:
            self.fail("Archive input queue safety ceiling exceeded (encoder too slow)")
            return
        self.wake.set()

    async def _chunks(self):
        while True:
            if self.error:
                raise RuntimeError(self.error)
            with self.queue_lock:
                chunk = self.queue.popleft() if self.queue else None
                if chunk is not None:
                    self.queued_bytes -= len(chunk)
                else:
                    self.wake.clear()
            if chunk is not None:
                yield chunk
            elif self.closed:
                return
            else:
                await asyncio.to_thread(self.wake.wait)

    async def _run(self):
        proc, readers = None, []
        try:
            prefix = bytearray()
            output = bytearray()
            mode = None
            source = None
            pcm_bytes = 0
            pcm_tail = b""
            wav_remaining = None
            async for chunk in self._chunks():
                if mode is None:
                    prefix.extend(chunk)
                    if len(prefix) < 12:
                        continue
                    if prefix.startswith(b"RIFF"):
                        header = _wav_header(prefix)
                        if header is None:
                            if len(prefix) > 65536:
                                raise RuntimeError("WAV header safety ceiling exceeded")
                            continue
                        source, offset, wav_remaining = header
                        chunk = bytes(prefix[offset:])
                        mode = "pcm"
                    elif self.metadata.get("format"):
                        source = dict(self.metadata)
                        chunk = bytes(prefix)
                        mode = "pcm"
                    else:
                        # Unknown raw data must never be guessed to be 24kHz PCM.
                        if not (prefix.startswith((b"ID3", b"OggS", b"fLaC")) or prefix[0] == 0xFF or prefix[4:8] == b"ftyp"):
                            raise RuntimeError("Unknown audio format; provider PCM metadata required")
                        chunk = bytes(prefix)
                        mode = "copy"
                    prefix.clear()
                    if mode == "pcm":
                        if source.get("format") not in ("u8", "s16le", "s24le", "s32le", "f32le", "f64le") or not source.get("sample_rate") or not source.get("channels"):
                            raise RuntimeError("Incomplete provider PCM metadata")
                        proc = await _spawn(binary("ffmpeg"), "-hide_banner", "-v", "error", "-f", source["format"],
                            "-ar", str(source["sample_rate"]), "-ac", str(source["channels"]), "-i", "pipe:0",
                            "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1")
                        readers = [asyncio.create_task(_read_limited(proc.stdout, MAX_ARCHIVE_BYTES)), asyncio.create_task(_read_limited(proc.stderr, 64 * 1024))]
                if mode == "copy":
                    if len(output) + len(chunk) > MAX_ARCHIVE_BYTES:
                        raise RuntimeError("Archive buffer safety ceiling exceeded")
                    output.extend(chunk)
                else:
                    for reader in readers:
                        if reader.done() and reader.exception():
                            raise reader.exception()
                    if wav_remaining is not None:
                        chunk = chunk[:wav_remaining]
                        wav_remaining -= len(chunk)
                    frame_size = source["channels"] * source["sample_width"]
                    chunk = pcm_tail + chunk
                    aligned = len(chunk) - len(chunk) % frame_size
                    pcm_tail = chunk[aligned:]
                    chunk = chunk[:aligned]
                    pcm_bytes += len(chunk)
                    proc.stdin.write(chunk)
                    await asyncio.wait_for(proc.stdin.drain(), 15)
            if mode is None:
                # A failed/cancelled provider attempt may never produce audio.
                # Its generation error belongs to the request, not the archive.
                if self.source_size == 0 and self.generation_status != "completed":
                    return None
                raise RuntimeError("No complete audio header or audio payload")
            if self.generation_status == "completed" and (pcm_tail or wav_remaining):
                raise RuntimeError("Incomplete WAV payload or PCM frame")
            if proc:
                proc.stdin.close()
                encoded, err = await asyncio.wait_for(asyncio.gather(*readers), 60)
                await asyncio.wait_for(proc.wait(), 15)
                if proc.returncode:
                    raise RuntimeError(err.decode(errors="replace")[-2000:])
                output = encoded
            data = bytes(output)
            info = await inspect_audio(data)
            if source:
                expected = pcm_bytes / (source["sample_rate"] * source["channels"] * source["sample_width"])
                if pcm_bytes % (source["channels"] * source["sample_width"]) or abs(info["duration_seconds"] - expected) > 0.1:
                    raise RuntimeError("Archive/source duration or PCM alignment mismatch")
            info.update({"source_sample_rate": source["sample_rate"] if source else info["sample_rate"],
                         "source_channels": source["channels"] if source else info["channels"],
                         "source_format": source["format"] if source else info["codec"],
                         "source_size_bytes": self.source_size, "archive_size_bytes": len(data)})
            return data, info
        except Exception as exc:
            self.fail(exc)
            return None
        finally:
            if proc:
                proc.stdin.close()
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            if proc:
                try:
                    await asyncio.wait_for(proc.stdin.wait_closed(), 5)
                except (OSError, ConnectionError, asyncio.TimeoutError):
                    pass
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)

    async def finish(self, *, log_id, provider, requested_model, resolved_model, text, status):
        self.generation_status = status
        self.closed = True
        self.wake.set()
        try:
            result = await asyncio.shield(self.task) if self.task else None
            if not result:
                if self.source_size == 0 and status != "completed" and not self.error:
                    return {}
                return {"archive_error": self.error or "Audio archive unavailable"}
            data, info = result
            archive_id = await save_archive(data, info, log_id=log_id, provider=provider,
                requested_model=requested_model, resolved_model=resolved_model, text=text, status=status, created_at=self.created_at)
            return {"audio_archive_id": archive_id, "audio_archive": info}
        except asyncio.CancelledError:
            self.fail("Archive finalization cancelled")
            if self.task:
                self.task.add_done_callback(lambda _: _active.discard(self))
            raise
        except Exception as exc:
            self.fail(exc)
            return {"archive_error": self.error}
        finally:
            if not self.task or self.task.done():
                _active.discard(self)


async def save_archive(data, info, *, log_id, provider, requested_model, resolved_model, text, status, created_at):
    pool = await db_manager.get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serialize with log deletion; preserve archives even if deletion won the race.
            linked_id = await conn.fetchval("SELECT id FROM router_request_logs WHERE id=$1 FOR KEY SHARE", log_id) if log_id is not None else None
            return await conn.fetchval("""
                INSERT INTO router_tts_audio_archives
                (log_id, audio, provider, requested_model, resolved_model, created_at,
                 codec, container, mime_type, duration_seconds, channels, sample_rate,
                 source_sample_rate, source_channels, source_format, source_size_bytes, archive_size_bytes, generation_status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18) RETURNING id
                """, linked_id, data, provider, requested_model, resolved_model, created_at,
                info["codec"], info["container"], info["mime_type"], info["duration_seconds"], info["channels"], info["sample_rate"],
                info["source_sample_rate"], info["source_channels"], info["source_format"], info["source_size_bytes"], info["archive_size_bytes"], status)
