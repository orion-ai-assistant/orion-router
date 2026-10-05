# Router LAN keşfi ve yerel erişim

Router, Hub'dan bağımsız bir süreç olarak kendi API portunda çalışır.
Varsayılan yerel panel adresi `http://localhost:20128/dashboard` olur.
`ROUTER_PORT` veya CLI portu değiştirilmişse gerçek çalışma portunu kullanın.
Router port 80'i sahiplenmez; ortak tarayıcı kısayolu ve port-80 giriş servisi yoktur.
Hub'ın `localhost/`, `/hub`, `/panel` girişlerini Hub projesi yönetir.

## DNS-SD sözleşmesi

Native çalışmada servis tipi `_orionrouter._tcp.local.` olur.

| Kaynak / alan | Değer |
| --- | --- |
| TXT `id` | Router kurulumunun kalıcı UUID'si |
| TXT `name` | Varsayılan `<bilgisayar adı> — Orion Router`, örneğin `Hiro — Orion Router` |
| TXT `path` | `/v1` |
| TXT `version` | Router uygulamasının sürümü |
| SRV hedefi | Kuruluma ait `orionrouter-<tiresiz UUID>.local.` hostname'i |
| SRV portu | Bu Router sürecinin gerçek dinleme portu |

`.local.` burada DNS-SD çözümlemesinin teknik parçasıdır. Kullanıcıların
tarayıcıya yazdığı ortak bir ad duyurulmaz. API portu TXT'den veya varsayılan
20128 değerinden tahmin edilmez; SRV kaydından alınır.

Her kurulum `persistent/mdns-id` dosyasında ayrı UUID tutar. Aynı bilgisayardaki
iki kurulumun kimlikleri ve hostname'leri farklıdır. Başlangıçta UUID tam dosya
olarak atomik yayımlanır. Yeniden başlatma, IP / port / görünen ad değişimi UUID'yi
değiştirmez. Bozuk kimlik dosyası korunur; sessizce yeni UUID oluşturulmaz.
Kurulumu yedekten geri yüklerken kimlik dosyasını koruyun; yeni bir kurulum
klonlarken bu dosyayı kopyalamayın. İki kurulum aynı kimlik dosyasını paylaşmamalıdır.

## Ayarlar

```dotenv
ORION_ROUTER_MDNS=1
# ORION_ROUTER_MDNS_NAME=Hiro — Orion Router
# ORION_ROUTER_MDNS_INTERFACES=Wi-Fi,Ethernet
# ORION_ROUTER_MDNS_ID_FILE=persistent/mdns-id
# Özel hostname kullanılacaksa her kurulum için benzersiz olmalı:
# ORION_ROUTER_MDNS_HOSTNAME=orionrouter-home-installation.local
```

Görünen adı değiştirmek için `ORION_ROUTER_MDNS_NAME` ayarını değiştirip
Router'ı yeniden başlatın. UUID aynı kalır. Göreli kimlik dosyası yolları
çalıştırılan dizinden bağımsız olarak Router repo köküne göre çözülür.
`ORION_ROUTER_MDNS=0` keşfi kapatır, API çalışmaya devam eder.

Duyuru gerçek IPv4 TCP dinleyicisi hazır olduktan sonra başlar. CLI port
değişiklikleri de bu dinleyiciden tespit edilir. Yalnızca aktif RFC1918 LAN
adresleri yayımlanır. Loopback'e özel bind ağda duyurulmaz. VPN, sanal ve WSL
arayüzleri otomatik olarak dışlanır; açık arayüz listesiyle isteğe bağlı eklenebilir.
Ağ ve arayüz değişimleri 30 saniyede bir kontrol edilir. Eski kayıtlar/soketler
kapatılıp yeni adresler duyurulur; kapanışta goodbye gönderilir. Keşif hataları
API'yi durdurmaz, arka planda yeniden denenir.

Windows'ta gerçek Python / uv süreci için Private ağ profilinde Router TCP
portuna ve UDP 5353'e izin gerekir. Linux'ta aynı portları LAN arayüzünde açın.
Docker bridge keşfi varsayılan olarak kapalıdır. Desteklenen Linux host-network
kurulumunda `ORION_ROUTER_MDNS=1` ve
`ORION_ROUTER_MDNS_CONTAINER_HOST_NETWORK=1` gerekir. Windows Docker bridge
duyurusu desteklenmez. Hub container içinde çalışıyorsa uygun Docker servis
adresini kullanması ayrıca gerekebilir.

## Hub / Flutter bağlantı davranışı

İstemci `_orionrouter._tcp.local.` servislerini tarar, TXT ve SRV kayıtlarını
çözer ve UUID ile eşleştirir. IP'leri tek tek taramaz. Son başarılı bağlantının
Router UUID'sini kaydeder. IP / port değişince aynı UUID'nin güncel hedefini
kullanır. Kayıtlı UUID yoksa bağlantı durumu, yeniden deneme ve değiştirme
seçenekleri gösterilir; başka Router'a sessizce geçilmez. Bu seçim politikası
Hub / Flutter istemcisinde uygulanır; Router yalnızca kendi kimliğini ve
çalışma adresini duyurur.

DNS-SD kaydı kimlik doğrulama sağlamaz. UUID cihazı yeniden bulmaya yarar,
karşı tarafın gerçekten aynı cihaz olduğunu kanıtlamaz. Keşif metadatasına
API anahtarı, yönetici şifresi veya token konmaz. Mevcut Router API anahtarı
ve yönetici doğrulaması devam eder. Gerçek cihaz anahtarı / QR eşleştirmesi /
Bu belge legacy HTTP keşfini anlatır. Güvenli Hub bağlantıları ayrı
`_orion-router-tls._tcp.local.` kaydını ve SPKI pinli HTTPS listener'ı kullanır;
güncel kurulum için [Router TLS](secure-router-tls.md) belgesine bakın.

Router artık HTML seçim kabuğu, iframe mesaj protokolü, cihaz listesi HTTP
endpoint'leri veya dashboard'da Router değiştirme arayüzü sunmaz. Keşif
ve hedef seçimi istemcinin Python / native keşif katmanına aittir.

## Doğrulama

- UUID yeniden başlatma sonrasında aynıdır.
- İki ayrı kurulum iki farklı UUID / hostname duyurur.
- TXT alanları `id`, `name`, `path`, `version`; port gerçek SRV portudur.
- IP / port değişiminde aynı UUID yeni çalışma adresiyle duyurulur.
- Kapanışta kayıt kaldırılır; Hub kapalıyken Router kendi portunda çalışır.
- Router kaynakları ortak hostname veya HTTP shortcut servisi yayımlamaz.
- İstemci kayıtlı cihazı bulamayınca otomatik başka hedef seçmez.

Son iki ağ senaryosunu Hub / Flutter entegrasyonunda ve ikinci LAN cihazında
da test edin; aynı bilgisayardaki testler telefon erişimini tek başına kanıtlamaz.
