# Sağlayıcı anahtarı izinleri

Router dashboard → Anahtar havuzu → Düzenle → Anahtar izinleri, sağlayıcı
anahtarının A katmanını düzenler. `all` gelecekteki sanal anahtarları kapsar;
`selected` boş listeyle hiç kimseyi kapsamaz. Aynı etiket kullanılabilir.

Sanal anahtarlar → Oluştur/Düzenle → Anahtar izinleri, B katmanını düzenler.
`unrestricted` varsayılandır; `only_selected` gelecekte eklenen sağlayıcı
anahtarlarını kapsamaz. Etkin izin A **ve** B'dir. B ekranından A genişletilemez.
Kişisel kayıtların A katmanı her zaman sahibidir; B bunları da daraltabilir.
Oluşturma ve düzenleme formlarındaki izin seçimi taslaktır; formun ana Kaydet
veya Oluştur düğmesi alanları ve izinleri tek transaction içinde kaydeder.
Geçersiz izin seçimi anahtar oluşturmayı ve alan güncellemelerini de geri alır.
Ayrı bir izin kaydetme düğmesi yoktur; seçili anahtar sayısı panelin üstündedir.
Kararlar her rota/deneme öncesinde veritabanından okunur.

Hub yönetimi sanal anahtarlar ekranındadır. İsimler yalnız görüntüleme içindir;
Hub UUID ve sanal anahtar UUID yetki ve raporların kimliğidir. Hub kapatma ve
anahtar kapatma, yeniden eşleştirmeyle sıfırlanmaz. Bağımsız sanal anahtarların
Hub'a ihtiyacı yoktur. Dashboard kısa UUID kodlarını isimlere eklemez;
filtreler ve API yine UUID kullanır. Hub yönetiminin sayısı yalnız panel açıkken
` · sayı` olarak gösterilir; burada sanal anahtar listesi tekrarlanmaz. Sanal
anahtar tablosu Hub veya anahtar adıyla aranabilir.

Anahtar havuzu varsayılan olarak Ortak sağlayıcılar sekmesini açar.
Kişisel sağlayıcı anahtarları sekmesinde arama ve sanal anahtar UUID üzerinden
kullanıcı filtresi bulunur; seçeneklerde kullanıcı ve Hub adları gösterilir.
Her iki sekme aynı sağlayıcı listesi bileşenini kullanır: sürükleme, yukarı/aşağı
sıralama ve Düzenle düğmesi. Kişisel kayıtlarda fazladan Kişisel etiketi yoktur.
Yönetici düzenleme formundan yeni değer yazabilir, kaydı etkin/pasif yapabilir
veya silebilir. Ekleme her iki sekmede açıktır; sahip olarak ortak havuz veya
bir sanal anahtar hesabı seçilebilir. Hesap ve sağlayıcı başına tek kişisel
kayıt sınırı korunur; ikinci oluşturma mevcut kaydı değiştirmeden reddedilir.
Kişisel sıralama `router_user_provider_keys.priority` alanında tutulur.
Ham sır geri dönmez.
Kullanıcının yazması pasif kaydı etkinleştirmez; pasif kişisel kayıt ortak
faturalandırmaya düşmez. Kullanıcı pasif kaydı kaldırarak bu kararı aşamaz.

Dashboard sanal anahtar oluştururken ad, bütçe ve isteğe bağlı izin seçimi sunar. Tarayıcı
`crypto.getRandomValues` ile 256 bit rastgele `sk-orion-…` anahtarı üretir ve
yazma amaçlı API isteğine ekler. Başarılı kayıt sonrası bir kez gösterilir ve
ortadaki Anahtarı kopyala ve kapat düğmesiyle kopyalanabilir; başarılı
kopyalama pencereyi kapatır. Kopyalama başarısızsa anahtar görünür kalır.
Kapatma veya oturum değişiminde temizlenir. Yalnız hash
kaydedilir; API yanıtları ve listeleri anahtarı geri döndürmez. API üzerinden
oluşturma yapan istemciler kendi ürettikleri `api_key` değerini gönderir.
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

Kullanım istatistikleri Genel Bakış'taki açılır kullanım panelindedir; Hub,
kullanıcı, sağlayıcı ve tarih aralığı filtreleri burada kullanılır. Sanal anahtar
düzenleme formundaki kısayol, bu paneli ilgili kullanıcı seçili olarak açar.
Üstteki mevcut genel toplam kartları bu panelin filtrelerinden bağımsızdır.
İşlem türü başına tek özet kartı gösterilir; birimi boş eski kayıtlar aynı
işlem türünün istek ve token toplamlarına eklenir. Farklı kullanım birimleri
ayrı tutulur. Günlük grafikte aynı gün ve işlem türünün istekleri toplanır;
sohbet mor, TTS mavi, STT yeşil, embedding sarıdır. Sağdaki tür düğmeleri
serileri gizleyip gösterir; tarihler dikey çubukların altındadır.

`GET /dashboard/api/usage` yöneticiye tüm geçmiş üzerinden özet ve günlük
grupları döner. `timezone` varsayılan UTC; dashboard cihazın IANA saat dilimini
gönderir. Tarih seçimi yerel gece yarısı sınırlarıyla yapılır ve bitiş günü
dahildir; API bitiş sınırı bir sonraki günün başlangıcıdır. Filtreler: `start` (dahil), `end` (hariç), `hub_id`, `key_id`,
`provider`, `model`, `upstream_key_id`. Tarihler saat dilimi içermelidir.
Gruplar işlem türü ve birimle ayrılır; eksik usage/maliyet NULL olarak kalır.
STT süreleri ve TTS karakterleri LLM tokenlarına eklenmez.
`GET /dashboard/api/logs?limit=100&offset=0` ayrı sayfalı istek listesidir ve
`total` kayıt sayısını döndürür. Dashboard 100 kayıtlık sayfalara böler;
tablonun altında sayfa numaraları ve doğrudan sayfaya gitme alanı bulunur.

İstek anındaki upstream anahtar UUID/kaynağı context üzerinden telemetry'ye
aktarılır. Sanal anahtar ve Hub UUID kayda kopyalanır, silmeler rapor geçmişini
korur. Eski upstream kaynakları veya birimleri güncel ayarlardan tahmin edilmez.
Migrasyon eski ortak kayıtları `all`, sanal kayıtları `unrestricted` yapar;
kimlik, bütçe ve geçmiş korunur. Eski config havuzu bir kez taşınır.

Regresyonlar `dev/test-orion-router/test_key_policy.py`,
`dev/test-orion-router/test_dashboard_key_forms.py` ve
`dev/test-orion-router/test_dashboard_reporting.py` içindedir. PostgreSQL
testleri rastgele geçici şema ve transaction rollback kullanır; üretim verisine
yazmaz. Önceki Hub testlerinden HTTP varsayımlı bağlantı/adres ve eski session
mock'u kullanan katalog testleri bu değişikliklerden önce de başarısızdır.
