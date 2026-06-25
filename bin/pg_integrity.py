import os
import json
from pathlib import Path

def generate_manifest(tools_dir: Path, version_label: str) -> None:
    """Kurulum bittiğinde klasördeki toplam dosya sayısını ve toplam boyutu manifest dosyasına kaydeder.
    
    SHA-256 hesabı yapmadığı için 21.500+ dosya için bile 0.1 saniye sürer.
    """
    pgsql_dir = tools_dir / "pgsql"
    if not pgsql_dir.exists():
        return

    (tools_dir / "pgsql.ready").unlink(missing_ok=True)

    total_files = 0
    total_size = 0
    for root, _, files in os.walk(pgsql_dir):
        for file in files:
            file_path = Path(root) / file
            try:
                total_files += 1
                total_size += file_path.stat().st_size
            except Exception:
                pass

    manifest = {
        "version": version_label,
        "total_files": total_files,
        "total_size": total_size
    }

    manifest_path = tools_dir / "pgsql.manifest"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Sentinel dosyasını oluştur
    (tools_dir / "pgsql.ready").write_text(version_label, encoding="utf-8")


def verify_manifest(tools_dir: Path) -> bool:
    """Kurulum bütünlüğünü toplam dosya sayısı ve toplam boyuta göre hızlıca doğrular.
    
    Yalnızca dizin yapısındaki dosya sayısını ve boyutları toplar, manifest ile karşılaştırır.
    Herhangi bir dosya listesi araması veya hash kontrolü yapmaz. Anında çalışır.
    """
    if not (tools_dir / "pgsql.ready").is_file():
        return False

    manifest_path = tools_dir / "pgsql.manifest"
    if not manifest_path.is_file():
        return False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        pgsql_dir = tools_dir / "pgsql"
        if not pgsql_dir.exists():
            return False

        expected_files = manifest.get("total_files")
        expected_size = manifest.get("total_size")

        if expected_files is None or expected_size is None:
            return False

        actual_files = 0
        actual_size = 0
        for root, _, files in os.walk(pgsql_dir):
            for file in files:
                file_path = Path(root) / file
                try:
                    actual_files += 1
                    actual_size += file_path.stat().st_size
                except Exception:
                    pass

        return actual_files == expected_files and actual_size == expected_size
    except Exception:
        return False
