import os
import json
import locale
from pathlib import Path

SUPPORTED_LOCALES = [
    "en", "vi", "zh-CN", "zh-TW", "ja", "pt-BR", "pt-PT", "ko", "es", "de", 
    "fr", "he", "ar", "ru", "pl", "cs", "nl", "tr", "uk", "tl", "id", "th", 
    "hi", "bn", "ur", "ro", "sv", "it", "el", "hu", "fi", "da", "no",
    "fa", "ms", "sw", "ta", "te", "mr", "sk", "bg", "sr", "hr"
]

# RTL (Right-to-Left) diller: terminal BIDI sorunlarını hafifletmek için
# mesajlar RLM (U+200F) + RLE (U+202B) ... PDF (U+202C) ile sarmalanır.
RTL_LOCALES = {"ar", "fa", "he", "ur"}

# RLM  = Right-to-Left Mark      → akış yönünü RTL olarak işaretler
# RLE  = Right-to-Left Embedding → gömülü LTR metni (değişkenler) doğru hizalar
# PDF  = Pop Directional Format  → RLE bloğunu kapatır
_RLM = "\u200f"
_RLE = "\u202b"
_PDF = "\u202c"

def normalize_locale(locale_str: str) -> str:
    if not locale_str:
        return "en"
    
    locale_str = locale_str.strip().lower().replace("_", "-")
    
    # Exact case-insensitive match
    for loc in SUPPORTED_LOCALES:
        if loc.lower() == locale_str:
            return loc
            
    # Try mapping prefix (e.g. ja-jp -> ja, es-es -> es)
    prefix = locale_str.split("-")[0]
    for loc in SUPPORTED_LOCALES:
        if loc.lower() == prefix:
            return loc
            
    # Custom fallback for Chinese
    if prefix == "zh":
        if "tw" in locale_str or "hk" in locale_str:
            return "zh-TW"
        return "zh-CN"
        
    return "en"

def detect_lang() -> str:
    # 1. Check if CLI_LANG is set in the .env file in project root
    root = Path(__file__).parent.parent.resolve()
    env_file = root / ".env"
    cli_lang = None
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, _, v = stripped.partition("=")
                    if k.strip() == "CLI_LANG":
                        cli_lang = v.strip().strip('"').strip("'")
                        break
        except Exception:
            pass

    if cli_lang:
        normalized = normalize_locale(cli_lang)
        if normalized != "en" or cli_lang.lower().startswith("en"):
            return normalized

    # 2. Check OS Environment variable
    env_lang = os.getenv("CLI_LANG")
    if env_lang:
        normalized = normalize_locale(env_lang)
        if normalized != "en" or env_lang.lower().startswith("en"):
            return normalized

    # 3. Detect system default display language
    try:
        sys_lang, _ = locale.getdefaultlocale()
        if sys_lang:
            normalized = normalize_locale(sys_lang)
            if normalized != "en" or sys_lang.lower().startswith("en"):
                return normalized
    except Exception:
        pass

    return "en"

LANG = detect_lang()

def load_messages(lang: str) -> dict:
    locales_dir = Path(__file__).parent / "locales"
    lang_file = locales_dir / f"{lang}.json"

    # Fallback to en.json if target file is not found
    if not lang_file.exists():
        lang_file = locales_dir / "en.json"

    if lang_file.exists():
        try:
            return json.loads(lang_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

MESSAGES = load_messages(LANG)
FALLBACK_MESSAGES = load_messages("en") if LANG != "en" else MESSAGES

def t(key: str, **kwargs) -> str:
    msg = MESSAGES.get(key, FALLBACK_MESSAGES.get(key, key))
    if kwargs:
        msg = msg.format(**kwargs)

    # RTL dillerde Unicode yön işaretleriyle sar:
    # RLM → terminal akışını RTL olarak işaretle
    # RLE...PDF → LTR içeriği (değişkenler, İngilizce terimler) doğru hizala
    if LANG in RTL_LOCALES:
        msg = f"{_RLM}{_RLE}{msg}{_PDF}"

    return msg

# --- API (HTTP Request) Translation Support ---
_API_LANG_CACHE = {}

def parse_accept_language(accept_language_header: str | None) -> str:
    """HTTP Accept-Language başlığından en öncelikli dil kodunu çıkarır."""
    if not accept_language_header:
        return LANG
    try:
        # Örnek: "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
        parts = accept_language_header.split(",")
        if parts:
            first_part = parts[0].split(";")[0].strip()
            return first_part
    except Exception:
        pass
    return LANG


def t_lang(key: str, lang_str: str | None, **kwargs) -> str:
    """Belirtilen dile göre (HTTP Accept-Language vb.) çeviri döndürür, cache kullanır."""
    parsed_lang = parse_accept_language(lang_str)
    normalized = normalize_locale(parsed_lang)
    
    if normalized not in _API_LANG_CACHE:
        _API_LANG_CACHE[normalized] = load_messages(normalized)
        
    msg = _API_LANG_CACHE[normalized].get(key)
    if msg is None:
        # Fallback to English
        if "en" not in _API_LANG_CACHE:
            _API_LANG_CACHE["en"] = load_messages("en")
        msg = _API_LANG_CACHE["en"].get(key, key)
        
    if kwargs:
        msg = msg.format(**kwargs)
        
    if normalized in RTL_LOCALES:
        msg = f"{_RLM}{_RLE}{msg}{_PDF}"
        
    return msg

