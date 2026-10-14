"""Finish Windows Proactor cleanup after a peer resets a closing socket.

CPython issue: https://github.com/python/cpython/issues/83191
"""
from functools import wraps
import linecache
import sys


def _reset_safe_connection_lost(original):
    @wraps(original)
    def connection_lost(transport, exc):
        try:
            return original(transport, exc)
        except ConnectionResetError as error:
            trace = error.__traceback__
            while trace is not None and trace.tb_frame.f_code is not original.__code__:
                trace = trace.tb_next
            # Only handle a reset in the transport's own cleanup. Errors in
            # protocol.connection_lost must retain their normal traceback.
            if (getattr(error, 'winerror', None) != 10054
                    or trace is None
                    or linecache.getline(original.__code__.co_filename, trace.tb_lineno).strip()
                       != 'self._sock.shutdown(socket.SHUT_RDWR)'
                    or error.__context__ is not None):
                raise
            # shutdown() failed before CPython could close/detach the socket.
            # Do not call connection_lost a second time or merely hide the log.
            transport._sock.close()
            transport._sock = None
            if transport._server is not None:
                transport._server._detach()
                transport._server = None
            transport._called_connection_lost = True
    return connection_lost


def install_reset_cleanup():
    if sys.platform != 'win32':
        return
    from asyncio.proactor_events import _ProactorBasePipeTransport
    current = _ProactorBasePipeTransport._call_connection_lost
    if not getattr(current, '_orion_reset_cleanup', False):
        replacement = _reset_safe_connection_lost(current)
        replacement._orion_reset_cleanup = True
        _ProactorBasePipeTransport._call_connection_lost = replacement
