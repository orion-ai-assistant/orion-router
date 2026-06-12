# Orion Custom Service Router — AI Gateway

Orion projesinin **AI Gateway (Router)** katmanı. İstemcilerden ve worker'lardan gelen tüm yapay zeka (LLM, Embedding, TTS, Dosya Yükleme) isteklerini tek bir merkezde toplar, yetkilendirir ve ilgili sağlayıcılara (OpenAI, OpenRouter, Gemini, Local) dinamik olarak yönlendirir.

## 🤔 Bu Proje Nedir ve Amacı Ne?

Orion Router, yapay zeka modelleriyle çalışan uygulamalarınız ve ekipleriniz için **kendi kişisel "OpenAI" ağ geçidinizi** (gateway) kurmanızı sağlar.

* **Tek API, Tüm Modeller:** Uygulamalarınızı sadece Orion Router'a bağlarsınız. Arka planda OpenAI, Anthropic, Gemini, OpenRouter veya kendi sunucunuzdaki yerel modelleri kullanabilirsiniz. Kodunuzu değiştirmeden sağlayıcı değiştirebilir veya çöken API'lardan anında yedeğe geçebilirsiniz (Fallback).
* **Güvenlik ve Gizlilik:** Gerçek API anahtarlarınız (Upstream Keys) sunucunuzda güvende kalır. İstemcilere ve takım arkadaşlarınıza sadece sizin belirlediğiniz **Sanal Anahtarları (Virtual Keys)** verirsiniz.
* **Maliyet Yönetimi:** Hangi kullanıcının veya projenin ne kadar harcadığını takip edebilir, bütçe limitleri koyabilirsiniz.
* **Hazır Dashboard:** İstekleri, maliyetleri, logları takip edebileceğiniz ve modelleri test edebileceğiniz modern bir arayüz ile gelir.

## 💡 Nasıl Kullanılır?

Orion Router, **tamamen OpenAI API uyumlu** çalışacak şekilde tasarlanmıştır. Herhangi bir OpenAI kütüphanesinde (Python, Node.js, LangChain vs.) sadece `base_url` ve `api_key` değiştirerek Orion'u anında sisteminize entegre edebilirsiniz!

**Örnek Python (OpenAI SDK) Kullanımı:**

```python
import openai

# OpenAI client'ını Orion Router'a yönlendiriyoruz
client = openai.OpenAI(
    base_url="http://localhost:20128/v1", # Orion Router sunucu adresiniz
    api_key="orion-sanal-anahtariniz"     # Dashboard üzerinden ürettiğiniz sanal anahtar
)

response = client.chat.completions.create(
    model="gemini-3.1-flash-lite", 
    messages=[{"role": "user", "content": "Merhaba Orion!"}],
    temperature=0.7, 
    tools=[], 
    extra_body={
        "thinking_level": "medium" # Düşünme kapasitesi; "low" - "high" veya token bütçesi: 1024, 8192 vb. (modelin desteklemesi gerekir)
    }
)

print(response.choices[0].message.content)
```

> **🧠 Gelişmiş Parametre Çevirisi:** Orion Router; `temperature`, `tools` (Fonksiyon çağırma/Function Calling) ve `thinking_level` (Düşünme Bütçesi) gibi özellikleri evrensel olarak destekler. Siz sadece standart formatta isteği gönderirsiniz, Orion Router arka planda bu parametreleri hedeflenen sağlayıcının (OpenAI, Gemini, Anthropic vb.) anlayacağı doğru yapıya (örn. *reasoning_effort*, *thinking_budget*) otomatik olarak adapte eder!

## ✨ Öne Çıkan Özellikler

* **Dinamik Yönlendirme:** Çöken API'larda otomatik olarak fallback (yedek) sağlayıcılara geçiş.
* **Bütçe ve Limit Kontrolü:** İstemcilere özel sanal anahtarlar (virtual keys) atayarak harcamaları kısıtlama.
* **Gizlilik Odaklı:** Gerçek API anahtarlarınızı (Upstream Keys) asla dışarı sızdırmaz.
* **Genişletilebilir Mimari:** Tek bir Python dosyası ekleyerek sisteme yeni bir AI sağlayıcısı entegre edebilme.
* **Dahili Dashboard:** İstekleri, maliyetleri ve logları takip edebileceğiniz, dahili test alanı (Playground) sunan modern arayüz.

---

## 🚀 Hızlı Başlangıç (Önerilen)

Projeyi sisteminize kurmanın en hızlı yolu **Docker** kullanmaktır. Repoyu klonlamanıza bile gerek yoktur. Terminalinize aşağıdaki komutu yapıştırarak tüm sistemi tek seferde ayağa kaldırabilirsiniz.

**Windows (PowerShell):**

```powershell
powershell -ep bypass -c "& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/krstalacam/orion-router/main/install.ps1'))) docker"
```

**macOS / Linux (Bash):**

```bash
curl -sL https://raw.githubusercontent.com/krstalacam/orion-router/main/install.sh | bash
```

Bu scriptler Docker kontrolü yapar, gerekli compose dosyasını indirir, `orion-network` ağını oluşturur ve servisi ayağa kaldırır.

Kurulum tamamlandığında panele 👉 **`http://localhost:20128/dashboard`** adresinden erişebilirsiniz.

> *Not:* API anahtarlarınızı `.env` dosyası yerine doğrudan Dashboard üzerindeki **Key Pool** menüsünden güvenle ekleyebilirsiniz.

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

### CLI Araçları (`orion.py`)

Geliştirme sürecini yönetmek için kök dizindeki `orion.py` dosyasını kullanabilirsiniz:

* `python orion.py dev` : Hot-reload aktif geliştirme ortamını başlatır (PostgreSQL: 5444, API: 20129, UI: 3001).
* `python orion.py prod` : Üretim sürümünü derler ve tek portta çalıştırır.
* `python orion.py stop` : Arka planda asılı kalan tüm portları ve servisleri temizler.

### 🔌 Yeni Bir Sağlayıcı (Provider) Eklemek

`dynamic_router.py`, `providers/` altındaki klasörleri tarayarak otomatik yükler.

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
