import os
import json
import hashlib
from pathlib import Path

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def generate_manifest(tools_dir: Path, version_label: str) -> None:
    pgsql_dir = tools_dir / "pgsql"
    if not pgsql_dir.exists():
        return

    manifest = {"version": version_label, "files": {}}
    for root, _, files in os.walk(pgsql_dir):
        for file in files:
            file_path = Path(root) / file
            relative = str(file_path.relative_to(pgsql_dir)).replace("\\", "/")
            try:
                manifest["files"][relative] = {
                    "size": file_path.stat().st_size,
                    "sha256": _sha256(file_path),
                }
            except Exception:
                pass

    manifest_path = tools_dir / "pgsql.manifest"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def verify_manifest(tools_dir: Path) -> bool:
    """Bütünlük doğrulaması — dosya varlığı ve boyut kontrolü.

    Hash hesaplamaz. Sadece dosya var mı ve boyutu doğru mu diye bakar.
    Bir hata durumunda çalışır, yaklaşık 100-300ms sürer. 
    Eğer eksik/farklı boyutta dosya varsa False döner ve onarımı tetikler.
    """
    manifest_path = tools_dir / "pgsql.manifest"
    if not manifest_path.exists():
        return False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        return False

    pgsql_dir = tools_dir / "pgsql"
    if "files" not in manifest:
        return False

    for relative_path, info in manifest["files"].items():
        actual_file = pgsql_dir / relative_path
        if not actual_file.exists():
            return False
        
        try:
            expected_size = info.get("size") if isinstance(info, dict) else None
            if expected_size is not None and actual_file.stat().st_size != expected_size:
                return False
        except Exception:
            return False

    return True

