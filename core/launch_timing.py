"""`launch.timing step=… seconds=…` lines (the Hub's format, updates/watcher.log) in the Router's own logs:
the supervisor's in supervisor.log, the backend's in its log. Where a slow Router start spent its time."""
from contextlib import contextmanager
import os
import time


def process_age():
    """Seconds since this process was created: interpreter start and imports included."""
    import psutil
    return time.time() - psutil.Process(os.getpid()).create_time()


def report(step, seconds):
    print(f'launch.timing step={step} seconds={seconds:.2f}', flush=True)


@contextmanager
def timed(step):
    started = time.monotonic()
    try:
        yield
    finally:
        report(step, time.monotonic() - started)
