import os
import json
import locale
from pathlib import Path

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
                        cli_lang = v.strip().strip('"').strip("'").lower()
                        break
        except Exception:
            pass

    if cli_lang in ["tr", "en", "zh"]:
        return cli_lang

    # 2. Check OS Environment variable
    env_lang = os.getenv("CLI_LANG")
    if env_lang:
        env_lang = env_lang.lower()
        if env_lang in ["tr", "en", "zh"]:
            return env_lang

    # 3. Detect system default display language
    try:
        sys_lang, _ = locale.getdefaultlocale()
        if sys_lang:
            sys_lang = sys_lang.lower()
            if sys_lang.startswith("tr"):
                return "tr"
            elif sys_lang.startswith("zh"):
                return "zh"
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
        return msg.format(**kwargs)
    return msg
