"""Independent Router compatibility APIs must not kill foreign listeners."""
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin import common
from core.process_lifecycle import LifecycleError


def test_port_cleanup_is_diagnostic_and_preserves_foreign_listener():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        with patch.object(common, 'run') as command:
            with pytest.raises(LifecycleError, match='Port conflict'):
                common.free_ports([port], Path('unused'), 'prod')
            command.assert_not_called()
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            pass


def test_compatibility_lock_preserves_legacy_marker(tmp_path):
    marker = tmp_path / '.orion.prod.lock'
    marker.write_text('legacy marker is not authority')
    with patch.object(common, 'ROOT', tmp_path):
        assert common.acquire_lock('.orion.prod.lock')
        common.release_lock('.orion.prod.lock')
    assert marker.read_text() == 'legacy marker is not authority'


def test_pid_only_router_shutdown_is_refused(tmp_path):
    marker = tmp_path / '.orion.pid'
    marker.write_text('12345')
    with patch.object(common, 'ROOT', tmp_path), patch.object(common, 'run') as command:
        with pytest.raises(LifecycleError, match='PID-only'):
            common.kill_orion_pid()
        command.assert_not_called()
    assert marker.read_text() == '12345'


def test_native_launcher_start_uses_same_readiness_contract():
    from core import lifecycle_cli
    with patch.object(lifecycle_cli, 'ensure_started', return_value=True) as start:
        lifecycle_cli.main(['start'])
        start.assert_called_once_with(lifecycle_cli.ROOT, 'router-prod',
            [sys.executable, str(lifecycle_cli.ROOT / 'cli.py'), 'prod'])


def test_native_launcher_propagates_start_failure():
    from core import lifecycle_cli
    with patch.object(lifecycle_cli, 'ensure_started', side_effect=LifecycleError('not ready')):
        with pytest.raises(LifecycleError, match='not ready'):
            lifecycle_cli.main(['start'])
