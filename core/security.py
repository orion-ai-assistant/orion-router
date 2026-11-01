import asyncio
import hashlib
import hmac
import os
from cryptography.fernet import Fernet, InvalidToken

def hash_secret(secret: str, salt: bytes = b"orion-router-salt") -> str:
    """Hashes a secret using PBKDF2 HMAC SHA256."""
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        secret.encode('utf-8'),
        salt,
        100000
    )
    return hash_bytes.hex()

def verify_secret(secret: str, hashed_secret: str, salt: bytes = b"orion-router-salt") -> bool:
    """Verifies a secret against a stored hash."""
    return hmac.compare_digest(hash_secret(secret, salt), hashed_secret)

async def check_admin_secret(secret: str | None) -> bool:
    """Verifies an admin secret against the stored DB hash or fallback config."""
    if not secret:
        return False
    from database import db_manager
    from core import config
    try:
        hashed_db = await db_manager.get_config("admin_secret_hash")
        if hashed_db:
            # PBKDF2 takes ~25 ms: off the event loop, so guesses cannot stall other requests.
            return await asyncio.to_thread(verify_secret, secret, hashed_db)
    except Exception:
        pass
    return bool(config.ADMIN_SECRET and is_default_secret(secret))


def is_default_secret(secret: str) -> bool:
    from core import config
    return bool(config.ADMIN_SECRET) and hmac.compare_digest(secret.encode(), config.ADMIN_SECRET.encode())


def remote_default_secret(scope, secret: str) -> bool:
    """The shipped default password opens the Router only on this PC (the
    loopback listener). Over the network it must be changed first: it is public."""
    return not scope.get('orion_loopback_listener') and is_default_secret(secret)

def _get_cipher() -> Fernet:
    from core.config import ENCRYPTION_KEY
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY is not set in environment variables.")
    return Fernet(ENCRYPTION_KEY.encode('utf-8'))

def encrypt(text: str) -> str:
    """Encrypts a string using Fernet symmetric encryption."""
    if not text:
        return text
    cipher = _get_cipher()
    return cipher.encrypt(text.encode('utf-8')).decode('utf-8')

def decrypt(encrypted_text: str) -> str | None:
    """Decrypts a string using Fernet symmetric encryption.
    Returns decrypted plaintext if valid.
    Returns the string as-is if it's plaintext (not a Fernet token).
    Returns None if it is a Fernet token (starts with gAAAAA) but cannot be decrypted.
    """
    if not encrypted_text:
        return encrypted_text
    
    # Check if the text actually looks like a fernet token (starts with gAAAAA or similar)
    if not encrypted_text.startswith('gAAAAA'):
        return encrypted_text # Probably plaintext

    try:
        cipher = _get_cipher()
        return cipher.decrypt(encrypted_text.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception):
        # Decryption failed (encryption key mismatch or corrupted ciphertext).
        # Return None so callers know this key cannot be decrypted.
        return None
