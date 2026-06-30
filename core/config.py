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

# Sadece ENCRYPTION_KEY için kalıcı volume dizini
_PERSISTENT_DIR = _ROOT / "persistent"
_KEY_FILE = _PERSISTENT_DIR / "encryption.key"


def _is_docker() -> bool:
    return pathlib.Path("/.dockerenv").exists()

def _ensure_env_file() -> bool:
    """
    .env dosyasını yönetir:
    - Yoksa .env.example'dan oluşturur.
    - Varsa .env.example'daki eksik anahtarları otomatik ekler.
    Docker içindeyken (RAM'den okunduğu için) bu fiziksel dosyayı oluşturmaz.
    """
    if _is_docker():
        return False

    if not _ENV_EXAMPLE_PATH.exists():
        return False

    if not _ENV_PATH.exists():
        # --- İlk kurulum: .env.example'ı kopyala ---
        try:
            shutil.copy(_ENV_EXAMPLE_PATH, _ENV_PATH)
            try:
                from bin.i18n import t
                msg = t("config_env_copied")
            except Exception:
                msg = "[orion-router] .env not found; .env.example copied to .env."
            print(msg, file=sys.stderr)
            return True
        except OSError:
            return False

    # --- Mevcut .env: eksik anahtarları .env.example'dan otomatik ekle ---
    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            env_content = f.read()

        existing_keys: set[str] = set()
        for line in env_content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                existing_keys.add(stripped.split("=", 1)[0].strip())

        missing_lines: list[str] = []
        with open(_ENV_EXAMPLE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key not in existing_keys:
                        missing_lines.append(stripped)

        if missing_lines:
            with open(_ENV_PATH, "a", encoding="utf-8") as f:
                f.write("\n# --- Auto-merged from .env.example ---\n")
                for ml in missing_lines:
                    f.write(ml + "\n")
            count = len(missing_lines)
            try:
                from bin.i18n import t
                msg = t("config_env_merged", count=count)
            except Exception:
                msg = f"[orion-router] {count} missing key(s) added to .env from .env.example."
            print(msg, file=sys.stderr)
    except OSError:
        pass

    return False


_ensure_env_file()


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


_load_env_file()


def _ensure_encryption_key() -> None:
    """
    ENCRYPTION_KEY'i yönetir.
    Öncelik sırası:
      1. Sistem ortam değişkeni (Docker env'den gelebilir)
      2. /app/persistent/encryption.key dosyası (Docker volume - kalıcı)
      3. Yoksa üret ve volume dosyasına yaz
    """
    # 1. Zaten ortam değişkeninden geliyorsa kullan
    if "ENCRYPTION_KEY" in os.environ:
        return

    # 2. Volume dosyasında varsa oku
    if _KEY_FILE.exists():
        try:
            key = _KEY_FILE.read_text(encoding="utf-8").strip()
            if key:
                os.environ["ENCRYPTION_KEY"] = key
                return
        except OSError:
            pass

    # 3. Üret ve volume dosyasına yaz (kalıcı)
    try:
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key().decode("utf-8")
        os.environ["ENCRYPTION_KEY"] = new_key
        # Volume dizini yoksa oluştur (yerel geliştirme için de çalışsın)
        _PERSISTENT_DIR.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_text(new_key, encoding="utf-8")
        try:
            from bin.i18n import t
            msg = t("config_key_created")
        except Exception:
            msg = "[orion-router] New ENCRYPTION_KEY generated and saved to persistent volume."
        print(msg, file=sys.stderr)
    except Exception as e:
        try:
            from bin.i18n import t
            msg = t("config_key_failed", e=e)
        except Exception:
            msg = f"[orion-router] ENCRYPTION_KEY could not be generated: {e}"
        print(msg, file=sys.stderr)

_ensure_encryption_key()








# --- Router (bu servis) ---
ROUTER_HOST = os.getenv("ROUTER_HOST")
ROUTER_PORT = os.getenv("ROUTER_PORT")

# --- Yerel Servis Adresleri ---
LLM_HOST = os.getenv("LLM_HOST")
LLM_PORT = os.getenv("LLM_PORT")

EMBED_HOST = os.getenv("EMBED_HOST")
EMBED_PORT = os.getenv("EMBED_PORT")

TTS_HOST = os.getenv("TTS_HOST")
TTS_PORT = os.getenv("TTS_PORT")

# --- Admin Paneli ---
# Admin paneline giriş için gereken şifre (sadece ilk seed işlemi için okunur, DB'ye aktarılır).
ADMIN_SECRET = os.getenv("ADMIN_SECRET")

# --- Şifreleme (API Keys vs) ---
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# --- Veritabanı (PostgreSQL) ---
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

# --- Veri Dosyaları ---
_DATA_DIR = _ROOT / "data"

MODEL_PRICING_PATH = _DATA_DIR / "model_pricing.json"

# --- App Identification Headers ---
APP_REFERER = os.getenv("APP_REFERER")
APP_TITLE = os.getenv("APP_TITLE")
APP_CATEGORIES = os.getenv("APP_CATEGORIES")

# --- Dashboard UI ---
# Next.js static build directory (out)
_dash_val = os.getenv("DASHBOARD_OUT_DIR")
if _dash_val:
    if pathlib.Path(_dash_val).is_absolute():
        DASHBOARD_OUT_DIR = _dash_val
    else:
        # Check if the relative path exists
        _rel_path = _ROOT / _dash_val
        if _rel_path.exists():
            DASHBOARD_OUT_DIR = str(_rel_path)
        elif os.path.exists("/dashboard_out"):
            # Fallback to container path if relative path doesn't exist but container path does
            DASHBOARD_OUT_DIR = "/dashboard_out"
        else:
            DASHBOARD_OUT_DIR = str(_rel_path)
else:
    DASHBOARD_OUT_DIR = "/dashboard_out" if os.path.exists("/dashboard_out") else str(_ROOT / "dashboard/out")

