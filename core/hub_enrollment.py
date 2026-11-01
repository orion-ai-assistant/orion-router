"""How a Hub earns its first Router credential. The administrator password never leaves the Router.

- Same PC: the Router keeps a random token beside its identity file. Only the local user can read it,
  and it is accepted only from a loopback peer.
- Another PC: the administrator creates a short, single-use code in the dashboard. The one code does
  both jobs: the Router first proves its TLS identity with it (pairing_proofs), so the Hub learns the
  fingerprint without anyone typing it, then the Hub sends the code to enroll over that pinned channel.
"""
import hashlib
import hmac
import ipaddress
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request

CODE_LIFETIME = timedelta(minutes=10)
# No 0/O/1/I/L: the code is read from one screen and typed into another.
_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
_CODE_LENGTH = 12


def local_token_path() -> Path:
    from core import config
    return config.MDNS_ID_FILE.parent / 'hub-enrollment-token'


def ensure_local_token() -> None:
    path = local_token_path()
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        os.chmod(temporary, 0o600)
        file.write(secrets.token_urlsafe(48).encode('ascii'))
        file.flush()
        os.fsync(file.fileno())
    try:
        os.link(temporary, path)  # Never replace a token another start already published.
    except FileExistsError:
        pass
    finally:
        temporary.unlink(missing_ok=True)


def _local_token_matches(token: str) -> bool:
    try:
        expected = local_token_path().read_text(encoding='ascii').strip()
    except OSError:
        return False
    return len(expected) >= 32 and hmac.compare_digest(token.encode(), expected.encode())


def _normalize(code: str) -> str:
    return ''.join(character for character in code.upper() if character.isalnum())


def _digest(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode()).hexdigest()


async def create_code() -> dict:
    from database import db_manager
    raw = ''.join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    expires = datetime.now(timezone.utc) + CODE_LIFETIME
    await db_manager.execute('DELETE FROM router_hub_enrollment_codes WHERE expires_at < NOW() OR used_at IS NOT NULL')
    await db_manager.execute('INSERT INTO router_hub_enrollment_codes(code_hash, expires_at) VALUES ($1,$2)',
                             _digest(raw), expires)
    return {'code': '-'.join(raw[i:i + 4] for i in range(0, _CODE_LENGTH, 4)), 'expires_at': expires.isoformat()}


PROOF_CONTEXT = 'orion-hub-pairing-v1'


async def pairing_proofs(router_id: str, fingerprint: str, nonce: str) -> list[str]:
    """One HMAC per active code over this Router's identity; which one the Hub holds is never revealed."""
    from database import db_manager
    rows = await db_manager.fetch(
        'SELECT code_hash FROM router_hub_enrollment_codes WHERE used_at IS NULL AND expires_at > NOW()')
    message = '|'.join((PROOF_CONTEXT, router_id, fingerprint, nonce)).encode()
    return [hmac.new(bytes.fromhex(row['code_hash']), message, hashlib.sha256).hexdigest() for row in rows]


async def _consume_code(code: str) -> bool:
    from database import db_manager
    if len(_normalize(code)) != _CODE_LENGTH:
        return False
    used = await db_manager.fetchval(
        'UPDATE router_hub_enrollment_codes SET used_at=NOW() '
        'WHERE code_hash=$1 AND used_at IS NULL AND expires_at > NOW() RETURNING 1', _digest(code))
    return bool(used)


async def authorize_enrollment(request: Request) -> None:
    """A FastAPI dependency for the Hub enrollment endpoint."""
    token = request.headers.get('x-orion-local-enrollment')
    if token is not None:
        try:
            loopback = ipaddress.ip_address(request.client.host).is_loopback
        except (AttributeError, ValueError):
            loopback = False
        if loopback and _local_token_matches(token):
            return
        raise HTTPException(401, 'local_enrollment_rejected')
    code = request.headers.get('x-orion-enrollment-code')
    if code is not None and await _consume_code(code):
        return
    raise HTTPException(401, 'enrollment_code_invalid')
