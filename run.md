# Orion Router


Gelisme ve Canli Ortam Rehberi

Bu proje, gelistirici deneyimini (Hiz ve HMR - Hot Module Replacement) en ust duzeye cikarmak ve ayni zamanda canli (Production) ortamda en yuksek performansi verecek sekilde iki farkli yapida tasarlanmistir.

---

## 1. Gelistirme (Development) Ortami

Kod yazarken, aninda guncellemeleri (Ctrl+S yaptiginda sayfanin aninda yenilenmesi) gormek icin bu ortami kullanmalisin.

**Nasil Calistirilir?**
Proje ana dizininde PowerShell ac ve dogrudan dev.ps1 calistir:

```powershell
.\dev.ps1
```

Not: dev.bat yerine dev.ps1 kullanmak, Ctrl+C sonrasi cmd.exe'den gelen "Terminate batch job (Y/N)?" sorusunu engeller ve loglarin ayni terminalde kalmasini saglar.

Bu komut sunlari yapar:
1. **Veritabani:** Docker uzerinde `router-db` adinda calisir.
2. **Backend (FastAPI):** `.env` icindeki `ROUTER_DEV_PORT` (varsayilan 20129) uzerinden calisir.
3. **Frontend (Next.js):** Node.js ile `http://localhost:3001/dashboard` portunda calisir (Hot-Reloading aktiftir).



## 2. Uretim (Production / Canli) Ortami

Projenin gelistirme asamasi bittiginde ve gercek bir sunucuda (veya yerel bilgisayarinda son halini) calistirmak istediginde bu ortami kullanmalisin.

**Nasil Calistirilir?**
Normal Docker Compose dosyasini kullanarak projeyi ayaga kaldirabilirsin:

```powershell
docker compose up -d --build
```
