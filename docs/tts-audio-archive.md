# TTS ses arşivi — ilk aşama

Yeni TTS kayıtlarının sesi `router_request_logs.response_json` içinde Base64 olarak tutulmaz.
WAV/PCM kopyası 32 kbps hedefli mono Ogg/Opus'a kodlanır; mevcut MP3, AAC, Opus,
Vorbis ve FLAC dosyaları yeniden kodlanmadan binary olarak saklanır. Ogg kapsayıcısındaki
codec ffprobe ile okunur. Canlı TTS çıktısı ve örnekleme hızı değiştirilmez.

`router_tts_audio_archives` aynı PostgreSQL veritabanında bulunur. `audio BYTEA NOT NULL`
alanı `STORAGE EXTERNAL` kullanır. Kaynak ve arşiv örnekleme hızları ayrı alanlardadır.
Satır ancak encoder kapanıp dosyanın tamamı decode edilerek süre/bütünlük kontrolünden
geçince tek INSERT ile oluşur. PCM kaynak süresiyle arşiv süresi en fazla 100 ms sapabilir.
Tamamlanmış üretimde eksik WAV/veri veya yarım PCM frame hata sayılır; erken kesilmiş
üretimde son eksik frame atılarak eldeki tam ses örnekleri kapatılır.

Arşivler süresiz saklanır. `log_id` bağlantısı `ON DELETE SET NULL` kullanır; log silme
ile arşiv INSERT'i yarışırsa satır kilidiyle sıralanır, log zaten silinmişse arşiv bağlantısız
oluşur. Sağlayıcı, istenen/çözümlenen model, üretim tarihi, metin ve `completed/interrupted`
durumu arşivde kalır. TTL, kapasite dolunca silme veya otomatik temizlik yoktur.

## Kaynak sınırları ve hata davranışı

- Her backend süreci en fazla 4 arşiv işi kabul eder. Doluysa yeni ses canlı olarak
  gönderilir, yalnızca arşiv başarısız olur. Çoklu worker dağıtımında toplam sınır worker
  sayısıyla çarpılır; toplam CPU/RAM buna göre boyutlandırılmalıdır.
- Her işin ham girdi kuyruğu en fazla 2 MiB / 4096 parçadır. Encoder geride kalırsa
  kuyruğun taşması arşivi başarısız yapar; canlı üretici encoder'ı beklemez.
- Arşiv çıktısının bellek tavanı 64 MiB'dır. Bu bir bellek korumasıdır; 30 dakika
  veya başka bir kayıt süresi sınırı değildir. Sıkıştırılmış dosyaları kopyalama yolu
  da aynı tavana tabidir. Bellekte doğrulama/DB yazımı sırasında sınırlı ek kopyalar bulunabilir.
- Windows'taki subprocess başlatma maliyetinin canlı event loop'u durdurmaması için her
  kabul edilen arşivin ayrı bir iş parçacığında çalışan async event loop'u vardır.
  FFmpeg stdin/stdout/stderr pipe'ları asenkron tüketilir. Backend Node'a bağımlı değildir.
- FFmpeg yazma/sonlandırma ve decode işlemlerinde takılan süreçleri sınırlayan işlem
  zaman aşımı vardır; ses üretiminin toplam süresini kesen zaman aşımı yoktur.
- Hatalar sunucu logunda ve request logunun `archive_error` alanında görünür. Arşiv satırı
  oluşturulmaz; kaynak ses saklanmadığından tekrar deneme garantisi yoktur.
- Ani süreç kapanışında yarım arşiv kaybolabilir. Geçici ses dosyası, açılış taraması,
  yarım Ogg kurtarma veya sahiplik/kilit sistemi yoktur. Normal kapanış bekleyen işleri tamamlar.

WAV başlığı gerçek formatı tanımlar. Ham Gemini PCM metadata'sı sağlayıcının inline MIME
bilgisinden, OpenAI PCM biçimi sağlayıcının sabit çıktı sözleşmesinden alınır. Yerel servis
ham PCM veriyorsa `X-Audio-Sample-Rate` (veya `X-Sample-Rate`), `X-Audio-Channels` ve
`X-Audio-Format` (`s16le`, `f32le` vb.) başlıklarını sağlamalıdır. Bunlar yoksa format
tahmin edilmez ve arşiv hatası raporlanır. Normal yerel WAV yanıtında bu başlıklar gerekmez.

## Kurulum ve operasyon

Native kurulum `python -m bin.ffmpeg_install` çalıştırır. Windows x64 için FFmpeg'in
[önerdiği dağıtıcılardan](https://ffmpeg.org/download.html) BtbN'in sürüm dalındaki paketi
GitHub SHA256 digest'iyle doğrulanır; yalnızca FFmpeg/ffprobe `tools/ffmpeg/bin` altına çıkarılır.
macOS Homebrew, Debian/Ubuntu apt ve dnf bulunan sistemlerde native paket yöneticisi kullanılır.
Paketin libopus içermediği veya platformun desteklenmediği durumda kurulum açık hatayla durur.
Windows ARM64 için uygun native binary kurularak yollar açıkça verilmelidir.

Özel yollar `ORION_FFMPEG` ve `ORION_FFPROBE` ortam değişkenleriyle seçilebilir. Backend
açılışında sürüm, çalıştırılabilir platform uyumu ve libopus kontrol edilir; başarısızsa
canlı TTS çalışmaya devam eder ve arşiv hataları görünür olur. Docker zaten FFmpeg kurar.
Encoder seçenekleri [FFmpeg libopus belgelerine](https://ffmpeg.org/ffmpeg-codecs.html#libopus)
göre ayarlanmıştır; 32 kbps bir hedeftir, değişken bit oranı ve Ogg overhead'i vardır.

Admin API:

- `GET /dashboard/api/audio-archives?limit=50&offset=0`: ses payload'ı olmadan arşiv listesi.
- `GET|HEAD /dashboard/api/audio-archives/{id}/audio`: mevcut `X-Admin-Key` doğrulaması,
  GET için tek byte Range, 206 ve 416, `Accept-Ranges`, `Content-Range`, `Content-Length`.
  HEAD tam GET temsilinin başlıklarını döner. Çoklu/geçersiz Range yok sayılıp tam yanıt verilir.
- `GET /dashboard/api/audio-archives/status`: encoder durumu, DB'nin ayırdığı arşiv alanı,
  loglarda kayıtlı arşiv hataları ve yerel PostgreSQL sunucusunda okunabiliyorsa boş disk alanı.

Disk 1 GiB veya %5'in altına indiğinde dashboard uyarır; otomatik silme yapmaz. PostgreSQL
uzak sunucudaysa veya dosya sistemi bilgisi okunamıyorsa boş alan gösterilmez; sunucu disk
izlemesi ayrıca kurulmalıdır. DB INSERT/disk dolu hataları da request metadata'sına yazılır;
DB log yazımını da reddediyorsa sunucu logu elde kalan hata kanalıdır.

Dashboard log detayında ve açılır ses arşivi listesinde oynatma düğmesi bulunur. Yeni ses
ancak düğmeye basılınca `adminFetch` ile indirilip blob URL olarak açılır. Tarayıcı bu yolda
sunucu Range istekleriyle seek yapmaz; indirilmiş küçük dosyada seek yapar. Blob URL bileşen
kapanınca geri alınır, devam eden fetch iptal edilir. Eski Base64 log oynatması korunur.

Tam PostgreSQL `pg_dump -Fc` yedeği yeni tabloyu, TOAST verisini, indeksleri ve sequence'i
otomatik içerir. Seçici yedekleme kullanılıyorsa `router_tts_audio_archives` tablosu,
`router_tts_audio_archives_id_seq` sequence'i ve bağımlı log şeması da dahil edilmelidir.
Yedekleme/geri yükleme öncesi kapasite planına WAL, TOAST, indeksler ve yedek boyutu eklenmelidir.

Örnek tam yedek/geri yükleme (kimlik bilgileri güvenli ortamdan sağlanır):

```sh
pg_dump -Fc -h DB_HOST -U DB_USER -d DB_NAME -f orion-router.dump
pg_restore --no-owner -h DB_HOST -U DB_USER -d EMPTY_RESTORE_DB orion-router.dump
```

## Ölçüm — 14 Ekim 2026, Windows x64 / PostgreSQL 16.3

`dev/benchmark_tts_archive.py --write-audio` mevcut loglardan gerçek Gemini ve yerel TTS
örneğini salt okunur alır. Ayrı, rastgele adlı test şemasında üretim INSERT yolunu, gerçek
log temizleme fonksiyonunu, log zaten silinmişken arşiv INSERT'ini ve pg_dump/pg_restore
ile satırların birebir korunmasını doğrular; test şemasını sonra kaldırır.
Kaynak loglar ve Base64 alanları değiştirilmez. Dinleme çiftleri ve ayrıntılı JSON raporu
`scratch/tts-archive-benchmark` altındadır. Benchmark, native PostgreSQL araçlarını gerektirir.

| Örnek | Kaynak WAV | Base64 | Opus | Kaynak / arşiv süre |
| --- | ---: | ---: | ---: | ---: |
| Gemini, log 4088, 24 kHz | 601.004 B | 801.340 B | 49.917 B | 12,52 / 12,52 sn |
| Yerel, log 4885, 24 kHz | 244.364 B | 325.820 B | 20.390 B | 5,09 / 5,09 sn |

Bu iki örnekte `pg_column_size` eski JSON için 801.483 / 325.963 B, arşiv BYTEA için
49.917 / 20.390 B ölçüldü. Küçük izole örnek kümesinin TOAST ve indeks dahil ayrılmış
ilişki alanı eski JSON tablosunda 1.245.184 B, arşiv tablosunda 253.952 B oldu.
Testteki silinmiş satırlar/ayrılmış sayfalar bu sayılara dahildir; üretim DB'si için sabit
tasarruf oranı veya dosyanın kendiliğinden küçüleceği vaadi değildir.

FFmpeg'in kendi `-benchmark` çıktısında encode CPU (user+system) Gemini için yaklaşık
156 ms, yerel örnek için 47 ms; tam decode doğrulaması yaklaşık 16 / 32 ms ölçüldü.
ffprobe CPU bu sayılara dahil değildir. Python kontrolü, süreç başlatma ve doğrulama dahil
işin toplam bitişi yaklaşık 2,16 / 2,09 sn sürdü; canlı yanıt bu işi beklemez.
Eşzamanlı 5 ms event-loop probunda en yüksek ek gecikme yaklaşık 11,6 / 11,2 ms idi.
Bu bir yerel sentetik event-loop ölçümüdür; gerçek sağlayıcıdan istemciye canlı TTS
gecikmesinin uçtan uca ölçümü değildir. Özellikle Windows süreç başlatma maliyeti ve bu
makinedeki diğer işler nedeniyle CPU ve duvar saati sonuçları farklı ortamlarda değişir.

Otomatik kontroller: normal/erken kesilen/non-stream kayıt, 24/48 kHz kaynak, 5 MB üzeri
ham ses, 1.801 saniyelik kayıt, PCM frame/WAV kesilmesi, farklı sıkıştırılmış codec'lerin
binary korunması, encoder/DB hataları ve bellek/eşzamanlılık sınırları; yetkisiz GET/HEAD,
Range ve log temizleme sonrası bağımsız erişim. Dashboard TypeScript ve üretim derlemesi geçti.

**Açık doğrulamalar:** öznel dinleme kalitesi ve hedef tarayıcılarda gerçek oynatma/seek.
Windows computer-use mevcut tarayıcı URL'sini güvenilir belirleyemediği için UI testi durdu.
Manuel kontrol için `python dev/serve_tts_archive_preview.py`, sonra
`http://127.0.0.1:8879/test` ve `/dashboard/logs` açılabilir. Bu yalnızca yerel fixture'dır;
üretim DB'sine bağlanmaz, test admin anahtarı `fixture-key`'dir. Gemini/yerel fetch→blob
oynatma ve ileri sarma düğmeleri sonucu JSON olarak aynı scratch klasörüne kaydeder.
Eski Base64 ve yeni arşiv logları dashboard fixture'ında yan yana bulunur. API Range
testlerinin geçmesi tek başına codec/tarayıcı uyumluluğunu kanıtlamaz.

## İkinci aşama

Eski Base64 göçü bu aşamada uygulanmadı. Dinleme, tarayıcı ve canlı gecikme doğrulamaları
tamamlandıktan sonra küçük gruplu, tekrar çalıştırılabilir göç ayrı uygulanmalıdır.
Arşiv commit edilip decode/süre/bütünlük kontrolünden geçmeden eski veri kaldırılmamalıdır;
başarısız kayıtların Base64 verisi korunmalıdır. Kayıplı dönüşümde byte eşitliği aranmaz.
Göç sonrası alan geri kazanımı için PostgreSQL bakımı ayrıca planlanmalıdır.
