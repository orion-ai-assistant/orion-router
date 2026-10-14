# Medya arşivi

Sol menüde Ayarlar'ın üstündeki **Arşiv** sayfası ses/görsel/video/belge sekmelerini,
yerel takvim günleriyle tarih aralığı filtresini ve tek dosya silmeyi içerir.
Sıralama `created_at DESC, id DESC`; bitiş günü filtreye dahildir. Tekilleştirilen
dosyalarda tarih, ilk arşivlenme tarihidir; her yeniden kullanım yeni kayıt yaratmaz.
Tarih seçimi istatistiklerdeki `DateRangeFilter` bileşeniyle ortaktır: günlük,
haftalık, aylık, tümü ve özel aralık seçenekleri aynı davranır. Seçili medya sekmeleri
ve ekler gri Router panel stili kullanır.

## Video

CHAT loglarının bağımsız JSON kopyalarında `input_video`, `video_url`, MIME etiketli
`inlineData/inline_data` ve `video_base64` alanları tanınır. Orijinal dosya Base64'ten
çözülür, SHA-256 ile `router_video_archives.video BYTEA` içinde tek kopya saklanır.
`ON CONFLICT DO NOTHING` ve ayrı SELECT eşzamanlı eklemeleri güvenli karşılar.
ffprobe yalnızca başlık/akış bilgisi okur; format, MIME, bayt boyutu, boyutlar ve
varsa süre tutulur. Yeniden kodlama, kare çıkarma veya kalite değişikliği yoktur.
Sağlayıcıya giden payload değişmez. URL indirme ve eski log göçü yapılmaz.

En fazla iki eşzamanlı çözme/probe işi ve dosya başına 100 MiB sınırı vardır.
Base64, ffprobe, kaynak sınırı veya DB hatasında orijinal inline değer logda kalır.
Probe işi ana event loop dışındaki iş parçacığında, 25 saniyelik timeout ile çalışır.
Yalnızca kendine yeterli video kapsayıcıları ve pipe protokolü kabul edilir.

## PDF, TXT ve notlar

`router_document_archives.document BYTEA` dosya içeriğini SHA-256 ile tek kopya saklar.
Girdi/çıktı log kopyalarında `input_file/file.file_data`, Claude `document.source`,
Gemini `inline_data/inlineData` ve MIME etiketli ekler desteklenir. Hub'ın açık
`Ek N — Metin dosyası: ad\n<file_content>\niçerik\n</file_content>` bloğu da dosya
olarak tanınır. Bu biçimdeki metin UTF-8 baytlarıyla saklanır; normal sohbet, araç
çıktısı veya rastgele Base64 metin dosyaya dönüştürülmez. Boş notlar desteklenir.

Gerçek PDF baytları gelirse aynen saklanır. İstemci PDF/DOCX gibi bir dosyadan yalnızca
çıkarılmış metni yollarsa orijinal dosya yeniden oluşturulmaz: `representation=text`
ve metin MIME'ıyla saklanır; arayüz bunu açıklar, indirme adına `.txt` ekler.
`/v1/files` üzerinden yüklenen PDF/TXT'nin orijinal baytları da upstream yükleme başarılı
olduktan sonra arka planda arşivlenir. Provider'ın yanıtı ve file URI'si değiştirilmez.
URI ile sonraki chat isteği yalnızca sağlayıcı referansını taşıyorsa bu URI indirilmez;
dosya bağımsız Arşiv listesinden erişilebilir.

Belge başına 32 MiB ve dört eşzamanlı arşiv işi sınırı vardır. Çözme, DB veya kaynak
sınırı hatasında CHAT logundaki orijinal ek aynen korunur; multipart yükleme yanıtı
da arşiv hatasından etkilenmez. Dosya adları hash'e dahil değildir. Arşiv satırı ilk
adı, log referansı o gönderimdeki adı tutar. Metin ekleri ayrıca prompt kopyalamaz;
dosyanın kendi içeriği saklanır.

Belge önizlemesinde metin React metin düğümü olarak gösterilir; HTML çalıştırılmaz.
Önizleme ilk 256 KiB ile sınırlıdır, indirme tam dosyadır. PDF için yerel blob URL'si
üzerinden açma/indirme sağlanır. Diğer ikili dosyalar indirilir. Dosya endpoint'i
`Content-Disposition: attachment`, `nosniff` ve sandbox CSP kullanır; HEAD BYTEA okumaz.

## Adlar, içerik ve silme

Dosyanın açık `filename/file_name/original_filename` bilgisi veya doğrudan önceki
`Ek N — Görsel/Ses/Video: dosya.ext` etiketi kullanılır. Yol ve kontrol karakterleri
ayıklanır. Normal prompt dosya adına dönüştürülmez. Ad verilmemişse arayüz yedek ad
gösterir. Log referansındaki ad her kullanım için ayrıdır; arşiv ilk görülen adı tutar.
Görsel/video arşivi prompt tutmaz. TTS'nin eski `tts_text` kolonu kaldırılır; yeni TTS
arşivi de metin kopyalamaz. Prompt normal istek logunun parçası olmaya devam eder.

Ekler penceresinin dış ölçüleri ve önizleme alanı sabittir. Seçilen dosya yüklenirken
alan korunur; görsel/video bu alana oranı korunarak sığdırılır. Yalnızca seçilen
dosya yetkili fetch ile alınır. Dosya değişince/kapanınca blob URL temizlenir.
Yalnız ses içeren pencereler kompakt ve koyu oynatıcı kullanır; tek dosyada boş yan
liste gösterilmez. Karışık eklerde seçim değişirken pencere boyutu sabit kalır.

Log silmek arşivi silmez. Arşivde **Sil** dosyayı kalıcı kaldırır; aynı dosyayı kullanan
bütün logların önizlemesi 404 döndürür, log JSON'u silinmez. Onay penceresi bunu açıklar.
Aynı dosya daha sonra yeniden gönderilirse yeni arşiv ID'siyle tekrar kaydedilir;
eski log referansları otomatik değiştirilmez. Otomatik silme/retention yoktur.

Admin endpoint'leri:

- `GET /dashboard/api/media-archives/{audio|image|video|document}?start=...&end=...&limit=30&offset=0`
- `DELETE /dashboard/api/media-archives/{audio|image|video|document}/{id}`
- `GET|HEAD /dashboard/api/video-archives/{id}/video` (GET Range destekler)
- `GET|HEAD /dashboard/api/media-archives/document/{id}/file` (GET Range destekler)

Tarihler timezone içeren ISO-8601 değerleridir; bitiş üst sınırı hariçtir. Arayüz
seçilen bitiş gününün ertesi yerel gece yarısını gönderir. Liste sorguları BYTEA ve
prompt getirmez. Güncelleme için backend yeniden başlatılmalı ve dashboard derlenmelidir.

Testler: `test_document_archive.py`, `test_video_archive.py`, `test_image_archive.py`, `test_tts_archive.py`,
`test_log_attachments.cjs` ve dashboard üretim derlemesi. PostgreSQL testleri yalnızca
`ORION_IMAGE_TEST_PORT` ile gösterilen geçici cluster'da rastgele şemalar kullanır.
