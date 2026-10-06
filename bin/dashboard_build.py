"""Build the static dashboard only when its source fingerprint changes."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from bin.npm_integrity import npm_needs_install, record_npm_install

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
SCHEMA = 1
MANIFEST = ".orion-build.json"
EXCLUDED_DIRS = {"node_modules", ".next", "out", ".git"}
EXCLUDED_FILES = {".DS_Store", "Thumbs.db", ".npm_lockfile_hash", "next-env.d.ts"}
# This catalog is imported by dashboard/lib/local-chat-defaults.ts at build time.
BUILD_INPUTS = ("providers/local/models.json",)


def _excluded(name: str) -> bool:
    return (name in EXCLUDED_DIRS or name in EXCLUDED_FILES
            or name.endswith((".log", ".tsbuildinfo")))


def get_dashboard_hash() -> str:
    def onerror(error: OSError) -> None:
        raise error

    files = []
    for directory, dirs, names in os.walk(DASHBOARD, onerror=onerror):
        dirs[:] = [name for name in dirs if not _excluded(name)]
        for name in names:
            if not _excluded(name):
                path = Path(directory) / name
                files.append((path.relative_to(ROOT).as_posix(), path))
    files.extend((name, ROOT / name) for name in BUILD_INPUTS)
    digest = hashlib.sha256()
    for name, path in sorted(files):
        # Length prefixes keep path/content boundaries unambiguous.
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _build_reason() -> str | None:
    out = DASHBOARD / "out"
    if not (out / "index.html").is_file():
        return "Dashboard çıktısı bulunamadı"
    try:
        manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict) or type(manifest.get("schema")) is not int
                or manifest["schema"] != SCHEMA):
            return "Dashboard manifesti geçersiz"
        if not manifest.get("source_hash"):
            return "Dashboard kaynak hash'i bulunamadı"
        if manifest["source_hash"] != get_dashboard_hash():
            return "Dashboard kaynakları değişti"
    except (OSError, ValueError):
        return "Dashboard manifesti veya kaynakları okunamadı"
    return None


def dashboard_needs_build() -> bool:
    return _build_reason() is not None


def _run_npm(command: str, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, shell=True)
    if result.returncode:
        raise RuntimeError(f"{command} başarısız oldu (exit code {result.returncode}).")


def build_dashboard() -> None:
    """Build in isolation, then replace out; failed builds leave the live UI intact."""
    source_hash = get_dashboard_hash()
    with tempfile.TemporaryDirectory(prefix=".orion-dashboard-", dir=ROOT) as directory:
        stage = Path(directory)
        shutil.copytree(DASHBOARD, stage, dirs_exist_ok=True,
                        ignore=lambda _, names: [name for name in names if _excluded(name)])
        modules = stage / "node_modules"
        # Windows directory junctions work without symlink privileges.
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(modules),
                            str(DASHBOARD / "node_modules")], check=True,
                           stdout=subprocess.DEVNULL)
        else:
            modules.symlink_to(DASHBOARD / "node_modules", target_is_directory=True)
        try:
            _run_npm("npm run build", stage)
        finally:
            if os.name == "nt":
                modules.rmdir()  # Remove the junction itself, never its target.
            else:
                modules.unlink()
        output = stage / "out"
        if not (output / "index.html").is_file():
            raise RuntimeError("Dashboard derlemesi index.html üretmedi.")
        if get_dashboard_hash() != source_hash:
            raise RuntimeError("Dashboard kaynakları derleme sırasında değişti; tekrar deneyin.")
        package = json.loads((DASHBOARD / "package.json").read_text(encoding="utf-8"))
        (output / MANIFEST).write_text(json.dumps({
            "schema": SCHEMA,
            "source_hash": source_hash,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "next_version": package.get("dependencies", {}).get("next"),
        }, indent=2) + "\n", encoding="utf-8")
        live = DASHBOARD / "out"
        backup = stage / "previous-out"
        if live.exists():
            live.rename(backup)
        try:
            output.rename(live)
        except BaseException:
            if backup.exists():
                backup.rename(live)
            raise


def ensure_dashboard(force: bool = False, *, log: Callable[[str], None] | None = None) -> None:
    report = log or (lambda message: print(message, flush=True))
    reason = "Dashboard derlemesi zorlandı" if force else _build_reason()
    if reason is None:
        report("[OK] Dashboard güncel, derleme atlandı.")
        return
    report(f"[INFO] {reason}, derleniyor...")
    if npm_needs_install(DASHBOARD):
        _run_npm("npm install", DASHBOARD)
        record_npm_install(DASHBOARD)
    build_dashboard()
    report("[OK] Dashboard derlemesi tamamlandı.")


if __name__ == "__main__":
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        ensure_dashboard()
    except Exception as exc:
        print(f"[ERROR] Dashboard hazırlanamadı: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
