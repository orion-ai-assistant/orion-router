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


def router_feed_configured(source):
    """True when the installation's release source lists a Router target.

    The source is one feed (schema 1: `targets`) or several (schema 2: `sources[].targets`, e.g. the
    Router's own feed beside the Hub/Client feed). Works for a Router-only install and a Hub-managed one."""
    if not isinstance(source, dict):
        return False
    feeds = source.get('sources') if source.get('schema') == 2 else [source]
    if not isinstance(feeds, list):
        return False
    return any(isinstance(feed, dict) and isinstance(feed.get('targets'), dict) and feed['targets'].get('router')
               for feed in feeds or [])


OUTCOMES = {
    'up_to_date': 'Router güncel; yeni sürüm yok.',
    'update_found': 'Yeni sürüm bulundu; hazırlanıyor. Hazır olunca {apply}',
    'pending': 'Başka bir güncelleme zaten hazır veya sürüyor; {apply} Yeni denetim, o bitince yapılır.',
    'disabled': 'Otomatik güncellemeler kapalı olduğu için denetlenmedi.',
    'paused': 'Ağ kullanımı duraklatıldığı için denetlenmedi.',
    'no_source': 'Bu kurulumda güncelleme kaynağı yapılandırılmamış.',
    'bootstrap_updated': 'Güncelleme yardımcısı yenilendi; birkaç saniye içinde yeniden denetlenecek.',
}
NAMES = {'hub': 'Hub', 'client': 'Arayüz', 'router': 'Router', 'bootstrap': 'Güncelleyici'}


def _names(kinds):
    return ', '.join(NAMES.get(kind, str(kind)) for kind in kinds)


def _apply_hint(hub_present):
    """How a prepared update gets installed: the Hub's settings card has "Şimdi kur"; a Router-only install has no
    such card, so it waits for the next safe start."""
    if hub_present:
        return 'Orion ayarlarındaki "Şimdi kur" veya sonraki güvenli açılış kurar.'
    return "Router'ın sonraki güvenli açılışında kurulur."


ERRORS = {
    'URLError': 'Güncelleme sunucusuna ulaşılamadı. İnternet bağlantısını kontrol edip yeniden denetleyin.',
    'UpdateError': 'Güncelleme hazırlanamadı (imza, uyumluluk veya bekleyen işlem denetimi). Yeniden denetleyebilirsiniz.',
    'MigrationError': 'Orion süreçleri güncelleme sırasında hâlâ çalışıyordu; güncelleme uygulanmadı. Yeniden denetleyebilirsiniz.',
    'failed': 'Önceki güncelleme başarısız oldu; yeniden denetleyebilirsiniz.',
    'rolled_back': 'Yeni sürüm çalışmadı, önceki sürüme dönüldü; yeniden denetleyebilirsiniz.',
    'repair_required': 'Güncelleme yarıda kaldı; yerel onarma gerekli.',
}


def _outcome_message(outcome, hub_present, found, waiting, version):
    text = OUTCOMES.get(outcome)
    if text is None:
        return None
    apply = _apply_hint(hub_present)
    if outcome == 'update_found' and found:
        text = text.replace('Yeni sürüm bulundu;', 'Yeni sürüm bulundu: %s;' % _names(found))
    if outcome == 'pending' and waiting:
        text = text.replace('Başka bir güncelleme', 'Başka bir güncelleme (%s)' % _names(waiting))
        text += ' Router (v%s) bu güncellemede değişmiyor.' % version
    return text.replace('{apply}', apply)


def _latest_check(base):
    """Router and Hub schedulers both check the Router now; report whichever ran last."""
    states = [_json(base / 'updates' / name, {}) or {} for name in ('router-automatic.json', 'automatic.json')]
    return max(states, key=lambda state: state.get('outcome_at') or state.get('last_attempt') or 0)


def _release_sources(base):
    """Every feed the retained updater uses. `release-sources.json` (all feeds) is written next to the legacy
    one-feed `release-source.json`, which stays Hub-only so that older Hubs can still read it."""
    for name in ('release-sources.json', 'release-source.json'):
        try:
            value = _json(base / 'bootstrap' / name)
        except (OSError, ValueError):
            continue
        if value and router_feed_configured(value):
            return value
    return {}


def get_update_status():
    try:
        registry, record, item = _installation()
        base = registry.path.parent
        manifest = _json(Path(item['code_path']) / 'orion-release.json', {})
        checked = _latest_check(base)
        router_state = _json(base / 'updates/router-automatic.json', {})
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
        other = [kind for kind in (tx or {}).get('changes', []) if kind != 'router']
        waiting = (tx or {}).get('phase') in {'staged', 'waiting_for_idle'}
        if tx and 'router' not in tx.get('changes', []):
            tx = None
        hub_present = any(c.get('kind') == 'hub' for c in record['components'])
        found = [kind for kind in ((checked.get('newer') or {}).get('components') or {})]
        phase = tx['phase'] if tx else 'idle'
        pending = phase in {'staged', 'waiting_for_idle'}
        busy = phase in {'checking', 'downloading', 'verifying', 'draining', 'backing_up', 'switching', 'health_check', 'rollback_pending'}
        proposed = (tx or {}).get('proposed') or {}
        target = next((c for c in proposed.get('components', []) if c['kind'] == 'router'), None)
        latest = _json(Path(target['code_path']) / 'orion-release.json', {}) if target else {}
        # A check clears `outcome` when it starts and writes it when it ends: in between it is running.
        checking = (checked.get('outcome') is None and not checked.get('error')
                    and (checked.get('last_attempt') or 0) > (checked.get('outcome_at') or 0))
        configured = bool(router_feed_configured(_release_sources(base))
                          and _json(base / 'bootstrap/automatic-runtime.json'))
        return {'status': 'ready' if configured else 'check-unavailable',
                'current_version': manifest.get('version', APP_VERSION),
                'latest_version': latest.get('version'), 'update_available': pending,
                'last_checked': max(checked.get('last_success') or 0, router_state.get('last_success') or 0) or None,
                'last_attempt': checked.get('last_attempt'),
                'automatic_updates': policy.get('enabled', False), 'phase': phase,
                'is_updating': busy, 'step': phase, 'progress': 100 if phase == 'completed' else 0,
                'success': phase == 'completed', 'error': checked.get('error') or
                (phase if phase in {'failed', 'repair_required', 'rolled_back'} else None),
                'logs': [], 'pending': pending,
                'check_outcome': checked.get('outcome'), 'checking': checking,
                'message': 'Hazır sürüm sonraki güvenli açılışı bekliyor.' if pending else
                'Güncellemeler denetleniyor…' if checking else
                ERRORS.get(checked.get('error') or (phase if phase in ERRORS else None)) or
                _outcome_message(checked.get('outcome'), hub_present, found if checked.get('outcome') == 'update_found' else [],
                                 other if waiting else [], manifest.get('version', APP_VERSION)) or
                ('Henüz denetim yapılmadı. "Güncellemeleri Denetle" ile denetleyin.' if configured else
                 'İmzalı paket kaynağı ve ayrı yardımcı gerekir; legacy dönüşümü kendiliğinden yapılmaz.')}
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
        feed = _release_sources(registry.path.parent)
        if not router_feed_configured(feed) or not _json(registry.path.parent / 'bootstrap/automatic-runtime.json'):
            raise ValueError('Signed Router repository/runtime unavailable')
        from core.process_lifecycle import LifecycleError
        try:
            lock = operation_lock(registry.path, timeout=0)
            lock.__enter__()
        except LifecycleError:
            # A check, download or update already holds the lock: that is the requested work, not an error.
            return {'status': 'busy', 'message': 'Bir denetim ya da güncelleme zaten sürüyor; sonucu birazdan burada görünür.'}
        try:
            if registry.read() != record:
                raise ValueError('Installation changed')
            path = canonical_path(registry.path.parent / 'updates/router-request.json')
            path.parent.mkdir(exist_ok=True)
            _atomic_write(path, json.dumps({'schema': 1, 'installation_id': record['installation_id'],
                                           'action': 'prepare'}).encode())
        finally:
            lock.__exit__(None, None, None)
        return {'status': 'started', 'message': 'İmzalı kontrol/hazırlama sıraya alındı. Çalışan Router durdurulmaz; hazır sürüm sonraki güvenli açılışta uygulanır.'}
    except (OSError, ValueError, RuntimeError):
        return {'status': 'error', 'message': 'Kayıtlı paket kurulumu, imzalı Router kaynağı ve dış launcher gerekir. Yerinde Git/pip güncellemesi kapalıdır.'}
