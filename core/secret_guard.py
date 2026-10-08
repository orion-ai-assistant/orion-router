"""Prevent request credentials from appearing in upstream echoes or diagnostics."""
import logging
import traceback
import json
from contextvars import ContextVar
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

_secrets = ContextVar('request_secrets', default=())


def remember(value):
    if value and isinstance(value, str) and value not in _secrets.get():
        _secrets.set((*_secrets.get(), value))


def redact(value):
    if isinstance(value, str):
        for secret in sorted(_secrets.get(), key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if k.lower() in ('api_key','authorization','x-admin-key','x-orion-api-key','x-orion-hub-key') else redact(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def redact_json(value):
    if value is None:
        return None
    try:
        return json.dumps(redact(json.loads(value)), ensure_ascii=False)
    except (ValueError, TypeError):
        return redact(value)


_factory = logging.getLogRecordFactory()


def _safe_record(*args, **kwargs):
    record = _factory(*args, **kwargs)
    if (record.name == 'uvicorn' or record.name.startswith('uvicorn.')) and isinstance(record.args, tuple):
        # AccessFormatter unpacks HTTP fields; DefaultFormatter also needs the
        # args for Uvicorn's color_message template (added after this factory).
        # Mask each field without collapsing the record to text.
        record.msg = redact(record.msg)
        record.args = tuple(redact(value) for value in record.args)
    else:
        record.msg = redact(record.getMessage())
        record.args = ()
    if record.exc_info:
        record.exc_text = redact(''.join(traceback.format_exception(*record.exc_info)))
        record.exc_info = None
    return record


logging.setLogRecordFactory(_safe_record)


class SecretRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                return JSONResponse(status_code=422, content={'detail': [
                    {k:e[k] for k in ('loc','msg','type') if k in e} for e in error.errors()]})
        return safe_handler
