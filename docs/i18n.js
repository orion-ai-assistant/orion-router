const LOCALES = ["en", "vi", "zh-CN", "zh-TW", "ja", "pt-BR", "pt-PT", "ko", "es", "de", "fr", "he", "ar", "ru", "pl", "cs", "nl", "tr", "uk", "tl", "id", "th", "hi", "bn", "ur", "ro", "sv", "it", "el", "hu", "fi", "da", "no", "fa", "ms", "sw", "ta", "te", "mr", "sk", "bg", "sr", "hr"];
const DEFAULT_LOCALE = "en";
const LOCALE_COOKIE = "locale";

const LOCALE_NAMES = {
  "en": "English",
  "vi": "Tiếng Việt",
  "zh-CN": "简体中文",
  "zh-TW": "繁體中文",
  "ja": "日本語",
  "pt-BR": "Português (Brasil)",
  "pt-PT": "Português (Portugal)",
  "ko": "한국어",
  "es": "Español",
  "de": "Deutsch",
  "fr": "Français",
  "he": "עברית",
  "ar": "العربية",
  "ru": "Русский",
  "pl": "Polski",
  "cs": "Čeština",
  "nl": "Nederlands",
  "tr": "Türkçe",
  "uk": "Українська",
  "tl": "Tagalog",
  "id": "Indonesia",
  "th": "ไทย",
  "hi": "हिन्दी",
  "bn": "বাংলা",
  "ur": "اردو",
  "ro": "Română",
  "sv": "Svenska",
  "it": "Italiano",
  "el": "Ελληνικά",
  "hu": "Magyar",
  "fi": "Suomi",
  "da": "Dansk",
  "no": "Norsk",
  "fa": "فارسی",
  "ms": "Bahasa Melayu",
  "sw": "Kiswahili",
  "ta": "தமிழ்",
  "te": "తెలుగు",
  "mr": "मराठी",
  "sk": "Slovenčina",
  "bg": "Български",
  "sr": "Српски",
  "hr": "Hrvatski"
};

function normalizeLocale(locale) {
  if (!locale) return DEFAULT_LOCALE;
  locale = locale.trim();
  const lowerLocale = locale.toLowerCase();
  
  if (lowerLocale === "zh" || lowerLocale === "zh-cn") {
    return "zh-CN";
  }
  if (lowerLocale === "zh-tw" || lowerLocale === "zh-hk") {
    return "zh-TW";
  }
  
  for (const loc of LOCALES) {
    if (loc.toLowerCase() === lowerLocale) {
      return loc;
    }
  }
  
  const prefix = lowerLocale.split("-")[0];
  for (const loc of LOCALES) {
    if (loc.toLowerCase() === prefix) {
      return loc;
    }
  }
  
  return DEFAULT_LOCALE;
}

function isSupportedLocale(locale) {
  return LOCALES.includes(locale);
}

(function() {
    function getStoredLanguage() {
        try {
            const localLang = localStorage.getItem(LOCALE_COOKIE);
            if (localLang && isSupportedLocale(localLang)) {
                return localLang;
            }
        } catch (e) {}
        return null;
    }

    function setStoredLanguage(lang) {
        try {
            localStorage.setItem(LOCALE_COOKIE, lang);
        } catch (e) {}
    }

    function loadLanguageFile(lang) {
        return new Promise((resolve) => {
            if (window.ORION_TRANSLATIONS && window.ORION_TRANSLATIONS[lang]) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.charset = 'utf-8';
            script.src = `locales/${lang}.js`;
            script.onload = () => resolve();
            script.onerror = () => {
                console.warn(`Could not load locale: ${lang}`);
                resolve();
            };
            document.head.appendChild(script);
        });
    }

    function detectLanguage() {
        const storedLang = getStoredLanguage();
        if (storedLang) {
            return storedLang;
        }
        const browserLang = (navigator.language || navigator.userLanguage || '').toLowerCase();
        return normalizeLocale(browserLang);
    }

    window.t = function(key) {
        if (typeof window.ORION_TRANSLATIONS === 'undefined') return key;
        const dict = window.ORION_TRANSLATIONS[window.ORION_CURRENT_LANG] || window.ORION_TRANSLATIONS['en'];
        const fallback = window.ORION_TRANSLATIONS['en'];
        return dict[key] !== undefined ? dict[key] : (fallback[key] !== undefined ? fallback[key] : key);
    };

    window.setLanguage = async function(lang) {
        const normalized = normalizeLocale(lang);
        await loadLanguageFile(normalized);
        
        window.ORION_CURRENT_LANG = normalized;
        document.documentElement.lang = normalized;
        
        // Handle RTL layouts (without flipping the global flex grids and logo/buttons)
        const rtlLocales = ["fa", "ar", "he", "ur"];
        if (rtlLocales.includes(normalized)) {
            document.documentElement.dir = "ltr";
            document.documentElement.classList.add("rtl-active");
        } else {
            document.documentElement.dir = "ltr";
            document.documentElement.classList.remove("rtl-active");
        }
        
        setStoredLanguage(normalized);

        const translateElements = document.querySelectorAll('[data-i18n]');
        translateElements.forEach(el => {
            const key = el.getAttribute('data-i18n');
            const value = window.t(key);
            if (value !== key) {
                el.innerHTML = value;
            }
        });

        document.dispatchEvent(new CustomEvent('orion-lang-changed', { detail: { lang: normalized } }));
    };

    window.ORION_CURRENT_LANG = detectLanguage();

    const globals = {
        LOCALES,
        DEFAULT_LOCALE,
        LOCALE_COOKIE,
        LOCALE_NAMES,
        normalizeLocale,
        isSupportedLocale
    };

    for (const key in globals) {
        window[key] = globals[key];
    }

    if (typeof exports !== 'undefined') {
        for (const key in globals) {
            exports[key] = globals[key];
        }
    }

    document.addEventListener('DOMContentLoaded', async () => {
        await loadLanguageFile('en');
        await window.setLanguage(window.ORION_CURRENT_LANG);
    });
})();
