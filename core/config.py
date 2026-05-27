"""
core/config.py
--------------
Uygulama genelindeki ortam değişkenleri ve sabitler.
Diğer modüller bu dosyadan import eder, doğrudan os.getenv çağırmazlar.
"""
import os
import pathlib

# --- .env Dosyasını Yükle ---
def _load_env_file():
    # Bu dosya core/config.py içinde olduğu için, parent.parent bizi services/router/ dizinine götürür.
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        # Çift veya tek tırnakları temizle
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        # .env dosyasındaki değerleri yükle (sistem ortam değişkenlerini ezebilsin)
                        if key:
                            os.environ[key] = val
        except Exception:
            pass

_load_env_file()


# --- Yerel Servis Adresleri ---
LLM_HOST = os.getenv("LLM_HOST", "llama-cpp")
LLM_PORT = os.getenv("LLM_PORT", "8080")

EMBED_HOST = os.getenv("EMBED_HOST", "llama-cpp-embed")
EMBED_PORT = os.getenv("EMBED_PORT", "8080")

TTS_HOST = os.getenv("TTS_HOST", "tts")
TTS_PORT = os.getenv("TTS_PORT", "8808")

# --- Dış Servis URL'leri ve Anahtarları ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Admin Paneli ---
# Admin paneline giriş için gereken şifre.
# Env'de ADMIN_SECRET ayarlanmadıysa varsayılan olarak "orion-admin" kullanılır.
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "orion-admin")

# --- Veri Dosyaları ---
import pathlib

# Bu dosyanın bulunduğu klasörden (core/) bir üst dizine çıkıp data/ klasörünü işaret eder
_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"

MODEL_PRICING_PATH = _DATA_DIR / "model_pricing.json"
MODEL_INFO_PATH = _DATA_DIR / "model_info.json"
