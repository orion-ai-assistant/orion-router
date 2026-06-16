# Design Document: Dashboard Localization (i18n)

## Overview

Bu belge, Orion Router Dashboard'una çok dilli destek (i18n) eklenmesinin teknik tasarımını açıklar.
Sistem; üçüncü parti kütüphane kullanmadan, React Context + düz JSON dosyaları ile 43 dili destekleyecek;
RTL yazım yönünü otomatik algılayacak; locale seçimini `localStorage`'da kalıcı tutacak ve tüm bileşen
çevirilerini `t()` fonksiyonu aracılığıyla senkron olarak sunacaktır.

### Temel Tasarım Kararları

- **Sıfır bağımlılık**: `react-i18next`, `next-intl` gibi kütüphaneler eklenmeyecek. Tüm i18n mantığı `dashboard/lib/i18n.ts` içinde geliştirilecek.
- **Next.js static export uyumu**: `output: 'export'` modunda çalışmak için locale dosyaları `public/` altında konumlandırılacak; dinamik `getServerSideProps` kullanılmayacak.
- **İstemci tarafı yükleme**: Locale dosyaları `fetch()` ile client-side yüklenecek, SSR gerektirmeyecek.
- **Namespace tabanlı anahtar yapısı**: Tüm çeviri anahtarları `namespace.key` formatını izleyecek.


## Architecture

### Katman Diyagramı

```
┌──────────────────────────────────────────────────────────┐
│                  dashboard/app/layout.tsx                 │
│  <html lang={locale} dir={dir}>                           │
│  <AppProvider> → locale, setLocale, t() sağlar            │
└─────────────────────────┬────────────────────────────────┘
                          │ React Context
          ┌───────────────▼───────────────┐
          │        AppContext.tsx          │
          │  locale state                 │
          │  translations state           │
          │  fallbackTranslations state   │
          │  setLocale()                  │
          │  t(key, vars?) closure        │
          └──────────────┬────────────────┘
                         │ lib/i18n.ts çağrıları
          ┌──────────────▼────────────────┐
          │          lib/i18n.ts           │
          │  SUPPORTED_LOCALES            │
          │  RTL_LOCALES                  │
          │  detectLocale()               │
          │  loadLocale(lang)             │
          │  createTranslator(tr, fb)     │
          └──────────────┬────────────────┘
                         │ fetch()
          ┌──────────────▼────────────────┐
          │   public/locales/{lang}.json  │
          │   (43 dil dosyası)            │
          └───────────────────────────────┘
```

### Veri Akışı

1. `AppProvider` mount olduğunda `detectLocale()` → başlangıç locale kodu belirlenir.
2. `en.json` (fallback) ve aktif locale dosyası paralel olarak yüklenir.
3. `createTranslator(translations, fallbackTranslations)` çağrılır; `t()` closure döner.
4. `locale`, `setLocale`, `t()` ve `SUPPORTED_LOCALES` Context değeri olarak sağlanır.
5. `setLocale(lang)` çağrıldığında: localStorage yazılır → yeni locale dosyası yüklenir → state güncellenir → tüm bileşenler yeniden render edilir.
6. `HtmlWrapper` bileşeni locale değiştiğinde `document.documentElement.lang` ve `dir` özniteliklerini günceller.


## Components and Interfaces

### `lib/i18n.ts` — Modül API'si

```typescript
// Desteklenen tüm 43 dil kodu
export const SUPPORTED_LOCALES: readonly string[]

// Sağdan sola yazım gerektiren dil kodları
export const RTL_LOCALES: string[] = ['ar', 'fa', 'he', 'ur']

// Dil adları haritası (yerel isimler)
export const LOCALE_NAMES: Record<string, string>

// localStorage → navigator.language → 'en' sırasıyla locale belirler
export function detectLocale(): string

// /dashboard/locales/{lang}.json dosyasını fetch eder
// In-flight deduplication: aynı dil için eş zamanlı istekler tek isteğe indirgenir
export function loadLocale(lang: string): Promise<Record<string, string>>

// Aktif ve fallback çeviri nesnelerini kapatan closure döner
// t(key) → active[key] ?? fallback[key] ?? key
// t(key, vars) → yukarıdaki değerde {variable} interpolasyonu uygular
export function createTranslator(
  translations: Record<string, string>,
  fallback: Record<string, string>
): (key: string, vars?: Record<string, string>) => string
```

**In-flight deduplication mekanizması:**

```typescript
const inFlightRequests = new Map<string, Promise<Record<string, string>>>()

export function loadLocale(lang: string): Promise<Record<string, string>> {
  if (inFlightRequests.has(lang)) return inFlightRequests.get(lang)!
  const promise = fetch(`/dashboard/locales/${lang}.json`)
    .then(res => res.json())
    .finally(() => inFlightRequests.delete(lang))
  inFlightRequests.set(lang, promise)
  return promise
}
```

