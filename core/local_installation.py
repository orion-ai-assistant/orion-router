"""Installer-owned local public identity locator, never a network trust source."""
import json
import os
import sys
import tempfile
from pathlib import Path

KIND = 'orion-router-local-installation'


def locator_path() -> Path:
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise RuntimeError('LOCALAPPDATA is required for local installation registration')
        return Path(local) / 'Orion' / 'router-installation.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'orion' / 'router-installation.json'


def native_default_root() -> Path:
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise RuntimeError('LOCALAPPDATA is required')
        return Path(local) / 'OrionRouter'
    return Path.home() / '.orion-router'


def register(root: Path, identity, identity_path: Path, port: int, *, destination: Path | None = None):
    """Explicit native installer registration. Does not expose private key paths."""
    root = root.resolve(strict=True)
    certificate = identity.certificate_path.resolve(strict=True)
    uuid_file = identity_path.resolve(strict=True)
    # A managed installation can bootstrap only identity files inside its root.
    certificate.relative_to(root)
    uuid_file.relative_to(root)
    if not 1 <= port <= 65535:
        raise ValueError('Invalid Router TLS port')
    payload = {'v': 1, 'kind': KIND, 'root': str(root), 'certificate_path': str(certificate),
               'identity_path': str(uuid_file), 'tls_port': port}
    destination = destination or locator_path()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        temporary = Path(file.name)
        os.chmod(temporary, 0o600)
        file.write((json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8'))
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def refresh_managed_installation(root: Path, identity, identity_path: Path, port: int,
                                 *, destination: Path | None = None) -> bool:
    """Startup refresh for an explicitly registered root or the native default only."""
    destination = destination or locator_path()
    root = root.resolve(strict=True)
    if destination.exists():
        record = json.loads(destination.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or not isinstance(record.get('root'), str):
            raise ValueError('Invalid local Router registration')
        if record.get('v') != 1 or record.get('kind') != KIND or Path(record.get('root', '')).resolve() != root:
            return False
    elif root != native_default_root().resolve():
        return False
    register(root, identity, identity_path, port, destination=destination)
    return True


if __name__ == '__main__':
    if sys.argv[1:] != ['register']:
        raise SystemExit('Usage: python -m core.local_installation register')
    from core import config
    from core.mdns import router_id
    from core.tls_identity import load_identity
    identity = load_identity(config.TLS_DIRECTORY, router_id(config.MDNS_ID_FILE))
    register(config._ROOT, identity, config.MDNS_ID_FILE, config.TLS_PORT)
    print('Registered local Router public identity locator:', locator_path())
