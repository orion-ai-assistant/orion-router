"""Install a native FFmpeg/ffprobe with libopus, without any Node dependency."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request
import zipfile

from core.tts_archive import check_runtime


def install():
    try:
        print(check_runtime())
        return
    except (OSError, subprocess.SubprocessError, RuntimeError):
        pass
    if os.name == "nt":
        if platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Install a native FFmpeg build and set ORION_FFMPEG / ORION_FFPROBE on Windows ARM64")
        # BtbN is a Windows build distributor linked by ffmpeg.org/download.html.
        with urllib.request.urlopen("https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest", timeout=60) as response:
            release = json.load(response)
        import re
        assets = [asset for asset in release["assets"] if re.fullmatch(r"ffmpeg-n\d+\.\d+-latest-win64-gpl-\d+\.\d+\.zip", asset["name"])]
        if not assets:
            raise RuntimeError("No supported FFmpeg Windows release build found")
        asset = max(assets, key=lambda item: tuple(map(int, re.search(r"-n(\d+)\.(\d+)", item["name"]).groups())))
        digest = asset.get("digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise RuntimeError("FFmpeg package has no SHA256 digest")
        expected = digest.split(":", 1)[1]
        url = asset["browser_download_url"]
        print(f"Downloading native FFmpeg ({asset['name']})...", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read(200 * 1024 * 1024 + 1)
        if len(data) > 200 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("FFmpeg download size/checksum verification failed")
        target = Path(__file__).resolve().parents[1] / "tools" / "ffmpeg" / "bin"
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                candidates = [item for item in archive.namelist() if item.endswith("/bin/" + name)]
                if len(candidates) != 1:
                    raise RuntimeError("Unexpected FFmpeg package layout")
                (target / name).write_bytes(archive.read(candidates[0]))
    else:
        if shutil.which("brew"):
            command = ["brew", "install", "ffmpeg"]
        elif shutil.which("apt-get"):
            prefix = [] if os.geteuid() == 0 else ["sudo"]
            subprocess.run(prefix + ["apt-get", "update"], check=True)
            command = prefix + ["apt-get", "install", "-y", "ffmpeg"]
        elif shutil.which("dnf"):
            command = ([] if os.geteuid() == 0 else ["sudo"]) + ["dnf", "install", "-y", "ffmpeg"]
        else:
            raise RuntimeError("Install FFmpeg/ffprobe with libopus, then rerun the native installer")
        subprocess.run(command, check=True)
    print(check_runtime())


if __name__ == "__main__":
    install()
