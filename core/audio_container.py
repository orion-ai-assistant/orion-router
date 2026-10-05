"""Finalize the container lengths of a completely buffered streaming WAVE."""
import struct


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
