"""Optional local services (speech-to-text, text-to-speech, ...) that may simply not be running.

Their absence is a state, not a fault: it is logged once when it begins and once when it ends, at INFO,
never as an ERROR for every request. Nothing is cached as "down": every request tries the service again, so
it is used as soon as it starts.
"""
import logging
import os
import threading

from fastapi import HTTPException

logger = logging.getLogger("service-router.availability")
_down = set()
_lock = threading.Lock()


def unavailable(service: str, cause: BaseException | None = None) -> None:
    with _lock:
        first = service not in _down
        _down.add(service)
    if first:
        reason = f"{type(cause).__name__}: {cause}" if cause is not None else "no answer"
        logger.info("%s is not available (%s); it is tried again with every request", service, reason)


def available(service: str) -> None:
    with _lock:
        was_down = service in _down
        _down.discard(service)
    if was_down:
        logger.info("%s is available again", service)


_LOOPBACK = {"127.0.0.1", "localhost", "0.0.0.0"}


def not_listening(host: str, port) -> bool:
    """True only when nothing listens on this PC's loopback `port` (a stopped optional service).

    On Windows a refused loopback connection is reported only after about 2 s (the SYN is retried, whatever the
    client's timeout): every voice/language listing waited that long while the local TTS service was off, and
    the Hub's model list took 2.3 s on every page load. The listener table answers in well under a millisecond,
    and nothing is cached: a service that starts is seen by the very next request. False whenever it cannot
    tell (another host, another OS, an error): the caller then simply tries the service."""
    if os.name != "nt" or str(host) not in _LOOPBACK:
        return False
    try:
        import ctypes
        import socket
        from ctypes import wintypes
        wanted = int(port)
        iphlp = ctypes.WinDLL("iphlpapi")
        size = wintypes.DWORD(0)
        # AF_INET, TCP_TABLE_BASIC_LISTENER: listening sockets only, no process lookup.
        iphlp.GetExtendedTcpTable(None, ctypes.byref(size), False, socket.AF_INET, 0, 0)
        buffer = ctypes.create_string_buffer(size.value + 64)
        size = wintypes.DWORD(len(buffer))
        if iphlp.GetExtendedTcpTable(buffer, ctypes.byref(size), False, socket.AF_INET, 0, 0) != 0:
            return False
        count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD))[0]
        rows = ctypes.cast(ctypes.addressof(buffer) + 4, ctypes.POINTER(wintypes.DWORD * 5))
        for index in range(count):
            state, _address, local_port, _remote, _remote_port = rows[index]
            if state == 2 and socket.ntohs(local_port & 0xFFFF) == wanted:  # MIB_TCP_STATE_LISTEN
                return False
        return True
    except Exception:
        return False


class ServiceUnavailable(HTTPException):
    """503 for an optional local service that is not running: an expected state, logged by unavailable()."""

    def __init__(self, service: str, detail: str, cause: BaseException | None = None, retry_after: int = 5):
        super().__init__(503, detail, headers={"Retry-After": str(retry_after)})
        self.service = service
        unavailable(service, cause)
