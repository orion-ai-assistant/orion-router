// Desteklenen tüm 43 dil kodu
export const SUPPORTED_LOCALES = [
  'ar', 'bg', 'bn', 'cs', 'da', 'de', 'el', 'en', 'es', 'fa', 'fi', 'fr', 'he', 'hi',
  'hr', 'hu', 'id', 'it', 'ja', 'ko', 'mr', 'ms', 'nl', 'no', 'pl', 'pt-BR', 'pt-PT',
  'ro', 'ru', 'sk', 'sr', 'sv', 'sw', 'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur', 'vi',
  'zh-CN', 'zh-TW'
] as const;

export type Locale = typeof SUPPORTED_LOCALES[number];

// Sağdan sola yazım gerektiren dil kodları
export const RTL_LOCALES = ['ar', 'fa', 'he', 'ur'];

// Dil adları haritası (yerel isimler)
export const LOCALE_NAMES: Record<string, string> = {
  'ar': 'العربية',
  'bg': 'Български',
  'bn': 'বাংলা',
  'cs': 'Čeština',
  'da': 'Dansk',
  'de': 'Deutsch',
  'el': 'Ελληνικά',
  'en': 'English',
  'es': 'Español',
  'fa': 'فارسی',
  'fi': 'Suomi',
  'fr': 'Français',
  'he': 'עברית',
  'hi': 'हिन्दी',
  'hr': 'Hrvatski',
  'hu': 'Magyar',
  'id': 'Bahasa Indonesia',
  'it': 'Italiano',
  'ja': '日本語',
  'ko': '한국어',
  'mr': 'मराठी',
  'ms': 'Bahasa Melayu',
  'nl': 'Nederlands',
  'no': 'Norsk',
  'pl': 'Polski',
  'pt-BR': 'Português (BR)',
  'pt-PT': 'Português (PT)',
  'ro': 'Română',
  'ru': 'Русский',
  'sk': 'Slovenčina',
  'sr': 'Српски',
  'sv': 'Svenska',
  'sw': 'Kiswahili',
  'ta': 'தமிழ்',
  'te': 'తెలుగు',
  'th': 'ไทย',
  'tl': 'Tagalog',
  'tr': 'Türkçe',
  'uk': 'Українська',
  'ur': 'اردو',
  'vi': 'Tiếng Việt',
  'zh-CN': '简体中文',
  'zh-TW': '繁體中文'
};

export const FALLBACK_LOCALE = 'en';
export const LOCALE_STORAGE_KEY = 'orion-locale';

export function isValidLocale(locale: string): locale is Locale {
  return SUPPORTED_LOCALES.includes(locale as any);
}

// localStorage -> navigator.language -> 'en' sırasıyla locale belirler
export function detectLocale(): string {
  if (typeof window === 'undefined') return FALLBACK_LOCALE;

  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored && isValidLocale(stored)) {
    return stored;
  }

  const browserLang = navigator.language;
  if (isValidLocale(browserLang)) {
    return browserLang;
  }

  // Handle cases like en-US -> en
  const shortLang = browserLang.split('-')[0];
  if (isValidLocale(shortLang)) {
    return shortLang;
  }

  return FALLBACK_LOCALE;
}

const inFlightRequests = new Map<string, Promise<Record<string, string>>>();

// /dashboard/locales/{lang}.json dosyasını fetch eder
export function loadLocale(lang: string): Promise<Record<string, string>> {
  if (inFlightRequests.has(lang)) {
    return inFlightRequests.get(lang)!;
  }

  // In Next.js with app router and static export, files in public/ are available at root
  // We specify basePath conditionally if needed, but relative to root is usually safe: /dashboard/locales/...
  // Here we assume base path is /dashboard
  const promise = fetch(`/dashboard/locales/${lang}.json`)
    .then((res) => {
      if (!res.ok) throw new Error(`Failed to load locale: ${lang}`);
      return res.json();
    })
    .catch((err) => {
      console.error(err);
      return {}; // return empty translations on failure
    })
    .finally(() => {
      inFlightRequests.delete(lang);
    });

  inFlightRequests.set(lang, promise);
  return promise;
}

export type TranslatorFunction = (key: string, vars?: Record<string, string | number>) => string;

// Aktif ve fallback çeviri nesnelerini kapatan closure döner
export function createTranslator(
  translations: Record<string, string>,
  fallback: Record<string, string>
): TranslatorFunction {
  return (key: string, vars?: Record<string, string | number>): string => {
    let result = translations[key] ?? fallback[key];
    
    if (result === undefined) {
      return key;
    }

    if (vars) {
      Object.entries(vars).forEach(([k, v]) => {
        result = result.replace(new RegExp(`{${k}}`, 'g'), String(v));
      });
    }

    return result;
  };
}
