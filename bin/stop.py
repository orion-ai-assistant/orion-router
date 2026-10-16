"""Stop only this Router installation through its verified supervisor."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.process_lifecycle import Runtime, LifecycleError, stop_component
from bin.common import database


def main():
    found = False
    for mode in ('prod', 'dev'):
        component = 'router-' + mode
        record = Runtime(ROOT, component).read()
        if record:
            stop_component(ROOT, component)
            database(ROOT / ('.pgdata-' + mode)).stop()
            found = True
    if not found:
        raise LifecycleError('No verified Router ownership record; stop legacy Router manually')
    print('Router children and databases verified stopped.')


if __name__ == '__main__':
    main()
