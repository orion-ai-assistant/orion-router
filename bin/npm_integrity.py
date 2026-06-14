import os
import hashlib
from pathlib import Path

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def npm_needs_install(dashboard: Path) -> bool:
    node_modules = dashboard / "node_modules"
    lock_file = dashboard / "package-lock.json"
    hash_file = dashboard / ".npm_lockfile_hash"
    
    if not node_modules.exists() or not node_modules.is_dir():
        return True
    if not lock_file.exists() or not hash_file.exists():
        return True
        
    try:
        current_hash = _sha256(lock_file)
        stored_hash = hash_file.read_text(encoding="utf-8").strip()
        return current_hash != stored_hash
    except Exception:
        return True

def record_npm_install(dashboard: Path) -> None:
    lock_file = dashboard / "package-lock.json"
    hash_file = dashboard / ".npm_lockfile_hash"
    
    if lock_file.exists():
        try:
            current_hash = _sha256(lock_file)
            hash_file.write_text(current_hash, encoding="utf-8")
        except Exception:
            pass
