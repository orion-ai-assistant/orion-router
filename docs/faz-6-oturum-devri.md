# Faz 6: güvenli mobil bağlantı — oturum devri ve plan incelemesi

> 2026-10-04 güncellemesi: Bu belgedeki eski yaprak sertifika DER pini ve
> otomatik sertifika yenilenmemesi sözleşmesi, kullanıcının yeni
> "Orion Faz 6 — Güvenli Yerel Bağlantı, Pairing ve TLS" planıyla geçersizdir.
> Güncel güven kimliği kalıcı P-256 anahtarın **SHA-256 DER SPKI** pinidir
> (küçük harfli 64 hex karakter). Sertifika süresi dolunca aynı anahtarla
> yenilenir, pin değişmez. Router HTTPS portu varsayılan 9443'tür.
> Aşağıdaki geçmiş oturum notları güncel protokol kaynağı değildir;
> uygulama ve kullanım için `secure-router-tls.md` belgesine bakın.

> Son kullanıcı yönlendirmesi: HTTP tamamen kaldırıldı. Router artık tek HTTPS
> listener kullanır (üretim 9443, geliştirme 9444); legacy 20128 ve legacy HTTP
> mDNS kaydı açılmaz. Aşağıdaki iki-listener/HTTP uyumluluğu tarihsel notlardır.

> Sonraki kullanıcı kararı: PC-yerel tarayıcı için yalnızca 127.0.0.1:20128
> HTTP listener geri eklendi. Gerçek loopback peer/Host/Origin sınırı vardır;
> LAN ve Hub bağlantıları HTTPS 9443 ve SPKI pini kullanmaya devam eder.

Bu oturumda TLS / eşleştirme kodu uygulanmadı. Bu belge sonraki oturumun
başlangıç bilgisidir. Kullanıcının planı: mevcut web HTTP akışı korunacak;
mobil Flutter → Hub ve sonraki aşamada Hub → Router için ayrı HTTPS listener,
güvenilir yerel ekrandan eşleştirme ve pin kontrolü eklenecek.


## Faz 6 — kesin ortak sözleşme (2026-10-04 revizyonu)

Bu bölüm Hub, Flutter ve Router devirlerinde aynı sözleşmedir. Aşağıdaki kurallar
kesindir; uygulama henüz tamamlanmış sayılmaz. Mevcut kod anlatımı hedef sözleşmenin
yerine geçmez. Önce Hub–Flutter, sonra Router TLS ve Hub'ın tüm Router istemcileri uygulanır.

| Kanal | Keşif (DNS-SD / native NSD) | Transport ve sınır |
| --- | --- | --- |
| Hub web | `_orion._tcp.local.` / `_orion._tcp` (değişmez) | Mevcut HTTP portu ve web hesabı/oturumu korunur; TLS şifrelemesi ve sunucu kimliği doğrulaması yok. |
| Hub mobil | `_orion-mobile._tcp.local.` / `_orion-mobile._tcp` | Ayrı HTTPS listener (varsayılan 8443, ayarlanabilir); zorunlu TXT: `id`, `v=1`, `scheme=https`. |
| Router güvenli API | `_orion-router-tls._tcp.local.` / `_orion-router-tls._tcp` | Ayrı TLS kaydı ve HTTPS listener; port ayarlanabilir, SRV gerçek TLS portudur. |

- Keşif yalnızca adres ipucudur. UUID kalıcıdır; SRV gerçek portu taşır. Mobil
  TXT'deki `v=1` protokol sürümüdür; eski `version` alanıyla değiştirilmez.
  `name` ve `path` ek bilgi olabilir. Eski `_orionrouter._tcp` HTTP kaydı TLS
  kaydı değildir. Keşif pini güncelleyemez; kayıtlı hedef yoksa başka hedefe geçilmez.
- `device_token` cihazı yetkilendirir; hesap girişi ayrıdır ve token yönetici
  yetkisi vermez. Mobil hesap oturumu eşleşmiş cihaza bağlanır. Hesap gerektiren
  isteklerde geçerli cihaz ve kullanıcı oturumu birlikte gerekir. Kullanıcı çıkışı
  cihaz eşleştirmesini silmez. HTTP listener hem cihaz token'ını hem mobil kullanıcı
  oturumunu reddeder; mevcut web oturumu ayrı kalır. Mobil istemci HTTP'ye sır göndermez.
- HTTPS/HTTP ayrımı gerçek dinleyiciden (TLS soketi/listener kimliği) yapılır.
  `X-Forwarded-Proto`, `Forwarded`, Host veya başka istemci başlıkları TLS kanıtı
  değildir; başlıkla HTTP isteği HTTPS yetkisi kazanamaz. Pair claim yalnızca HTTPS'tedir.
- Kod kriptografik rastgele 40 bit (8 base32 karakter), TTL 120 saniye ve tek
  kullanımlıktır. Kod tüketimi ve cihaz token'ı oluşturma tüm süreçler arasında
  atomiktir; eşzamanlı claim'lerden yalnızca biri başarılı olur. Yanlış denemeler
  kodları iptal ETMEZ. Gerçek kaynak IP başına ve genel hız sınırı, backoff ve
  429 uygulanır; kaynak IP istemci başlığından alınmaz. Bilinmeyen, süresi dolmuş
  veya kullanılmış kod aynı `403 pair_code_invalid` cevabını verir.
- Claim: `POST /api/v1/pair/claim`, istek `{code,device_id,device_name,platform}`,
  başarı `{hub_id,hub_name,device_token}`. QR/metin `{v:1,id,url,fp,code,name}`
  güvenilir yerel ekrandan alınır. Aday pin yalnızca claim için kullanılır;
  başarılı claim ve QR UUID eşitliğinden sonra pin/token kalıcılaşır. Cihaz token'ı
  256 bit rastgele, yalnızca bir kez döner; sunucuda yalnızca hash'i saklanır.
- Cihaz silinince token ve bağlı mobil oturumlar iptal edilir; açık SSE ve
  WebSocket bağlantıları kapatılır. Yalnızca sonraki isteği reddetmek yeterli
  değildir. Kimlik sıfırlama tüm cihazlar ve açık bağlantılar için aynı sonucu verir.
- Mobil REST, SSE, WSS ve dosya indirme/yükleme dahil tüm bağlantılar tek pinli
  HttpClient fabrikasını kullanır. Ses WebSocket'i pinli HttpClient ile
  `WebSocket.connect(..., customClient: pinnedClient)` üzerinden açılır; kanala
  gerekiyorsa bu soket sarılır. Doğrudan pinsiz `WebSocketChannel.connect` kullanılmaz.
  `SecurityContext(withTrustedRoots:false)`, ek CA yok, yalnızca aday/kayıtlı
  DER SPKI SHA-256 eşitliği kabul edilir. Pin doğrulanmadan kod, parola, token, API
  anahtarı veya gövde gönderilmez. Redirect ve HTTP fallback kapalıdır.
- Router pini Hub→Router bağlantılarının tamamında uygulanır: keşif/bağlantı
  kontrolü, worker, sohbet, model/grup listesi, ses katalogları, STT/TTS, HTTP
  akışları ve ses WebSocket'i. Aiohttp pini ayrı WebSocket istemcisine kendiliğinden
  geçmez; onun transport'u da sır gönderilmeden pini doğrular. Pin kaydı API ve
  worker tarafından ortak kullanılır; hedef/pin değişiminde eski havuz ve akışlar kapanır.
- Hub ve Router kalıcı ECDSA P-256 özel anahtar ve yaklaşık 50 yıllık self-signed
  sertifika kullanır. Süresi dolan sertifika aynı anahtarla yenilenebilir.
  Pin DER SPKI SHA-256 parmak izidir; sertifikanın parmak izi değildir.
  Özel anahtara sahip olunduğu TLS el sıkışmasıyla doğrulanır. Anahtar
  değişimi açık yeniden eşleştirme gerektirir; normal restart ve aynı anahtarla
  sertifika yenileme kimliği değiştirmez.

Kabul kontrolleri: servis adları/TXT/SRV ve web HTTP uyumluluğu; hem cihaz hem
mobil oturumunun HTTP'de reddi (sahte TLS başlıkları dahil); cihaz token'ıyla
yönetici erişiminin reddi; yanlış kodlarla mevcut kodun iptal olmaması, IP ve
genel backoff/429, TTL/tek kullanım/atomik yarış; cihaz silinince açık SSE/WS'nin
kapanması; REST/SSE/WSS/dosya ve tüm Hub→Router yollarında pin hatasında sıfır
sır gönderimi; doğru pinle süre kontrolü olmadan bağlantı; yanlış pin ve özel
anahtarsız sertifika kopyasında bağlantının reddi; IP/port değişiminde pinin korunması.


## Repo ve mevcut durum

- Router: `D:/krstlcm Workspace/DevProjects/orion-router`.
- Hub: `D:/krstlcm Workspace/DevProjects/orion-ai-assistant`.
- Flutter: `D:/krstlcm Workspace/DevProjects/orion-ai-assistant-flutter/main_app/app`.
- Paylaşılan eski keşif sözleşmesi:
  `orion-ai-assistant/files/orion-yerel-giris-kesif-sozlesmesi.md`.
  Mevcut HTTP kodunu anlatır; Faz 6 hedefi kesin ortak sözleşmeyle ayrılmıştır.
- Router'da commit edilmemiş mevcut değişiklikler var. Önce `git status` ve
  ilgili `AGENTS.md` okunmalı; mevcut çalışmayı reset/clean ile silmeyin.

## Router'da tamamlanan işler

- `orionrouter.local`, port-80 adres servisi ve bu servisin Windows Run başlangıç
  kaydı kaldırıldı. Ortak alias ve seçim/iframe arayüzü yok.
- Router Hub'dan bağımsız olarak kendi portunda çalışır. Mevcut yerel panel
  `http://localhost:20128/dashboard`; port yapılandırılabilir.
- `core/mdns.py`: `_orionrouter._tcp.local.` duyurusu, kalıcı kurulum UUID'si,
  gerçek SRV portu, arayüz değişimi ve goodbye yönetimi.
- UUID `persistent/mdns-id` içinde. Bu dosyayı silmeyin veya kimliği yeniden
  üretmeyin. TLS eklenmesi mevcut kurulum UUID'sini değiştirmemeli.
- Varsayılan TXT adı `<PC adı> — Orion Router`; kullanıcı override edebilir.
  Paylaşılan önceki belgede ters ad sırası var; tek biçim üzerinde anlaşılmalı.
- TXT alanları `id`, `name`, `path=/v1`, `version`. Teknik hostname
  `orionrouter-<UUID hex>.local.` kalır; ortak tarayıcı kısayolu değildir.
- `/v1/models` ve `/v1/discovery/self` mevcut sürümde yok.
- Hub'ın mevcut bağlantı kontrolü bunların 404 olmasını destekler; gerçek
  Router anahtarını model çalıştırmadan boş `/v1/chat/completions` isteğinin
  bilinen model-eksikliği 400 yanıtıyla kontrol eder.
- Yönetici doğrulaması korunur. Hızlı yönetici kontrolü
  `POST /dashboard/api/auth/login`, `X-Admin-Key`, başarı 204, hata 401.
- Giriş düğmesi “Giriş Yap”; yerel HTTP'de clipboard alternatifi vardır.
- Son mevcut doğrulama: 44 Python testi, 4 clipboard testi ve Next üretim
  derlemesi geçti. İki ayrı geçici kurulumun SRV çözümü ve goodbye kaldırılması
  canlı multicast ile doğrulandı. Telefon erişimi veya TLS pinning testi değildir.

## Hub / Flutter kaynaklarında gözlenen mevcut durum

- Hub HTTP public API/dashboard portu 8910; yerel yönetim yalnızca localhost.
- Hub'ın `RouterAssociation` kodu UUID'nin TLS kimliği olmadığını açıkça belirtir.
  Bu kodda henüz Router pin kontrolü yok.
- Flutter `lib/core/network/hub_discovery_native.dart`, `_orion._tcp` tarar ve
  keşif sonucunu açıkça `scheme: 'http'` ile URL'ye dönüştürür.
- QR/TLS/device-token akışının tamamlandığı varsayılmamalı; uygulama ve güvenlik
  testleri ayrıca eklenmeli. SHA adlı mevcut başka bir yardımcı TLS pinning
  uygulandığını kanıtlamaz.

## İki listener düzeni

| Kanal | Mevcut / hedef | Sınır |
| --- | --- | --- |
| Hub web | HTTP 8910 | Mevcut kullanıcı girişi ve web oturumu korunur; TLS şifrelemesi ve sunucu kimliği doğrulaması yok. |
| Hub yerel panel | Loopback HTTP 80 | QR oluşturma / cihaz yönetimi; gerçek peer + Host + Origin kontrolleri. |
| Hub mobil API | HTTPS 8443, ayarlanabilir | Pair claim ve mobil cihaz yetkilendirmesi; yalnızca pinli Flutter istemcisi. |
| Router mevcut API/UI | HTTP 20128 | Mevcut web erişimi; TLS şifrelemesi ve sunucu kimliği doğrulaması yok. |
| Router güvenli API | Ayrı HTTPS portu | Hub'ın pinli istemcisi; sır gönderilmeden önce TLS doğrulaması. |

Router HTTPS portu varsayılan 9443'tür ve yapılandırılabilir. Mevcut HTTP
korunur; eşleştirilmiş Hub istemcisi HTTP'ye otomatik düşmemeli.

Web'de mevcut kimlik doğrulama vardır. “Güvenlik yok” yerine “TLS şifrelemesi
ve sunucu kimliği doğrulaması yok” denmeli. Mobil HTTPS eklenmesi HTTP web
oturumunu, HTTP'ye girilen parolayı veya o kanalda taşınan veriyi korumaz.

## Kesin sözleşmenin Router / Hub uygulama sınırları

1. Listener ayrımı gerçek TLS soketinden yapılır; başlıklar TLS kanıtı değildir.
   HTTP hem device_token hem mobil hesap oturumunu reddeder. Pair route'ları
   yalnızca HTTPS listener'dadır; mobil cihaz token'ı yönetici yetkisi vermez.
2. Cihaz silinince token ve bağlı mobil oturumlar iptal, açık SSE/WS kapanır.
3. Keşif adları kesindir: web `_orion._tcp`, mobil `_orion-mobile._tcp`
   (TXT `id`, `v=1`, `scheme=https`), Router TLS `_orion-router-tls._tcp`.
   Her kayıt SRV'de kendi gerçek portunu verir. Mevcut HTTP Router kaydı ayrı kalır.
4. Pin güvenilir yerel ekrandan alınır. mDNS / HTTP self endpoint'i pin kaynağı
   olamaz. QR URL'si adres ipucudur; kayıtlı pin keşifle değiştirilmez.
5. Mobil REST/SSE/WSS/dosya tek pinli fabrikadadır. Ses WebSocket'i
   `WebSocket.connect(..., customClient: pinnedClient)` kullanır. Hub→Router pini
   worker, model/grup/ses katalogları, STT/TTS ve ses WebSocket'i dahil tüm
   istemcilerdedir. Aiohttp pini ayrı WS istemcisine otomatik uygulanmaz.
6. Sertifika yaklaşık 50 yıl; süresi dolunca aynı kalıcı anahtarla yenilenir.
   DER SPKI SHA-256 pini sertifika yenilemede değişmez.
7. Kod 40 bit, TTL 120 saniye, atomik tek tüketimdir. Yanlış denemeler kodları
   iptal ETMEZ; gerçek kaynak IP başına ve genel hız sınırı/backoff/429 uygulanır.
8. Token 256 bit rastgele; sunucuda hash, Android/iOS'ta Hub UUID'sine göre
   güvenli depolama. Token/QR içeriği loglanmaz; web JWT'siyle karıştırılmaz.
9. Anahtar eksik/bozuksa sessiz kimlik değişimi olmaz; açık yeniden eşleştirme
   gerekir. Kimlik yenileme kullanıcı hesaplarını/sohbetleri silmez.

## Keşif korunacak

Keşif adresi bulur; TLS, bulunan adresteki sunucunun kayıtlı sertifika / anahtara
sahip olduğunu doğrular. UUID IP değişiminde eşleştirmeye yardım eder, güven
kanıtı değildir. Keşif kayıtlı pini değiştiremez. Aynı UUID iki farklı hedefte
belirsizse otomatik bağlantı yerine belirsizlik gösterilir. Kayıtlı hedef yoksa
başka Hub / Router'a sessiz geçilmez. mDNS genellikle aynı yerel ağ içindir;
başka ağ / internet erişiminde ayrıca adresleme veya güvenli erişim yolu gerekir.

## Sonraki oturumun kabul testleri

- Pin uyuşmazlığı: eşleştirme kodu, parola, token, API anahtarı ve gövde karşıya gitmez.
- Kopyalanmış sertifika ama özel anahtar yok: TLS handshake tamamlanmaz.
- Doğru pin / yeni IP-port: bağlantı olur, kayıtlı pin değişmez.
- Pair claim yarışı: iki eşzamanlı istekte tek başarılı tüketim.
- Claim id uyuşmazlığı veya başarısız claim: aday pin ve token kalıcılaşmaz.
- HTTP listener + device token veya mobil kullanıcı oturumu: reddedilir;
  sahte forwarded başlık bunu aşmaz.
- Hesap yetkisi: device token tek başına diğer kullanıcıların verilerini açmaz.
- SSE / ses / dosya / WebSocket akışları aynı güven sınırını uygular.
- Hub değiştirme / token iptali: eski bağlantılar kapanır ve eski sırlar yeni hedefe gitmez.
- HTTP redirect, HTTPS redirect ve otomatik HTTP fallback: istemci reddeder.
- İşlemler arasında restart: kalıcı anahtar, UUID ve token kayıtları tutarlı kalır.
- Anahtar yenileme: eski pin/tokenlar geçersiz; hesaplar/sohbetler korunur.
- Mevcut HTTP web girişleri çalışmayı sürdürür; yeni HTTPS SRV duyurusu bunları bozmaz.

## İncelenen birincil kaynaklar

- TLS: https://www.rfc-editor.org/rfc/rfc8446.html
- Dart badCertificateCallback:
  https://api.dart.dev/dart-io/HttpClient/badCertificateCallback.html
- Dart SecurityContext:
  https://api.dart.dev/dart-io/SecurityContext/SecurityContext.html
- aiohttp fingerprint / TLS istemcisi:
  https://docs.aiohttp.org/en/stable/client_advanced.html
