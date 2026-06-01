# Orion Custom Service Router — AI Gateway

Bu servis, Orion projesinin **AI Gateway (Router)** katmanıdır. Worker'lardan ve istemcilerden gelen tüm yapay zeka (LLM, Embedding vb.) isteklerini karşılar, kimlik doğrulaması yapar, bütçe kontrollerini gerçekleştirir ve ilgili API sağlayıcısına (OpenAI, OpenRouter, Gemini, Local) dinamik olarak yönlendirir.

![Orion Router Dashboard](assets/img/dashboard.png)

---

## 🚀 Nasıl Çalıştırılır?

Bu proje Docker'a olan bağımlılığı ortadan kaldırarak tamamen **yerel (native)** olarak çalışacak şekilde tasarlanmıştır. Veritabanı olarak **taşınabilir (portable) PostgreSQL** kullanır; hiçbir şey kurmanız gerekmez, scriptler gerekli dosyaları otomatik indirir.

**Ön Koşullar:** Python 3.11+ ve Node.js kurulu olmalıdır.

Tüm komutlar proje kök dizininde `orion.py` üzerinden çalışır:

```powershell
python orion.py <komut>
```

| Komut | Açıklama |
|-------|----------|
| `dev` | Geliştirme ortamını başlatır (hot-reload aktif) |
| `prod` | Üretim ortamını derleyip yerel olarak başlatır |
| `stop` | Çalışan tüm servisleri ve portları temizler |

---

### 1. Geliştirme (Development) Ortamı

Kod yazarken anlık güncellemeleri (hot-reload) görmek için bu modu kullanın:

```powershell
python orion.py dev
```

Bu komut sırasıyla şunları yapar:

1. **PostgreSQL Portable** — İlk seferde otomatik indirilir, `.pgdata-dev/` klasöründe **Port 5444** üzerinde başlatılır.
2. **Backend (FastAPI)** — `.env` içindeki `ROUTER_DEV_PORT` (varsayılan `20129`) üzerinde hot-reload ile çalışır.
3. **Frontend (Next.js)** — `http://localhost:3001` adresinde hot-reload ile çalışır.

Servisler hazır olduğunda terminalde aşağıdaki gibi bir banner görürsünüz:

![Dev ortamı banner](assets/img/dev_banner.png)

---

### 2. Üretim (Production) Ortamı

Docker gerektirmez. Projenin son halini yerel olarak derleyip çalıştırmak için:

```powershell
python orion.py prod
```

Bu komut sırasıyla şunları yapar:

1. **PostgreSQL Portable** — `.pgdata-prod/` klasöründe **Port 5433** üzerinde başlatılır.
2. **Dashboard Build** — Next.js projesi `npm run build` ile derlenir, `out/` klasörüne statik dosyalar çıkarılır.
3. **Tek Port** — FastAPI, Dashboard statik dosyalarını kendi üzerinden sunar. Dashboard ve API, `.env` içindeki `ROUTER_PORT` (varsayılan `20128`) üzerinde birlikte çalışır.

Servis hazır olduğunda Gateway Dashboard'una şu adresten ulaşabilirsiniz:
👉 **`http://localhost:20128/dashboard`**

---

### 3. Acil Durdurma

`CTRL+C` normalde her şeyi temiz kapatır. Arka planda takılı kalan bir süreç varsa:

```powershell
python orion.py stop
```

Bu script tüm portları (`3001`, `20128`, `20129`, `5433`, `5444`) boşaltır ve her iki PostgreSQL örneğini (dev + prod) durdurur.

---

## 🐳 Docker ile Çalıştırma

### A) Hazır Image'ı Çekip Kullanma (Önerilen)

Projeyi bilgisayarınıza klonlamadan (sadece Docker kullanarak) çalıştırmak için tek ihtiyacınız olan `docker-compose.ghcr.yml` dosyasıdır. Terminalinizde sırasıyla şu komutları çalıştırarak kurabilirsiniz:

```bash
# 1. Proje için bir klasör oluşturun ve içine girin
mkdir orion-router && cd orion-router

# 2. Hazır compose dosyasını indirin
curl -O https://raw.githubusercontent.com/krstalacam/orion-router/main/docker-compose.ghcr.yml

# 3. Docker ağını oluşturun
docker network create orion-network

# 4. Servisi başlatın
docker compose -f docker-compose.ghcr.yml up -d
```

Bu komut, GitHub Container Registry'den `ghcr.io/krstalacam/orion-router:latest` imajını ve PostgreSQL veritabanını otomatik indirip ayağa kaldırır.

> **💡 Güncelleme Notu:** `docker-compose.ghcr.yml` dosyasında `pull_policy: always` tanımlı olduğu için `docker compose up -d` komutunu her çalıştırdığınızda Docker en güncel imajı otomatik olarak çeker. Eğer çalışan bir sistemi manuel olarak güncellemek isterseniz şu komutları kullanabilirsiniz:
> ```bash
> docker compose -f docker-compose.ghcr.yml pull
> docker compose -f docker-compose.ghcr.yml up -d
> ```

### B) Repodan Build Ederek Çalıştırma

Eğer kodlarda değişiklik yapacaksanız veya kendiniz build etmek isterseniz repoyu klonlayıp çalıştırabilirsiniz:

```bash
docker network create orion-network
docker compose up -d
```

`.env` dosyası yoksa uygulama ilk açılışta `.env.example` dosyasından otomatik oluşturur; elle kopyalamanız gerekmez. Sağlayıcı API anahtarlarını Dashboard → **Key Pool** üzerinden ekleyin (`.env`'de tutulmaz).

---

## 📂 Proje Yapısı

```text
.
├── assets/             # Görseller ve statik varlıklar
│   └── img/            # README ve dokümantasyon görselleri
├── bin/                # Çalıştırma scriptleri
│   ├── dev.py          # Development ortamı (PostgreSQL + FastAPI + Next.js)
│   ├── prod.py         # Production ortamı (PostgreSQL + FastAPI, statik dashboard)
│   └── stop.py         # Acil durdurma ve port temizleme
├── dashboard/          # SPA Dashboard (Next.js)
├── providers/          # Sağlayıcı Eklentileri (Plugins)
│   ├── __init__.py
│   ├── base.py         # Sağlayıcı Arayüzü (Base Interface)
│   ├── gemini.py       # Google Gemini Sağlayıcısı
│   ├── local.py        # Lokal Modeller (Llama.cpp/Ollama) & <think> parser
│   ├── openai.py       # Standart OpenAI Sağlayıcısı
│   └── openrouter.py   # OpenRouter Sağlayıcısı
├── database.py         # asyncpg DB Bağlantı Havuzu ve Tablolar
├── dynamic_router.py   # Dinamik Yükleyici (Auto-Discovery) & Maliyet Hesaplama
├── main.py             # Uvicorn FastAPI Uygulama Girişi ve Dashboard API'leri
├── orion.py            # CLI Entrypoint (dev / prod / stop)
├── pyproject.toml      # Paket Yönetim ve Bağımlılık Yapılandırması
├── docker-compose.yml  # Docker Compose Yapılandırması
└── Dockerfile          # Bağımsız Docker İmajı Oluşturucu
```

---

## ⚙️ Teknik Detaylar

### `main.py`
Uygulamanın ana giriş noktasıdır.
- **FastAPI Lifespan:** Uygulama başlarken veritabanı bağlantı havuzunu başlatır (`init_db`) ve dinamik yönlendiriciyi ayağa kaldırır. Kapanırken havuzu kapatır.
- **`authenticate_request` (Dependency):** Gelen `Authorization: Bearer <key>` veya `x-orion-api-key` değerini alır, SHA-256 ile hash'ini kontrol eder. Sanal anahtarın aktiflik durumunu ve bütçe sınırını (`budget` ve `used_amount`) sorgular. Gerçek upstream anahtarlarını **asla istemciye sızdırmaz.**
- **`/v1/chat/completions`:** İstemcinin standart sohbet isteklerini `DynamicLLMRouter.run_combo` fonksiyonuna aktarır ve `StreamingResponse` (SSE) olarak döner.
- **Dashboard API'leri (`/dashboard/api/...`):** Sanal anahtar listeleme/oluşturma, canlı kullanım istatistikleri (`/stats`) ve log izleme uç noktalarını sunar.

### `database.py`
PostgreSQL ile asenkron bağlantıları yönetir.
- **`asyncpg` Pool:** Performans odaklı ham SQL bağlantı havuzudur.
- **Otomatik Şema Doğrulama:** `_ensure_tables` fonksiyonu `router_virtual_keys`, `router_combo_routes` ve `router_request_logs` tablolarını kontrol eder, yoksa oluşturur.
- **Canlı Güncelleme:** Eski şemalarda eksik kolonlar `ALTER TABLE` ile otomatik güncellenir.

### `dynamic_router.py`
Gateway'in beynidir.
- **Auto-Discovery (Eklenti Tespiti):** `providers/` altındaki tüm Python dosyalarını tarar ve `BaseLLMProvider` sınıfından türetilen sınıfları belleğe yükler.
- **`run_combo`:** İsteği doğrudan veya veritabanındaki yönlendirme kurallarına (`combo_routes`) göre ilgili sağlayıcı eklentisine paslar. Primary sağlayıcı çökerse `fallback_provider` ve `fallback_model` devreye girer.
- **Asenkron Loglama:** Akış tamamlandığında arka planda (`asyncio.create_task`) token miktarları üzerinden maliyet hesaplanır ve bütçeden düşülür. Ana istemci akışını **geciktirmez.**

### `providers/` (Pluginler)
Her sağlayıcı `BaseLLMProvider` interface'ine (`stream_chat` metodu) uymak zorundadır.
- **`openai.py`:** Doğrudan OpenAI (`api.openai.com`) hedeflerine gider.
- **`openrouter.py`:** OpenRouter hedefine gider; `HTTP-Referer` ve `X-OpenRouter-Title` başlıklarını otomatik enjekte eder.
- **`gemini.py`:** Google'ın OpenAI uyumlu API endpoint'ine yönlendirir.
- **`local.py`:** Ollama veya Llama.cpp gibi yerel motorlara istek atar. Gelişmiş state machine ile `<think>...</think>` bloklarını ayıklayarak istemciye ayrı SSE event'leri olarak gönderir.

### `dashboard/`
- **Tek Sayfa Uygulaması (SPA):** Doğrudan FastAPI (`StaticFiles`) tarafından `/dashboard` adresinde sunulur.
- **Teknolojiler:** Premium karanlık tema, Glassmorphic buzlu cam tasarımı, CSS HSL renk değişkenleri, Vanilla JS.
- **Playground Sekmesi:** Sanal anahtarı girip OpenRouter, OpenAI, Gemini veya Local sağlayıcıları üzerinden canlı test etmenizi sağlar.

---

## 🔌 Yeni Bir Eklenti (Provider) Nasıl Eklenir?

Yeni bir sağlayıcı (örneğin Anthropic) eklemek son derece basittir ve **hiçbir mevcut kodu değiştirmeniz gerekmez:**

1. `providers/` klasörü altında `anthropic.py` adında bir dosya oluşturun.
2. Aşağıdaki şablonu kullanarak sınıfı tanımlayın:

```python
import os
import json
import httpx
from typing import AsyncGenerator, Any
from .base import BaseLLMProvider

class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"  # x-orion-provider başlığında kullanılacak isim

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs
    ) -> AsyncGenerator[Any, None]:
        
        # 1. API Anahtarı Ayarı (sanal anahtarları süz)
        final_key = None
        if auth_header and not auth_header.startswith("Bearer sk-orion-"):
            final_key = auth_header
        elif api_key and not api_key.startswith("sk-orion-"):
            final_key = api_key
        else:
            final_key = api_key  # Key Pool / router tarafından iletilen upstream anahtar
            
        # 2. HTTP isteğini oluştur ve akış yap (HTTPX client)
        # 3. Gelen veriyi yield et:
        #    - Düşünme adımları: yield 'data: {"type": "thinking", "text": "..."}\n\n'
        #    - İçerik adımları:  yield 'data: {"type": "content", "text": "..."}\n\n'
        #    - İstatistikler:    yield {"internal_usage": {"prompt_tokens": 10, "completion_tokens": 20}}
        pass
```

3. Gateway yeniden başlatıldığında dosyayı otomatik olarak keşfedip yükler:
   ```
   Loaded provider plugin: anthropic
   ```
