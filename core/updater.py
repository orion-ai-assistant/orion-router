"""Signed package update bridge. Never Git/pip/build or restart live work."""
import json
from pathlib import Path
from core.config import APP_VERSION
from core.installation_registry import Registry, operation_lock, _atomic_write
from core.installation_paths import canonical_path

ROOT = Path(__file__).resolve().parents[1]


def _installation():
    registry = Registry()
    record = registry.read()
    matches = [c for c in (record or {}).get('components', []) if c['kind'] == 'router'
               and c['distribution'] == 'packaged' and c['management'] == 'local'
               and c['ownership'] == 'owned' and Path(c['code_path']).resolve() == ROOT.resolve()]
    if len(matches) != 1:
        raise ValueError('Legacy/development installations require explicit package conversion')
    return registry, record, matches[0]


def _json(path, default=None):
    path = canonical_path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def get_update_status():
    try:
        registry, record, item = _installation()
        base = registry.path.parent
        manifest = _json(Path(item['code_path']) / 'orion-release.json', {})
        checked = _json(base / 'updates/router-automatic.json', {})
        policy = _json(base / 'updates/router-policy.json', {'enabled': False})
        pointer = _json(base / 'updates/active.json')
        tx = None
        if pointer:
            import uuid
            identity = str(uuid.UUID(pointer['operation_id']))
            if identity != pointer['operation_id'] or pointer['schema'] != 1:
                raise ValueError('Invalid update pointer')
            tx = _json(base / 'updates' / identity / 'journal.json')
            if not tx or tx['installation_id'] != record['installation_id']:
                raise ValueError('Invalid update journal')
        if tx and 'router' not in tx.get('changes', []):
            tx = None
        phase = tx['phase'] if tx else 'idle'
        pending = phase in {'staged', 'waiting_for_idle'}
        busy = phase in {'checking', 'downloading', 'verifying', 'draining', 'backing_up', 'switching', 'health_check', 'rollback_pending'}
        proposed = (tx or {}).get('proposed') or {}
        target = next((c for c in proposed.get('components', []) if c['kind'] == 'router'), None)
        latest = _json(Path(target['code_path']) / 'orion-release.json', {}) if target else {}
        configured = bool(_json(base / 'bootstrap/release-source.json', {}).get('targets', {}).get('router')
                          and _json(base / 'bootstrap/automatic-runtime.json'))
        return {'status': 'ready' if configured else 'check-unavailable',
                'current_version': manifest.get('version', APP_VERSION),
                'latest_version': latest.get('version'), 'update_available': pending,
                'last_checked': checked.get('last_success'), 'last_attempt': checked.get('last_attempt'),
                'automatic_updates': policy.get('enabled', False), 'phase': phase,
                'is_updating': busy, 'step': phase, 'progress': 100 if phase == 'completed' else 0,
                'success': phase == 'completed', 'error': checked.get('error') or
                (phase if phase in {'failed', 'repair_required', 'rolled_back'} else None),
                'logs': [], 'pending': pending,
                'message': 'Hazır sürüm sonraki güvenli açılışı bekliyor.' if pending else
                'İmzalı paket kaynağı ve ayrı yardımcı gerekir; legacy dönüşümü kendiliğinden yapılmaz.'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'check-unavailable', 'current_version': APP_VERSION,
                'latest_version': None, 'update_available': None, 'last_checked': None,
                'is_updating': False, 'step': 'unavailable', 'progress': 0,
                'success': False, 'logs': [], 'error': 'Package installation/update status unavailable'}


def check_for_updates(force=False):
    # The public version endpoint is read-only, including its historical force flag.
    return get_update_status()


def start_update():
    try:
        registry, record, item = _installation()
        feed = _json(registry.path.parent / 'bootstrap/release-source.json', {})
        if not feed.get('targets', {}).get('router') or not _json(registry.path.parent / 'bootstrap/automatic-runtime.json'):
            raise ValueError('Signed Router repository/runtime unavailable')
        with operation_lock(registry.path, timeout=0):
            if registry.read() != record:
                raise ValueError('Installation changed')
            path = canonical_path(registry.path.parent / 'updates/router-request.json')
            path.parent.mkdir(exist_ok=True)
            _atomic_write(path, json.dumps({'schema': 1, 'installation_id': record['installation_id'],
                                           'action': 'prepare'}).encode())
        return {'status': 'started', 'message': 'İmzalı kontrol/hazırlama sıraya alındı. Çalışan Router durdurulmaz; hazır sürüm sonraki güvenli açılışta uygulanır.'}
    except (OSError, ValueError, RuntimeError):
        return {'status': 'error', 'message': 'Kayıtlı paket kurulumu, imzalı Router kaynağı ve dış launcher gerekir. Yerinde Git/pip güncellemesi kapalıdır.'}
