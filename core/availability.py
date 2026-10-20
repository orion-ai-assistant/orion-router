"""Optional local services (speech-to-text, text-to-speech, ...) that may simply not be running.

Their absence is a state, not a fault: it is logged once when it begins and once when it ends, at INFO,
never as an ERROR for every request. Nothing is cached as "down": every request tries the service again, so
it is used as soon as it starts.
"""
import logging
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


class ServiceUnavailable(HTTPException):
    """503 for an optional local service that is not running: an expected state, logged by unavailable()."""

    def __init__(self, service: str, detail: str, cause: BaseException | None = None, retry_after: int = 5):
        super().__init__(503, detail, headers={"Retry-After": str(retry_after)})
        self.service = service
        unavailable(service, cause)
