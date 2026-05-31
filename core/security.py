import hashlib
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
    return hash_secret(secret, salt) == hashed_secret

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

def decrypt(encrypted_text: str) -> str:
    """Decrypts a string using Fernet symmetric encryption."""
    if not encrypted_text:
        return encrypted_text
    
    # Check if the text actually looks like a fernet token (starts with gAAAAA or similar)
    if not encrypted_text.startswith('gAAAAA'):
        return encrypted_text # Probably plaintext

    cipher = _get_cipher()
    try:
        return cipher.decrypt(encrypted_text.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        # If decryption fails, it might be plaintext that coincidentally starts with gAAAAA
        # or the encryption key changed. Return as is for graceful failure/fallback.
        return encrypted_text
