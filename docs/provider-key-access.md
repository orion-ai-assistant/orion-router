# Sağlayıcı anahtarı izinleri

Router dashboard → Anahtar havuzu → Düzenle → Anahtar izinleri, sağlayıcı
anahtarının A katmanını düzenler. `all` gelecekteki sanal anahtarları kapsar;
`selected` boş listeyle hiç kimseyi kapsamaz. Aynı etiket kullanılabilir.

Sanal anahtarlar → Düzenle → Anahtar izinleri, B katmanını düzenler.
`unrestricted` varsayılandır; `only_selected` gelecekte eklenen sağlayıcı
anahtarlarını kapsamaz. Etkin izin A **ve** B'dir. B ekranından A genişletilemez.
Kişisel kayıtların A katmanı her zaman sahibidir; B bunları da daraltabilir.
Kararlar her rota/deneme öncesinde veritabanından okunur.

Hub yönetimi sanal anahtarlar ekranındadır. İsimler yalnız görüntüleme içindir;
Hub UUID ve sanal anahtar UUID yetki ve raporların kimliğidir. Hub kapatma ve
anahtar kapatma, yeniden eşleştirmeyle sıfırlanmaz. Bağımsız sanal anahtarların
Hub'a ihtiyacı yoktur.

Kişisel anahtar yönetimi anahtar havuzu ekranındadır. Yönetici yeni değer
yazabilir, kaydı etkin/pasif yapabilir veya silebilir. Ham sır geri dönmez.
Kullanıcının yazması pasif kaydı etkinleştirmez; pasif kişisel kayıt ortak
faturalandırmaya düşmez. Kullanıcı pasif kaydı kaldırarak bu kararı aşamaz.

Sanal anahtar oluşturma artık önceden oluşturulmuş `sk-orion-…` değerinin
yazılmasını ister: yalnız hash kaydedilir, oluşturma yanıtında sır dönmez.
Hub hesap anahtarları mevcut deterministik yöntemle otomatik oluşturulur.

Yerel motorlar sağlayıcı anahtarı tüketmez. Admin/system çağrıları ortak havuzu
kısıtsız kullanabilir; eski yapılandırma/ortam anahtarları yalnız system
çağrılarında kullanılabilir. Kullanıcı çağrısı bu yollara düşmez. Router kimlik
doğrulama sırrı upstream anahtar olarak gönderilmez.

Hub/Flutter özeti yalnız doğrulanmış hesap anahtarıyla sorgulanır. `all` ve
birden fazla sanal anahtara seçili kayıtlar ortak; yalnız bu hesaba seçili
kayıtlar ve kişisel kayıtlar size özel sayılır. Yalnız etkin A ve B geçen
kayıtlar sayılır. Başka hesapların kayıt kimliği veya metadata'sı dönmez.
Birden fazla bağlı Router desteklenir; kişisel form hedef Router'ı seçebilir.

`GET /dashboard/api/usage` yöneticiye tüm geçmiş üzerinden özet ve günlük UTC
grafiği döner. Filtreler: `start` (dahil), `end` (hariç), `hub_id`, `key_id`,
`provider`, `model`, `upstream_key_id`. Tarihler saat dilimi içermelidir.
Gruplar işlem türü ve birimle ayrılır; eksik usage/maliyet NULL olarak kalır.
STT süreleri ve TTS karakterleri LLM tokenlarına eklenmez.
`GET /dashboard/api/logs?limit=100&offset=0` ayrı sayfalı istek listesidir.

İstek anındaki upstream anahtar UUID/kaynağı context üzerinden telemetry'ye
aktarılır. Sanal anahtar ve Hub UUID kayda kopyalanır, silmeler rapor geçmişini
korur. Eski upstream kaynakları veya birimleri güncel ayarlardan tahmin edilmez.
Migrasyon eski ortak kayıtları `all`, sanal kayıtları `unrestricted` yapar;
kimlik, bütçe ve geçmiş korunur. Eski config havuzu bir kez taşınır.

Regresyonlar `dev/test-orion-router/test_key_policy.py` içindedir. PostgreSQL
testleri rastgele geçici şema ve transaction rollback kullanır; üretim verisine
yazmaz. Önceki Hub testlerinden HTTP varsayımlı bağlantı/adres ve eski session
mock'u kullanan katalog testleri bu değişikliklerden önce de başarısızdır.
