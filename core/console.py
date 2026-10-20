"""UTF-8 text and ANSI colours on a Windows console, set through the console API.

`os.system("chcp 65001")` and `os.system("")` did the same by starting a cmd.exe: one more process on every
start and stop (the supervisor, its backend and `cli.py stop` each paid for it). Without a console (the
installed Router runs with its output in a log file) there is nothing to set.
"""
import sys

ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
STD_HANDLES = (-11, -12)  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE


def _kernel():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return kernel


def enable_ansi():
    """What `os.system("")` left behind: escape sequences interpreted by the console (colours)."""
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    kernel = _kernel()
    for number in STD_HANDLES:
        handle = kernel.GetStdHandle(number)
        mode = wintypes.DWORD()
        if handle and kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)


def utf8_console(*, line_buffering=None):
    """What `chcp 65001` set (the console's code pages, shared with child processes), ANSI colours, and UTF-8
    standard streams (`line_buffering=None` keeps the streams' buffering)."""
    if sys.platform != 'win32':
        return
    kernel = _kernel()
    kernel.SetConsoleOutputCP(65001)
    kernel.SetConsoleCP(65001)
    enable_ansi()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace', line_buffering=line_buffering)
        except Exception:
            pass
