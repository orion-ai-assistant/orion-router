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
    lock_file    = dashboard / "package-lock.json"
    hash_file    = dashboard / ".npm_lockfile_hash"

    if not node_modules.exists() or not node_modules.is_dir():
        return True
    if not lock_file.exists() or not hash_file.exists():
        return True

    try:
        # Hızlı boyut kontrolü — boyut değişmemişse hash hesaplamaya gerek yok
        stored = hash_file.read_text(encoding="utf-8").strip()

        # Yeni format: "SIZE:HASH" — boyut eşleşmezse direkt True dön
        if ":" in stored:
            stored_size_str, stored_hash = stored.split(":", 1)
            current_size = lock_file.stat().st_size
            if int(stored_size_str) != current_size:
                return True
            return _sha256(lock_file) != stored_hash
        else:
            # Eski format: sadece hash — tam kontrol yap
            return _sha256(lock_file) != stored

    except Exception:
        return True

def record_npm_install(dashboard: Path) -> None:
    lock_file = dashboard / "package-lock.json"
    hash_file = dashboard / ".npm_lockfile_hash"

    if lock_file.exists():
        try:
            size = lock_file.stat().st_size
            current_hash = _sha256(lock_file)
            # Yeni format: "SIZE:HASH"
            hash_file.write_text(f"{size}:{current_hash}", encoding="utf-8")
        except Exception:
            pass
