# Orion Router API Kullanım Kılavuzu

Orion Router, standart **OpenAI Chat Completions API** (`/v1/chat/completions`) ile %100 uyumludur. Mevcut OpenAI Python/Node.js SDK'larını, LangChain, LlamaIndex, Cursor, Cline veya doğrudan `curl` isteklerini herhangi bir kod değişikliği yapmadan Orion Router'a yönlendirebilirsiniz.

---

## 1. Temel Bağlantı Bilgileri

- **Base URL:** `http://localhost:20128/v1`
- **Endpoint:** `/v1/chat/completions`
- **Yetkilendirme:** `Authorization: Bearer <API_KEY>` (Orion Router Dashboard'unda oluşturduğunuz bir Key veya Admin Secret)

---

## 2. Düşünme / Akıl Yürütme (`thinking`) Kullanımı

Farklı yapay zeka sağlayıcıları (Gemini, Claude, OpenAI o-serisi, DeepSeek, Local Chat) düşünme parametrelerini farklı isimlerle (`reasoning_effort`, `thinking_budget`, `budget_tokens` vb.) bekler. 

Orion Router tüm sağlayıcıları tek ve standart bir **`thinking`** parametresi altında birleştirir ve arkada ilgili sağlayıcının beklediği formata otomatik dönüştürür.

### A. Bütçe Modu (Budget Mode)
Gemini 2.5, Local Chat veya token bazlı bütçe destekleyen modeller için:
- **Belirli bir bütçe vermek:** `"thinking": 2048` veya `"thinking": "2048"` (Token cinsinden düşünme limiti).
- **Otomatik / Dinamik düşünme:** `"thinking": -1` veya `"thinking": "-1"`.
- **Düşünmeyi kapatmak:** `"thinking": 0` (Gemini gibi destekleyen modellerde düşünme bloğunu tamamen devre dışı bırakır).

### B. Seviye Modu (Level Mode)
OpenAI `o1`/`o3-mini`, Anthropic Claude 3.7 Sonnet gibi seviye bazlı modeller için:
- **Düşünme seviyesi belirlemek:** `"thinking": "low"`, `"thinking": "medium"`, `"thinking": "high"`

### C. Sağlayıcı Varsayılanı (API Default)
Eğer modele ne bütçe ne de seviye dayatmak istiyorsanız ve sağlayıcının orijinal varsayılanına bırakmak istiyorsanız:
- `thinking` parametresini göndermeyin veya `"thinking": "api_default"` gönderin.

---

## 3. Router Varsayılanları ve `bypass_defaults`

### Model Varsayılanları Nasıl Çalışır?
Orion Router Dashboard'unda (`/models` veya `/groups`) her model için varsayılan bir `temperature`, `thinking` veya `system_prompt` tanımlayabilirsiniz.
- Normal bir API isteğinde `temperature` veya `thinking` göndermezseniz, Router panelde modele tanımladığınız varsayılan değeri isteğe otomatik olarak ekler.

### `bypass_defaults` Nedir?
Eğer bir isteğin **hiçbir router varsayılanına maruz kalmadan**, tamamen gönderdiğiniz saf haliyle upstream sağlayıcıya (OpenAI, Gemini vb.) gitmesini istiyorsanız `bypass_defaults` özelliğini kullanabilirsiniz.

Bu özellik aktif olduğunda:
1. Panelde tanımlı `temperature`, `system_prompt` ve `thinking` değerleri arkadan enjekte **edilmez**.
2. İstekte açıkça ne belirttiyseniz yalnızca o gönderilir; belirtmediğiniz değerler sağlayıcının fabrika ayarlarına bırakılır.

#### Kullanım Yolu 1: HTTP Header (Önerilen)
```http
X-Orion-Bypass-Defaults: true
```

#### Kullanım Yolu 2: JSON Body Parametresi
```json
{
  "model": "gemini-2.5-flash-lite",
  "messages": [{"role": "user", "content": "Merhaba!"}],
  "bypass_defaults": true
}
```

---

## 4. Kod Örnekleri

### Python (`openai` SDK ile)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:20128/v1",
    api_key="orion_admin_secret_key"  # veya Orion Key'iniz
)

# 1. Normal İstek (Thinking Seviyesi ile)
response = client.chat.completions.create(
    model="o3-mini",
    messages=[
        {"role": "user", "content": "9.11 ile 9.9 sayılarından hangisi daha büyüktür?"}
    ],
    extra_body={
        "thinking": "high"  # Tek standart thinking anahtarı
    }
)
print(response.choices[0].message.content)

# 2. Token Bütçeli İstek (Gemini veya Local Chat)
response = client.chat.completions.create(
    model="gemini-2.5-flash-lite",
    messages=[
        {"role": "user", "content": "Python'da hızlı bir quicksort algoritması yaz."}
    ],
    extra_body={
        "thinking": 4096  # 4096 token düşünme bütçesi
    }
)
print(response.choices[0].message.content)

# 3. Router Varsayılanlarını Atlayarak (Bypass Defaults) İstek Atma
response = client.chat.completions.create(
    model="gemini-2.5-flash-lite",
    messages=[
        {"role": "user", "content": "Bana kısa bir şiir yaz."}
    ],
    # Router'ın paneldeki varsayılan sıcaklık ve düşünme ayarlarını zorlamasını engeller:
    extra_headers={
        "X-Orion-Bypass-Defaults": "true"
    }
)
print(response.choices[0].message.content)
```

---

### cURL ile İstek Örnekleri

#### Standart İstek:
```bash
curl -X POST http://localhost:20128/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer orion_admin_secret_key" \
  -d '{
    "model": "gemini-2.5-flash-lite",
    "messages": [{"role": "user", "content": "Merhaba!"}],
    "thinking": 1024,
    "temperature": 0.7
  }'
```

#### Varsayılanları Devre Dışı Bırakan (`bypass_defaults`) İstek:
```bash
curl -X POST http://localhost:20128/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer orion_admin_secret_key" \
  -H "X-Orion-Bypass-Defaults: true" \
  -d '{
    "model": "gemini-2.5-flash-lite",
    "messages": [{"role": "user", "content": "Merhaba!"}]
  }'
```

---

## 5. Local Chat Modelleri İçin Gelişmiş Parametreler

Yerel (`local`) modellerle çalışırken aşağıdaki standart sampling parametrelerini doğrudan JSON gövdesinde gönderebilirsiniz:

- `top_p` (ör. `0.9`)
- `top_k` (ör. `40`)
- `min_p` (ör. `0.05`)
- `repeat_penalty` (ör. `1.05`)

Örnek:
```json
{
  "model": "local-chat",
  "messages": [{"role": "user", "content": "Hikaye anlat."}],
  "top_p": 0.95,
  "top_k": 50,
  "min_p": 0.03,
  "repeat_penalty": 1.1
}
```
