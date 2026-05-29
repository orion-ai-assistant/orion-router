"""
core/config.py
--------------
Uygulama genelindeki ortam değişkenleri ve sabitler.
Diğer modüller bu dosyadan import eder, doğrudan os.getenv çağırmazlar.
"""
import os
import pathlib
import shutil
import sys

_ROOT = pathlib.Path(__file__).parent.parent
_ENV_PATH = _ROOT / ".env"
_ENV_EXAMPLE_PATH = _ROOT / ".env.example"


def _ensure_env_file() -> bool:
    """Yoksa .env.example dosyasından .env oluşturur (Docker / ilk kurulum)."""
    if _ENV_PATH.exists():
        return False
    if not _ENV_EXAMPLE_PATH.exists():
        return False
    try:
        shutil.copy(_ENV_EXAMPLE_PATH, _ENV_PATH)
        print(
            "[orion-router] .env bulunamadı; .env.example kopyalanarak .env oluşturuldu.",
            file=sys.stderr,
        )
        return True
    except OSError:
        return False


def _load_env_file() -> None:
    if not _ENV_PATH.exists():
        return
    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        val = val[1:-1]
                    # Sistem ortam değişkenleri önceliklidir, ezilmezler
                    if key and key not in os.environ:
                        os.environ[key] = val
    except OSError:
        pass


_ensure_env_file()
_load_env_file()


# --- Router (bu servis) ---
ROUTER_HOST = os.getenv("ROUTER_HOST", "0.0.0.0")
ROUTER_PORT = os.getenv("ROUTER_PORT", "20128")

# --- Yerel Servis Adresleri ---
LLM_HOST = os.getenv("LLM_HOST", "llama-cpp")
LLM_PORT = os.getenv("LLM_PORT", "8080")

EMBED_HOST = os.getenv("EMBED_HOST", "llama-cpp-embed")
EMBED_PORT = os.getenv("EMBED_PORT", "8080")

TTS_HOST = os.getenv("TTS_HOST", "tts")
TTS_PORT = os.getenv("TTS_PORT", "8808")

# --- Admin Paneli ---
# Admin paneline giriş için gereken şifre.
# Env'de ADMIN_SECRET ayarlanmadıysa varsayılan olarak "orion-admin" kullanılır.
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "orion-admin")

# --- Veri Dosyaları ---
_DATA_DIR = _ROOT / "data"

MODEL_PRICING_PATH = _DATA_DIR / "model_pricing.json"
MODEL_INFO_PATH = _DATA_DIR / "model_info.json"

# --- Dashboard UI ---
# Next.js static build directory (out)
DASHBOARD_OUT_DIR = os.getenv("DASHBOARD_OUT_DIR", str(_ROOT / "dashboard" / "out"))

