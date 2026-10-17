"""The native launcher uses the same verified runtime as Hub/installer callers."""
from pathlib import Path
import sys

from core.process_lifecycle import ensure_started

ROOT = Path(__file__).resolve().parents[1]


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments == ['start']:
        from core.runtime_layout import component
        installed = component(ROOT)
        if installed:
            from core.release_packages import verify_registered_package
            verify_registered_package(ROOT)
            if installed['ownership'] != 'owned' or installed['management'] != 'local':
                raise RuntimeError('Packaged local management is not authorized')
        ensure_started(ROOT, 'router-prod', [sys.executable, str(ROOT / 'cli.py'), 'prod'])
        print('Router identity and readiness verified.')
    elif arguments == ['stop']:
        from bin.stop import main as stop
        stop()
    else:
        raise SystemExit('Usage: python -m core.lifecycle_cli start|stop')


if __name__ == '__main__':
    main()
