Öncelikle "tek satır kurulum" konusundaki endişeni anlıyorum ama içini ferah tut: **Senin mevcut Docker kurulumun zaten endüstri standardı ve gayet pratik.** Piyasada "tek satır" diye pazarlanan kurulumların çoğu arka planda ya tehlikeli olabilen `curl -sL url | bash` scriptleri çalıştırır ya da zaten Docker kullanır. Senin sunduğun `docker compose up` yöntemi, neyin kurulduğunu görmek isteyen geliştiriciler ve sistem yöneticileri için aslında **en güvenilir** ve tercih edilen yoldur. Hiçbir sorun olmaz.

README'nin yapısına gelirsek, metnin teknik olarak çok doyurucu ama okuyucuyu (özellikle projeyi ilk kez gören birini) biraz yoruyor. Projenin ne olduğunu anlattıktan hemen sonra **"Özellikler"** gibi kısa bir maddeleme eklemek ve kurulum adımlarını daha az metinle, daha "vurucu" hale getirmek scannability'yi (göz gezdirilebilirliği) artırır.

İşte gereksiz kalabalıktan arındırılmış, hiyerarşisi daha net ve profesyonel görünen bir README alternatifi:

---

# Orion Custom Service Router — AI Gateway

Orion projesinin **AI Gateway (Router)** katmanı. İstemcilerden ve worker'lardan gelen tüm yapay zeka (LLM, Embedding, TTS, Dosya Yükleme) isteklerini tek bir merkezde toplar, yetkilendirir ve ilgili sağlayıcılara (OpenAI, OpenRouter, Gemini, Local) dinamik olarak yönlendirir.

## ✨ Öne Çıkan Özellikler

* **Dinamik Yönlendirme:** Çöken API'larda otomatik olarak fallback (yedek) sağlayıcılara geçiş.
* **Bütçe ve Limit Kontrolü:** İstemcilere özel sanal anahtarlar (virtual keys) atayarak harcamaları kısıtlama.
* **Gizlilik Odaklı:** Gerçek API anahtarlarınızı (Upstream Keys) asla dışarı sızdırmaz.
* **Genişletilebilir Mimari:** Tek bir Python dosyası ekleyerek sisteme yeni bir AI sağlayıcısı entegre edebilme.
* **Dahili Dashboard:** İstekleri, maliyetleri ve logları takip edebileceğiniz, dahili test alanı (Playground) sunan modern arayüz.

---

## 🚀 Hızlı Başlangıç (Önerilen)

Projeyi sisteminize kurmanın en hızlı yolu **Docker** kullanmaktır. Repoyu klonlamanıza bile gerek yoktur.

**Windows (PowerShell):**

```powershell
powershell -c "irm https://raw.githubusercontent.com/krstalacam/orion-router/main/install.ps1 | iex"
```

**macOS / Linux (Bash):**

```bash
curl -sL https://raw.githubusercontent.com/krstalacam/orion-router/main/install.sh | bash
```

Bu scriptler Docker kontrolu yapar, gerekli compose dosyasini indirir, `orion-network` agini olusturur ve servisi ayaga kaldirir.

Kurulum tamamlandiginda panele 👉 **`http://localhost:20128/dashboard`** adresinden erisebilirsiniz.

> *Not:* API anahtarlarinizi `.env` dosyasi yerine dogrudan Dashboard uzerindeki **Key Pool** menusunden guvenle ekleyebilirsiniz.

---

## 🐍 Yerel (Native) Kurulum

Eğer projeyi Docker olmadan çalıştırmak isterseniz, sistemin sunduğu taşınabilir (portable) yapı sayesinde veritabanı kurmanıza gerek kalmaz.

**Ön Koşul:** `Python 3.11+`

```bash
git clone https://github.com/krstalacam/orion-router.git 
cd orion-router
python orion.py prod

```

Bu komut; PostgreSQL'i indirir, Next.js arayüzünü derler ve tüm sistemi tek bir port (`20128`) üzerinden yayına alır.

---

## 🛠 Geliştiriciler İçin

Sistemi özelleştirmek veya yeni özellikler eklemek isteyen geliştiriciler için temel rehber.

### Proje Yapısı

```text
.
├── api/                # API Uç Noktaları (Chat, Embeddings, Speech, vb.)
├── bin/                # Yerel CLI komutları (dev.py, prod.py, stop.py)
├── core/               # Lifespan, Güvenlik (Dependencies) ve Bağımlılıklar
├── dashboard/          # SPA Dashboard (Next.js & Glassmorphism UI)
├── database/           # asyncpg Havuzu, Tablo Şemaları ve Migration
├── providers/          # Sağlayıcı Eklentileri (Auto-Discovery)
├── dynamic_router.py   # Gateway'in Beyni & Maliyet Hesaplama
└── main.py             # FastAPI Uygulama Girişi

```

### CLI Araçları (`orion.py`)

Geliştirme sürecini yönetmek için kök dizindeki `orion.py` dosyasını kullanabilirsiniz:

* `python orion.py dev` : Hot-reload aktif geliştirme ortamını başlatır (PostgreSQL: 5444, API: 20129, UI: 3001).
* `python orion.py prod` : Üretim sürümünü derler ve tek portta çalıştırır.
* `python orion.py stop` : Arka planda asılı kalan tüm portları ve servisleri temizler.

### 🔌 Yeni Bir Sağlayıcı (Provider) Eklemek

`dynamic_router.py`, `providers/` klasörü altındaki klasörleri yeteneklerine (capability) göre dinamik tarayarak otomatik yükler. Herhangi bir kayıt (registration) veya `__init__.py` dosyası eklemenize gerek yoktur.

**Yetenek Dosya Eşleşmeleri:**
`providers/<provider_adi>/` klasörü altında desteklemek istediğiniz yeteneğe ait dosyayı oluşturmanız yeterlidir:
* `chat.py` ➔ `BaseChat` sınıfından türetilen Chat sağlayıcısı
* `embeddings.py` ➔ `BaseEmbed` sınıfından türetilen Embedding sağlayıcısı
* `tts.py` ➔ `BaseTTS` sınıfından türetilen Text-to-Speech sağlayıcısı
* `files.py` ➔ `BaseFileUpload` sınıfından türetilen Dosya Yükleme sağlayıcısı

**Örnek: Anthropic Entegrasyonu (Chat)**

1. `providers/anthropic/chat.py` dosyasını oluşturun ve `BaseChat` sınıfından miras alın:

```python
import os
from typing import AsyncGenerator, Any
from providers.base import BaseChat

class AnthropicChatProvider(BaseChat):
    provider_name = "anthropic"

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        # 1. API Anahtarını al (auth_header, api_key veya env_key fallbacks)
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
            env_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        
        if not resolved_key:
            raise ValueError("Anthropic Error: No API key provided.")
        
        # 2. HTTPX AsyncClient ile hedef API'ye istek at
        # 3. Veriyi standart formatta yield et:
        # yield 'data: {"choices":[{"delta":{"content":"..."}}]}\n\n'
        pass

```

FastAPI/Gateway yeniden başladığında, `anthropic` sağlayıcısı ve `chat` yeteneği otomatik olarak keşfedilir ve kullanıma hazır hale gelir.

""""""""

 powershell -ep bypass -c "& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/krstalacam/orion-router/main/install.ps1'))) docker"

 bunu kullanıyoruz artık