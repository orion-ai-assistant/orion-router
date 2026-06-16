# Requirements Document

## Introduction

Bu belge, Orion Router Dashboard'una çok dilli arayüz (i18n / localization) desteği eklenmesine ilişkin gereksinimleri tanımlar. Dashboard şu an yalnızca İngilizce metin içermektedir. Bu özellik sayesinde kullanıcı, 43 farklı dilden birini seçebilecek; seçilen dil tarayıcıda kalıcı olarak saklanacak ve tüm dashboard bileşenleri (sidebar, sayfa başlıkları, butonlar, hata mesajları, dialog metinleri) seçili dile anlık olarak çevrilecektir.

Teknik tercihler: üçüncü parti i18n kütüphanesi kullanılmayacak; çözüm React Context + düz JSON dosyaları ile gerçekleştirilecektir. Locale JSON dosyaları `dashboard/public/locales/{lang}.json` biçiminde konumlandırılacak; `dashboard/lib/i18n.ts` modülü locale algılama ve çeviri (`t()`) işlevini barındıracak; `AppContext.tsx` locale durumunu ve `setLocale` işlevini yönetecektir.

---

## Glossary

- **I18n_System**: Locale algılama, locale yükleme, çeviri arama ve fallback mantığını kapsayan dashboard yerelleştirme sistemi.
- **Locale**: Bir dili ve bölgesel biçimlendirmeyi tanımlayan kod (örn. `tr`, `en`, `zh-CN`).
- **Locale_File**: `dashboard/public/locales/{lang}.json` konumundaki, o dile ait tüm çeviri anahtarlarını içeren JSON dosyası.
- **Translation_Key**: Locale dosyasında bir metne karşılık gelen benzersiz dize anahtarı (örn. `"nav.overview"`, `"settings.title"`).
- **t() Fonksiyonu**: Bir Translation_Key alıp aktif Locale'deki karşılık metnini döndüren çeviri yardımcı fonksiyonu.
- **Fallback_Locale**: Aktif Locale dosyasında bir Translation_Key bulunamazsa devreye giren yedek dil; bu projede İngilizce (`en`).
- **AppContext**: Dashboard genelindeki global state'i (`adminKey`, `isAuthenticated`, `locale`, `setLocale` vb.) sağlayan React Context.
- **Language_Panel**: Settings sayfasında yer alan, kullanıcının aktif Locale'i değiştirebildiği arayüz paneli.
- **Browser_Locale**: Tarayıcının `navigator.language` özelliğiyle bildirdiği kullanıcı dili.
- **Supported_Locales**: Dashboard'un desteklediği 43 dilin tam listesi: `ar`, `bg`, `bn`, `cs`, `da`, `de`, `el`, `en`, `es`, `fa`, `fi`, `fr`, `he`, `hi`, `hr`, `hu`, `id`, `it`, `ja`, `ko`, `mr`, `ms`, `nl`, `no`, `pl`, `pt-BR`, `pt-PT`, `ro`, `ru`, `sk`, `sr`, `sv`, `sw`, `ta`, `te`, `th`, `tl`, `tr`, `uk`, `ur`, `vi`, `zh-CN`, `zh-TW`.
- **localStorage**: Kullanıcının seçtiği locale'i `"orion-locale"` anahtarı altında kalıcı olarak saklayan tarayıcı depolama alanı.
- **RTL**: Sağdan sola yazılan diller (Arapça `ar`, Farsça `fa`, İbranice `he`, Urduca `ur`).

---

## Requirements

### Requirement 1: Locale Dosyası Yükleme

**User Story:** Bir dashboard kullanıcısı olarak, uygulama başladığında seçili dilin metin içeriklerinin otomatik olarak yüklenmesini istiyorum; böylece tüm arayüz metinlerini kendi dilimde görebilirim.

#### Acceptance Criteria

1. WHEN kullanıcı dashboard'u açtığında, THE I18n_System SHALL `localStorage`'da `"orion-locale"` anahtarını kontrol etmeli ve kayıtlı bir değer varsa o Locale'e ait Locale_File'ı yüklemelidir.
2. WHEN `localStorage`'da kayıtlı Locale bulunmadığında, THE I18n_System SHALL `navigator.language` değerini okuyarak Browser_Locale'i belirlemeli ve bu değer Supported_Locales listesinde yer alıyorsa ilgili Locale_File'ı yüklemelidir.
3. WHEN Browser_Locale değeri Supported_Locales listesinde yer almadığında, THE I18n_System SHALL Fallback_Locale olan `en` için Locale_File'ı yüklemelidir.
4. WHEN Browser_Locale değeri tam eşleşme olmaksızın yalnızca dil kodu içerdiğinde (örn. `"tr-TR"`), THE I18n_System SHALL dil kodunu (`"tr"`) ayıklayarak Supported_Locales içinde eşleşen Locale_File'ı yüklemelidir.
5. WHEN Locale_File yüklendiğinde, THE I18n_System SHALL dosyanın geçerli bir JSON nesnesi içerdiğini doğrulamalı ve geçerliyse çeviri deposuna aktarmalıdır.
6. IF Locale_File yüklemesi ağ hatası veya geçersiz JSON nedeniyle başarısız olursa, THEN THE I18n_System SHALL Fallback_Locale olan `en` Locale_File'ını yüklemeye çalışmalıdır.
7. IF Fallback_Locale Locale_File'ı da yüklenemezse, THEN THE I18n_System SHALL boş bir çeviri deposuyla çalışmaya devam etmeli ve hata durumunu konsola yazmalıdır.

---

### Requirement 2: Çeviri Fonksiyonu (t())

**User Story:** Bir frontend geliştirici olarak, bileşenlerde metni `t("key")` şeklinde tek satırda döndürebilmek istiyorum; böylece bileşen kodunu karmaşıklaştırmadan çeviri kullanabilirim.

#### Acceptance Criteria

1. THE t() Fonksiyonu SHALL bir Translation_Key argümanı alarak aktif Locale'in çeviri deposunda o anahtarın karşılığını döndürmelidir.
2. WHEN Translation_Key aktif Locale çeviri deposunda bulunamadığında, THE t() Fonksiyonu SHALL Fallback_Locale (`en`) deposunda aynı anahtarı aramalı ve bulursa o değeri döndürmelidir.
3. WHEN Translation_Key ne aktif Locale'de ne de Fallback_Locale'de bulunamadığında, THE t() Fonksiyonu SHALL Translation_Key'in kendisini dize olarak döndürmelidir.
4. THE t() Fonksiyonu SHALL `{variable}` biçiminde tanımlanmış yer tutucuları (interpolation), ikinci argüman olarak geçilen nesnenin karşılık gelen değerleriyle değiştirmelidir.
5. WHEN ikinci argüman sağlanmadığında veya bir yer tutucu için değer eksik olduğunda, THE t() Fonksiyonu SHALL yer tutucuyu olduğu gibi bırakmalı ve hata fırlatmamalıdır.
6. THE t() Fonksiyonu SHALL senkron olarak çalışmalı ve her çağrıda aynı Locale ve aynı anahtar için aynı değeri döndürmelidir (deterministik).

---

### Requirement 3: Locale Durumu Yönetimi (AppContext)

**User Story:** Bir dashboard kullanıcısı olarak, dil değiştiğinde sayfayı yenilemeden tüm arayüzün anında güncellenmesini istiyorum.

#### Acceptance Criteria

1. THE AppContext SHALL `locale` (aktif Locale kodu), `setLocale` (Locale kodu kabul eden ve locale değişimini tetikleyen fonksiyon) ve `t()` fonksiyonunu context değeri olarak sağlamalıdır.
2. WHEN `setLocale` çağrıldığında, THE AppContext SHALL yeni Locale değerini `localStorage`'da `"orion-locale"` anahtarı altında saklamalıdır.
3. WHEN `setLocale` çağrıldığında, THE AppContext SHALL yeni Locale_File'ı asenkron olarak yüklemeli, çeviri deposunu güncellemeli ve tüm bileşenlerin yeniden render edilmesini sağlamalıdır.
4. WHEN yeni Locale_File yükleme işlemi devam ederken, THE AppContext SHALL önceki Locale'in çevirilerini göstermeye devam etmeli ve mevcut sayfayı işlevsel tutmalıdır.
5. WHILE uygulama çalışırken, THE AppContext SHALL Supported_Locales listesinin tamamını context değeri olarak sunmalıdır.

---

### Requirement 4: Locale Kalıcılığı

**User Story:** Bir dashboard kullanıcısı olarak, dil tercihimin tarayıcıyı kapattıktan sonra da hatırlanmasını istiyorum; her oturumda dilin sıfırlanması beni yoruyor.

#### Acceptance Criteria

1. WHEN kullanıcı `setLocale` aracılığıyla bir Locale seçtiğinde, THE I18n_System SHALL seçilen Locale kodunu `localStorage`'da `"orion-locale"` anahtarına yazmalıdır.
2. WHEN dashboard sonraki oturumda yüklendiğinde, THE I18n_System SHALL `localStorage`'dan `"orion-locale"` değerini okumalı ve bu değer Supported_Locales içinde geçerliyse o Locale'i etkin olarak ayarlamalıdır.
3. IF `localStorage`'dan okunan değer Supported_Locales içinde yer almıyorsa, THEN THE I18n_System SHALL bu değeri görmezden gelerek Browser_Locale veya Fallback_Locale belirleme adımlarını uygulamalıdır.
4. WHEN kullanıcı tarayıcı `localStorage`'ını temizlediğinde, THE I18n_System SHALL bir sonraki yüklemede otomatik algılama sürecini (Browser_Locale → Fallback_Locale) yeniden başlatmalıdır.

---

### Requirement 5: Dil Seçici — Settings Sayfası Language Paneli

**User Story:** Bir dashboard kullanıcısı olarak, Settings sayfasında diğer paneller (Admin Authentication, Danger Zone) ile tutarlı bir görünüme sahip bir Language panelinden dil seçmek istiyorum.

#### Acceptance Criteria

1. THE Language_Panel SHALL Settings sayfasında "Admin Authentication" ve "Danger Zone" panelleriyle aynı stil ve düzeni paylaşan ayrı bir kart bileşeni olarak görünmelidir.
2. THE Language_Panel SHALL Supported_Locales içindeki tüm 43 dili seçilebilir şekilde listelemelidir.
3. THE Language_Panel SHALL her dilin kendi dilindeki yerel adını (örn. "Türkçe", "Deutsch", "日本語") göstermelidir.
4. WHEN kullanıcı listeden bir dil seçtiğinde, THE Language_Panel SHALL `setLocale` fonksiyonunu çağırmalı ve tüm arayüzün seçilen dile geçmesini sağlamalıdır.
5. WHEN Locale değiştiğinde, THE Language_Panel SHALL sayfa yenilemesi gerektirmeksizin seçimi anında yansıtmalıdır.

---

### Requirement 6: Sidebar Navigasyon Çevirisi

**User Story:** Bir dashboard kullanıcısı olarak, sol kenar çubuğundaki menü öğelerini (Overview, Virtual Keys, Logs vb.) seçtiğim dilde görmek istiyorum.

#### Acceptance Criteria

1. THE I18n_System SHALL `DashboardLayout.tsx` içindeki `TABS` dizisinde tanımlı tüm sekme etiketlerini Translation_Key karşılıklarıyla çevirmelidir; bu etiketler şunlardır: Overview, Virtual Keys, Logs, Provider Keys, Models, Groups, Playground, Model Info, Settings.
2. THE I18n_System SHALL sidebar alt kısmındaki "Sign Out" buton etiketini de çevirmelidir.
3. WHEN Locale değiştiğinde, THE I18n_System SHALL sidebar etiketlerini sayfa yenilemesi gerektirmeksizin güncellenmiş dile çevirmelidir.
4. WHILE Locale_File yüklenmekteyken, THE I18n_System SHALL sidebar etiketlerini Fallback_Locale değerleriyle göstermelidir.

---

### Requirement 7: Sayfa Metinleri Çevirisi

**User Story:** Bir dashboard kullanıcısı olarak, tüm sayfalardaki başlıkları, alt başlıkları, buton etiketlerini, form etiketlerini, hata mesajlarını ve dialog metinlerini seçtiğim dilde görmek istiyorum.

#### Acceptance Criteria

1. THE I18n_System SHALL aşağıdaki sayfaların tüm statik metin içeriklerini çevirmelidir: Overview, Virtual Keys, Logs, Provider Keys, Models, Groups, Playground, Model Info, Settings.
2. THE I18n_System SHALL her sayfadaki sayfa başlığı, açıklama metni, tablo sütun başlıkları, boş durum metinleri ve buton etiketlerini çevirmelidir.
3. THE I18n_System SHALL `AppContext.tsx` içindeki tüm dialog ve modal başlıklarını, açıklama metinlerini ve buton etiketlerini çevirmelidir (login dialog ve confirm dialog dahil).
4. THE I18n_System SHALL `showToast` çağrılarıyla üretilen bildirimlerdeki statik hata ve başarı mesajlarını çevirmelidir.
5. WHEN bir sayfanın Translation_Key listesinde eksik çeviri bulunduğunda, THE t() Fonksiyonu SHALL ilgili metni Fallback_Locale'deki karşılığıyla göstermelidir.

---

### Requirement 8: Fallback Davranışı

**User Story:** Bir dashboard kullanıcısı olarak, seçtiğim dil dosyasında bazı çeviriler eksik olsa bile arayüzde ham anahtar kodu değil anlaşılır bir metin görmek istiyorum.

#### Acceptance Criteria

1. WHEN aktif Locale_File'da bir Translation_Key bulunamadığında, THE t() Fonksiyonu SHALL Fallback_Locale (`en`) dosyasındaki aynı anahtarı aramalı ve bulursa bu değeri döndürmelidir.
2. WHEN Translation_Key ne aktif Locale'de ne de Fallback_Locale'de bulunmadığında, THE t() Fonksiyonu SHALL Translation_Key'in kendisini döndürmelidir.
3. THE I18n_System SHALL Fallback_Locale dosyasını (`en.json`) uygulama başlangıcında yüklemeli ve tüm oturum boyunca bellekte tutmalıdır.
4. IF aktif Locale, Fallback_Locale ile aynıysa (`en`), THEN THE I18n_System SHALL yalnızca tek bir locale dosyası yüklemeli ve ikinci bir yükleme gerçekleştirmemelidir.

---

### Requirement 9: RTL (Sağdan Sola) Dil Desteği

**User Story:** Arapça, Farsça, İbranice veya Urduca kullanan bir dashboard kullanıcısı olarak, arayüzün metin yönünün kendi dilime uygun şekilde sağdan sola düzenlenmesini istiyorum.

#### Acceptance Criteria

1. THE I18n_System SHALL RTL grubuna ait Locale kodlarını (`ar`, `fa`, `he`, `ur`) tanımlayan sabit bir liste içermelidir.
2. WHEN aktif Locale RTL listesinde yer aldığında, THE I18n_System SHALL `<html>` elementinin `dir` özniteliğini `"rtl"` ve `lang` özniteliğini aktif Locale kodu olarak ayarlamalıdır.
3. WHEN aktif Locale RTL listesinde yer almadığında, THE I18n_System SHALL `<html>` elementinin `dir` özniteliğini `"ltr"` olarak ayarlamalıdır.
4. WHEN Locale değiştiğinde, THE I18n_System SHALL `dir` ve `lang` özniteliklerini sayfa yenilemesi gerektirmeksizin güncel değerlere çevirmelidir.

---

### Requirement 10: Locale Dosyası Yapısı ve Anahtar Şeması

**User Story:** Bir frontend geliştirici olarak, tüm çeviri dosyalarının tutarlı bir anahtar şemasını izlemesini istiyorum; böylece yeni sayfa veya bileşen eklerken hangi anahtarları tanımlamam gerektiğini öngörebilirim.

#### Acceptance Criteria

1. THE I18n_System SHALL tüm Translation_Key'leri `namespace.key` biçiminde organize etmeli; namespace değerleri şunları kapsamalıdır: `nav`, `common`, `auth`, `settings`, `keys`, `logs`, `keyPool`, `models`, `groups`, `playground`, `modelInfo`, `overview`.
2. THE Locale_File SHALL geçerli bir JSON nesnesi olmalı ve Fallback_Locale (`en`) Locale_File'ında tanımlı tüm Translation_Key'leri içermelidir.
3. THE I18n_System SHALL `en.json`'ı tüm Locale_File'lar için referans şema olarak kabul etmeli; diğer dillerde eksik anahtarlar Fallback Davranışı (Requirement 8) kuralları çerçevesinde karşılanmalıdır.
4. WHEN yeni bir sayfa veya bileşen eklendiğinde, THE I18n_System SHALL söz konusu sayfanın tüm statik metinlerinin `en.json`'a eklenmesini zorunlu kılmalıdır; diğer dil dosyaları için bu anahtarlar isteğe bağlı olarak eklenebilir.

---

### Requirement 11: lib/i18n.ts Modülü

**User Story:** Bir frontend geliştirici olarak, locale algılama ve çeviri işlemlerinin tek bir modülde toplanmasını istiyorum; böylece bağımlılıkları net ve test edilebilir tutabilirim.

#### Acceptance Criteria

1. THE I18n_System SHALL `dashboard/lib/i18n.ts` dosyasında tanımlanmalı ve şu dışa aktarımları içermelidir: `SUPPORTED_LOCALES`, `detectLocale()`, `loadLocale(lang: string)`, `createTranslator(translations, fallback)`.
2. THE `detectLocale()` fonksiyonu SHALL önce `localStorage["orion-locale"]`'i, ardından `navigator.language`'i kontrol etmeli, Supported_Locales ile eşleştirmeli ve geçerli bir Locale kodu veya `"en"` döndürmelidir.
3. THE `loadLocale(lang)` fonksiyonu SHALL `/dashboard/locales/{lang}.json` adresine `fetch` isteği atmalı ve çözümlenmiş JSON nesnesini içeren bir Promise döndürmelidir.
4. THE `createTranslator(translations, fallback)` fonksiyonu SHALL aktif ve fallback çeviri nesnelerini kapatan bir closure döndürmeli ve bu closure `t(key, vars?)` imzasına sahip olmalıdır.
5. THE `loadLocale()` fonksiyonu SHALL aynı Locale için birden fazla eş zamanlı çağrıda tekrarlı ağ isteği yapmamak amacıyla yükleme süresince isteği önbelleğe almalıdır (in-flight deduplication).
