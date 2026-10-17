"""Queue signed Router preparation; never mutate an active source checkout."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.updater import start_update, get_update_status


def main():
    result = get_update_status() if '--status' in sys.argv else start_update()
    print(json.dumps(result, ensure_ascii=True))
    return 1 if result.get('status') in {'error', 'check-unavailable'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
