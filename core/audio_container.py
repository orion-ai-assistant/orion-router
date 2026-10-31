"""Audio container helpers: finalize a buffered streaming WAVE and name what a speech stream carries."""
import struct

PCM_STREAM_HEADERS = {
    "Content-Disposition": 'inline; filename="speech.pcm"',
    "X-Audio-Sample-Rate": "24000",
    "X-Audio-Channels": "1",
    "X-Audio-Bits-Per-Sample": "16",
}


def _is_mpeg_frame(data: bytes) -> bool:
    """A believable MPEG audio frame header: sync bits plus valid version, layer, bitrate and sample-rate fields."""
    if len(data) < 4 or data[0] != 0xFF or (data[1] & 0xE0) != 0xE0:
        return False
    version, layer = (data[1] >> 3) & 3, (data[1] >> 1) & 3
    bitrate, rate = (data[2] >> 4) & 15, (data[2] >> 2) & 3
    return version != 1 and layer != 0 and bitrate not in (0, 15) and rate != 3


def stream_media(first_chunk: bytes | None, requested_format: str | None) -> tuple[str, dict[str, str]]:
    """Media type and headers of a streamed speech response.

    Raw PCM has no signature, and its first sample can look like an MP3 frame header (a small negative
    sample such as FF FF). A caller that asked for PCM therefore gets PCM unless the stream really starts with
    a WAVE header; the byte check only decides when the caller did not say what it wants.
    """
    chunk = first_chunk or b""
    if chunk[:4] == b"RIFF" and len(chunk) >= 12 and chunk[8:12] == b"WAVE":
        return "audio/wav", {"Content-Disposition": 'inline; filename="speech.wav"'}
    if str(requested_format or "").lower() not in ("pcm", "s16le") and (chunk[:3] == b"ID3" or _is_mpeg_frame(chunk)):
        return "audio/mpeg", {"Content-Disposition": 'inline; filename="speech.mp3"'}
    return "audio/pcm", dict(PCM_STREAM_HEADERS)


def finalize_buffered_wav(audio: bytes) -> bytes:
    if len(audio) < 12 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE':
        return audio
    offset = 12
    while offset + 8 <= len(audio):
        kind = audio[offset:offset + 4]
        size = struct.unpack_from('<I', audio, offset + 4)[0]
        start = offset + 8
        if kind == b'data':
            # A streaming writer cannot know the final length when it emits its
            # header. HTTPX has already buffered the whole response at this point.
            # Only repair the standard unknown-length sentinel, never guess the
            # end of a truncated, ordinary data chunk or re-encode its samples.
            if size == 0xFFFFFFFF:
                updated = bytearray(audio)
                struct.pack_into('<I', updated, offset + 4, len(audio) - start)
                struct.pack_into('<I', updated, 4, len(audio) - 8)
                return bytes(updated)
            if size <= len(audio) - start and struct.unpack_from('<I', audio, 4)[0] == 0xFFFFFFFF:
                updated = bytearray(audio)
                struct.pack_into('<I', updated, 4, len(audio) - 8)
                return bytes(updated)
            return audio
        if size > len(audio) - start:
            return audio
        offset = start + size + (size & 1)
    return audio
