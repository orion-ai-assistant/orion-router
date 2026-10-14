# Router görsel log arşivi

Bu özellik yalnızca **chat loglarının saklanmasını** değiştirir. İstemci → Hub → Router →
sağlayıcı payload'ı, mesaj metinleri, STT ve embedding kayıtları değişmez.

## Saklama

Log yazılırken bağımsız JSON kopyasındaki görsel alanları incelenir. Data URL veya düz
Base64 çözülür, dosyanın SHA-256 özeti hesaplanır. `router_image_archives` tablosunda:

- benzersiz SHA-256 ve arşiv kimliği;
- orijinal dosya `BYTEA NOT NULL`;
- dosyadan belirlenen MIME/format, bayt boyutu, başlık genişlik/yüksekliği ve tarih bulunur.

`ON CONFLICT (sha256) DO NOTHING` sonrasında mevcut kimlik okunur. Aynı dosyanın data URL
veya düz Base64 olarak, farklı loglarda veya aynı anda gelmesi yeni kopya üretmez. Görselin
yeniden kodlanmış başka bir dosyası farklı baytlara sahipse farklı arşiv kaydıdır.

Pillow `Image.open()` ile dosya tanımlanır ve başlık ölçüleri okunur; piksel yükleme,
yeniden kodlama, boyut küçültme veya ZIP uygulanmaz. PNG/JPEG/WebP/GIF ve kurulu Pillow'un
desteklediği BMP/TIFF/ICO/AVIF başlıkları kabul edilir. Metadata'daki MIME yerine dosyanın
gerçek biçimi kullanılır. EXIF yönlendirmesi uygulanmaz; ölçüler dosya başlığındaki ölçülerdir.
Desteklenmeyen veya başlığı okunamayan görseller eski Base64 haliyle loglanır.

Log kopyasında yalnızca görselin bulunduğu değer değiştirilir. Örneğin:

```json
{
  "type": "image_url",
  "image_url": {
    "url": {
      "image_archive_id": 42,
      "sha256": "…",
      "mime_type": "image/png",
      "format": "png",
      "size_bytes": 102400,
      "width": 800,
      "height": 600
    },
    "detail": "high"
  }
}
```

Bu bir **log gösterimidir**; sağlayıcıya bu referans nesnesi gönderilmez. Sağlayıcı özgün
Base64 isteğini alır. OpenAI/Hub `image_url`, `input_image`, Claude `source` ve Gemini
`inline_data/inlineData` biçimleri ile açık görsel/ek listeleri tanınır. Normal metin
alanları Base64 gibi görünse bile değiştirilmez. HTTP(S) görsel URL'leri aynen kalır;
Router bunları indirip arşivlemez.

Başlangıç logu, yerel sağlayıcının payload güncellemesi, normal/final log INSERT ve UPDATE
yolları aynı politikayı kullanır. Birden fazla yazım aynı hash için aynı kaydı kullanır.

## Hata davranışı ve saklama ömrü

Çözme, başlık okuma veya DB yazımı başarısız olursa ilgili Base64 alanı değiştirilmez.
Diğer geçerli görseller yine arşivlenebilir. Sunucu loguna payload içermeyen hata türü
yazılır. Arşiv hatası sağlayıcı isteğini başarısız yapmaz; mevcut genel anahtar redaksiyonu
politikası loglara uygulanmaya devam eder.

Bellek koruması için görsel başına 32 MiB ve backend süreci başına 4 eşzamanlı görsel işi
sınırı vardır. Sınır aşılırsa görsel düşürülmez; orijinal Base64 logda kalır. Sınırsız
arşiv iş kuyruğu veya yeniden deneme mekanizması yoktur. Bu sınırlar saklama süresi değildir.

Görsel tablosu loglara bağlı bir FK içermez; log temizlendiğinde görseller korunur.
TTL, referans sayacıyla silme, otomatik temizlik ve retention eklenmedi. Başarılı arşiv
INSERT'inden sonra log yazımı başarısız olursa arşiv kaydı kalabilir. Sonradan kullanılmayan
arşivleri silmek ayrı bir politika kararıdır.

Eski Base64 loglar değiştirilmez; göç yapılmaz. Tam PostgreSQL yedeği yeni tabloyu ve
sequence'ini de kapsar. Seçici yedeklerde `router_image_archives` ve
`router_image_archives_id_seq` dahil edilmelidir.

## API ve dashboard

TTS arşiviyle aynı admin doğrulaması (`X-Admin-Key`) ve fetch→blob yaklaşımı kullanılır:

- `GET /dashboard/api/image-archives?limit=50&offset=0`: dosya baytları olmadan arşiv
  metadata listesi, toplam benzersiz görsel sayısı ve toplam dosya baytı.
- `GET /dashboard/api/image-archives/{id}/image`: dosyanın orijinal baytları ve gerçek MIME.
- `HEAD /dashboard/api/image-archives/{id}/image`: dosya baytlarını okumadan başlıkları.

Yanıtlar `private, no-store`, `nosniff` ve sandbox CSP başlıkları taşır. Arşiv rotaları
dashboard'un statik catch-all rotasından önce kayıtlıdır. Kimliksiz erişim reddedilir.

Log detayında her görselin önizleme düğmesi vardır. Yeni arşiv dosyası ancak düğmeye
basılınca yetkili fetch ile indirilir; blob URL bileşen kapanınca geri alınır. Eski inline
Base64 görseller de düğmeyle görüntülenebilir. Harici URL'lere otomatik görsel isteği
yapılmaz. Bağımsız görsel arşivi listesi loglar temizlendikten sonra da erişim sağlar.

Pillow backend bağımlılığı `pyproject.toml` dosyasına eklidir. Mevcut kurulumda Python
bağımlılıklarını güncelleyin ve backend'i yeniden başlatın; tablo normal başlangıç
akışında oluşturulur. Dashboard üretim çıktısı yeniden derlenmelidir.

## Testler

Log detayındaki **Ekler** düğmesi, istek ve yanıttaki görsel/ses/video eklerini
girdi/çıktı etiketiyle ayrı pencerede gösterir. Yalnızca seçilen arşiv dosyası
yetkili endpoint'ten yüklenir; önizleme kapanınca blob URL'si serbest bırakılır.
Eski inline Base64 görsel, ses ve video logları da desteklenir. Video ve giriş
sesinin depolama biçimi bu değişiklikle değiştirilmez: mevcut log içeriği kullanılır,
videoya yeni bir BYTEA arşivi veya yeniden kodlama eklenmez. Uzak bağlantılar otomatik
indirilmez; kullanıcı bağlantıyı açabilir. Tarayıcının desteklemediği formatlarda
orijinal dosyayı indirme seçeneği bulunur. Bağımsız görsel ve TTS ses listeleri
Loglar sayfasındaki **Medya arşivi** düğmesinden açılır.

```powershell
.venv/Scripts/python.exe -m unittest discover -s dev/test-orion-router -p test_image_archive.py -v
node --test dev/test-orion-router/test_log_images.cjs
node --test dev/test-orion-router/test_log_attachments.cjs
```

PostgreSQL entegrasyon testleri için üretim DB'si kullanılmaz. `ORION_IMAGE_TEST_PORT`,
localhost üzerinde `postgres` kullanıcısı/veritabanıyla çalışan, yalnızca test için açılmış
PostgreSQL örneğine ayarlanır. Testler rastgele şemalar oluşturup kaldırır:

```powershell
$env:ORION_IMAGE_TEST_PORT='65439'
.venv/Scripts/python.exe -m unittest discover -s dev/test-orion-router -p test_image_archive.py -v
```

Kontroller: orijinal bayt/ölçü korunması, data URL/düz Base64 ve farklı payload biçimleri,
eşzamanlı hash çakışması, normal metin ve URL'lerin korunması, kısmi hata fallback'i,
arşiv tablosu yokken logun korunması, STT/embed/TTS kapsamının değişmemesi, sağlayıcıya
orijinal mesajların ulaşması, log temizleme sonrası arşiv erişimi, admin GET/HEAD ve
gerçek uygulamadaki route sırası. Dashboard ayrıştırma ve üretim derlemesi ayrıca doğrulanır.
