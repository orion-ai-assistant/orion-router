# Gemini Multimodal (Çoklu Ortam) ve Dosya API Kullanım Kılavuzu

Google Gemini, metin dışındaki büyük boyutlu dosyaları (Video, Ses, PDF) işleme konusunda oldukça güçlüdür. Bu dizinde bulunan `files.py` ve `chat.py` modülleri, bu çoklu ortam desteğini Orion Router üzerinden çalıştırmak için tasarlanmıştır.

## Mimarinin Çalışma Mantığı

Gemini'de büyük boyutlu dosyaları doğrudan sohbet isteğinin içine base64 olarak gömmek yerine iki adımlı bir süreç izlenir:
1. **Dosya Yükleme (Upload):** Dosya öncelikle `/v1/files` (veya ilgili yükleme endpoint'i) aracılığıyla Google sunucularına yüklenir (`files.py`).
2. **Sorgulama (Chat):** Yükleme tamamlandıktan sonra dönen `file_uri` adresi sohbet isteğinde referans gösterilerek dosya hakkında soru sorulur (`chat.py`).

---

## 1. Dosya Yükleme (Files API)

`files.py` dosyası, yüklenen dosyaları Gemini File API'ye aktarır. Video gibi büyük dosyalar yüklendikten sonra Google tarafında işlenme süreci başlar. Dosya durumu `ACTIVE` olana kadar sohbetlerde kullanılamaz. `files.py` bu bekleme (polling) sürecini otomatik yönetir.

### Desteklenen Formatlar ve MIME Tipleri
- **Resimler:** `image/jpeg`, `image/png`, `image/webp`, `image/gif`
- **Videolar:** `video/mp4`, `video/mov`, `video/mpeg` vb.
- **Ses Dosyaları:** `audio/mp3`, `audio/wav`, `audio/ogg` vb.
- **Dokümanlar:** `application/pdf`, `text/plain` vb.

---

## 2. Chat Üzerinden Soru Sorma (Chat API)

`chat.py` dosyasındaki `stream_chat` metodu, OpenAI formatındaki çoklu parçalı (multimodal) mesajları algılar. Mesajın `content` alanı bir liste (dizi) olduğunda, `file_uri` tipindeki dosyaları Gemini formatındaki `Part.from_uri` nesnelerine dönüştürür.

---

## 3. Örnek Kullanım Kodları (Python OpenAI SDK)

Aşağıdaki örneklerde, dosyaları Router üzerinden yükleyip nasıl soru soracağınız gösterilmektedir.

### A) Video Analizi Örneği (Büyük Dosyalar)

Büyük video dosyalarında, önce dosyayı yükleyip ardından dönen ID ile soru sormak zorunludur:

```python
import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:20128/v1",
    api_key="sk-orion-your-key"
)

# 1. Dosyayı Router'a yükle (providers/gemini/files.py tetiklenir)
uploaded_file = client.files.create(
    file=open("sunum.mp4", "rb"),
    purpose="vision"
)

# Dönen dosya ID'sini (URI) alıyoruz
# Not: Router'ınızın response yapısına göre .id veya .uri kullanılabilir.
file_uri = uploaded_file.id 

# 2. Dosyayı referans göstererek soru sor
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Bu videoda ne anlatılıyor? 2. dakikada gösterilen slaytı özetle."
            },
            {
                "type": "file_uri",
                "file_uri": file_uri,
                "mime_type": "video/mp4"
            }
        ]
    }
]

response = client.chat.completions.create(
    model="gemini-3.1-pro",
    messages=messages
)
print(response.choices[0].message.content)
```

### B) Ses Analizi Örneği (Müzik veya Konuşma Kaydı)

Ses dosyalarınızı da aynı mantıkla yükleyip deşifre ettirebilir veya analiz ettirebilirsiniz:

```python
# 1. Ses dosyasını yükle
uploaded_audio = client.files.create(
    file=open("toplanti_kaydi.mp3", "rb"),
    purpose="vision"
)

# 2. Ses dosyasını sor
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Bu ses kaydında konuşulanları Türkçe'ye deşifre et ve önemli kararları listele."
            },
            {
                "type": "file_uri",
                "file_uri": uploaded_audio.id,
                "mime_type": "audio/mp3"
            }
        ]
    }
]

response = client.chat.completions.create(
    model="gemini-3.1-flash",
    messages=messages
)
print(response.choices[0].message.content)
```

### C) Görsel Sorgulama Örneği (Resimler)

Görseller de aynı `file_uri` yapısıyla sorgulanabilir:

```python
# 1. Resmi yükle
uploaded_image = client.files.create(
    file=open("grafik.png", "rb"),
    purpose="vision"
)

# 2. Resim hakkında soru sor
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Bu grafikteki yıllık büyüme oranını yorumlar mısın?"
            },
            {
                "type": "file_uri",
                "file_uri": uploaded_image.id,
                "mime_type": "image/png"
            }
        ]
    }
]

response = client.chat.completions.create(
    model="gemini-3.1-flash",
    messages=messages
)
print(response.choices[0].message.content)
```
