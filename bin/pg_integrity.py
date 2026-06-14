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
            manifest["files"][relative] = _sha256(file_path)
            
    manifest_path = tools_dir / "pgsql.manifest"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

def verify_manifest(tools_dir: Path) -> bool:
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
        
    for relative_path, expected_hash in manifest["files"].items():
        actual_file = pgsql_dir / relative_path
        if not actual_file.exists():
            return False
        try:
            if _sha256(actual_file) != expected_hash:
                return False
        except Exception:
            return False
            
    return True
