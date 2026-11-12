"""The Router stays up for weeks: a crashed service is started again, and its supervisor does not rewrite its
state file every second."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def backoff_class():
    sys.argv = ['prod.py']
    with patch('core.runtime_layout.data_root', return_value=ROOT), \
            patch('bin.common.read_env', return_value='5433'):
        import bin.prod as prod
    return prod.CrashBackoff


def test_crashes_are_retried_with_growing_delays_and_never_given_up():
    clock = Clock()
    backoff = backoff_class()(clock=clock)
    delays = []
    for _ in range(9):
        delays.append(backoff.crashed())
        backoff.started_now()
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60, 60]


def test_a_long_run_starts_the_delays_over():
    clock = Clock()
    backoff = backoff_class()(clock=clock)
    for _ in range(5):
        backoff.crashed()
    backoff.started_now()
    clock.now += 600
    assert backoff.crashed() == 1


def test_state_is_saved_only_when_children_change():
    from core import process_lifecycle
    runtime = process_lifecycle.Runtime.__new__(process_lifecycle.Runtime)
    runtime.children = {'backend': {'job': {'name': 'j'}, 'process': {'pid': 1}}}
    records = [[{'pid': 2, 'started': 1.0}]]
    job = Mock()
    job.__enter__ = Mock(return_value=job)
    job.__exit__ = Mock(return_value=False)
    job.records.side_effect = lambda: records[0]
    adapter = Mock()
    adapter.Job.return_value = job
    runtime.save = Mock()
    with patch.object(process_lifecycle, 'job_adapter', return_value=adapter):
        for _ in range(3):
            runtime.refresh_children()
        assert runtime.save.call_count == 1
        records[0] = [{'pid': 2, 'started': 1.0}, {'pid': 3, 'started': 2.0}]
        runtime.refresh_children()
    assert runtime.save.call_count == 2
