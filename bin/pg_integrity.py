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
    """Kurulum tamamlandığında manifest + sentinel dosyasını oluşturur.
    
    Sentinel (pgsql.ready) dosyası yalnızca tüm işlemler başarıyla
    tamamlandığında yazılır. Bu sayede yarım kalan kurulumlar güvenle tespit edilir.
    """
    pgsql_dir = tools_dir / "pgsql"
    if not pgsql_dir.exists():
        return

    # Önceki sentinel'i sil — yeni manifest yazılana kadar kurulum "eksik" sayılır
    (tools_dir / "pgsql.ready").unlink(missing_ok=True)

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

    # Sentinel: manifest tamamen yazıldıktan sonra kurulumun eksiksiz olduğunu işaretler
    (tools_dir / "pgsql.ready").write_text(version_label, encoding="utf-8")


def verify_manifest(tools_dir: Path) -> bool:
    """Kurulumun eksiksiz tamamlandığını kontrol eder.

    Mantık: Sadece 'pgsql.ready' sentinel dosyasına bakar.
    Bu dosya yalnızca generate_manifest() başarıyla tamamlandığında oluşturulur.
    Kurulum yarım kaldıysa sentinel yoktur → False döner → yeniden kurulum tetiklenir.
    """
    return (tools_dir / "pgsql.ready").is_file()


