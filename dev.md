
**Başlatmak için:**
```powershell
docker compose -f docker-compose.dev.yml up -d
```

**Durdurmak için:**
```powershell
docker compose -f docker-compose.dev.yml down
```

**Logları takip etmek için:**
```powershell
docker compose -f docker-compose.dev.yml logs -f router
```

*(Konteynerleri bu yeni dosya ile yeniden başlattım, şu an sorunsuz bir şekilde çalışıyor ve kod değişikliklerini dinlemeye hazır!)*