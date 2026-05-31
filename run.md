# Orion Router

Geliştirme ve Canlı Ortam Rehberi

Bu proje, Docker'a olan bağımlılığı ortadan kaldırarak tamamen yerel (native) Windows üzerinde çalışacak şekilde tasarlanmıştır. Veritabanı olarak **taşınabilir (portable) PostgreSQL** kullanır. Bilgisayarınıza hiçbir şey kurmanıza gerek yoktur; scriptler gerekli dosyaları (~80 MB) otomatik indirir ve izole bir klasörde çalıştırır.

**Ön Koşullar:** Python 3.11+ ve Node.js kurulu olmalı.

---

## 1. Geliştirme (Development) Ortamı

Kod yazarken, anında güncellemeleri (Hot-Reload) görmek için bu ortamı kullanmalısın.

**Nasıl Çalıştırılır?**

```powershell
python dev.py
```

Bu komut şunları yapar:
1. **PostgreSQL:** Portable binary otomatik indirilir (ilk seferde), `.pgdata-dev/` klasöründe **Port 5444** üzerinden çalışır.
2. **Backend (FastAPI):** `.env` içindeki `ROUTER_DEV_PORT` (varsayılan 20129) üzerinden, **hot-reload** ile çalışır.
3. **Frontend (Next.js):** `http://localhost:3001/dashboard` üzerinden, **hot-reload** ile çalışır.

---

## 2. Üretim (Production) Ortamı

Projenin son halini Docker olmadan yerel Windows'ta çalıştırmak için.

**Nasıl Çalıştırılır?**

```powershell
python prod.py
```

Bu komut şunları yapar:
1. **PostgreSQL:** `.pgdata-prod/` klasöründe **Port 5433** üzerinden çalışır.
2. **Dashboard:** Next.js projesi `npm run build` ile derlenir ve `out/` klasörüne çıkarılır.
3. **Tek Port:** FastAPI, Dashboard statik dosyalarını kendi üzerinden sunar. Dashboard ve API tek bir portta (`ROUTER_PORT`, varsayılan 20128) çalışır.

---

## 3. Acil Durdurma

`CTRL+C` normalde her şeyi temiz kapatır. Arka planda takılı kalan bir süreç varsa:

```powershell
python stop.py
```

Bu script tüm portları (3001, 20128, 20129, 5433, 5444) boşaltır ve PostgreSQL'i durdurur.


---

## 1. Geliştirme (Development) Ortamı

Kod yazarken, anında güncellemeleri (Hot-Reload) görmek için bu ortamı kullanmalısın.

**Nasıl Çalıştırılır?**
Proje ana dizininde PowerShell aç ve doğrudan `dev.ps1` çalıştır:

```powershell
.\dev.ps1
```

Bu komut şunları yapar:
1. **Veritabanı:** PostgreSQL Portable otomatik indirilir (ilk seferde), `tools/pgsql` altına kurulur ve `.pgdata-dev` klasöründe **Port 5444** üzerinden çalışır.
2. **Backend (FastAPI):** `.env` içindeki `ROUTER_DEV_PORT` (varsayılan 20129) üzerinden çalışır.
3. **Frontend (Next.js):** Node.js ile `http://localhost:3001/dashboard` portunda çalışır (Hot-Reloading aktiftir).

---

## 2. Üretim (Production / Canlı) Ortamı

Projenin geliştirme aşaması bittiğinde, yerel bilgisayarında son halini test etmek veya statik olarak çalıştırmak için bu ortamı kullanmalısın. Docker'a ihtiyaç duymaz.

**Nasıl Çalıştırılır?**
Proje ana dizininde PowerShell aç ve doğrudan `prod.ps1` çalıştır:

```powershell
.\prod.ps1
```

Bu komut şunları yapar:
1. **Veritabanı:** `.pgdata-prod` klasöründe **Port 5433** üzerinden bağımsız bir production veritabanı çalıştırır.
2. **Dashboard:** Next.js projesi `npm run build` ile derlenerek `out` klasörüne çıkarılır.
3. **Backend & Frontend (Tek Port):** FastAPI, oluşturulan Dashboard statik dosyalarını kendi üzerinden sunar. Tıpkı Docker'da olduğu gibi **Dashboard ve Backend tek bir portta** (varsayılan `.env` içindeki `ROUTER_PORT` veya 20128) çalışır.

---

## 3. Acil Durdurma (Stop)

Script'leri `CTRL+C` ile durdurduğunda genellikle her şey düzgün kapanır. Ancak arka planda asılı kalan bir süreç veya PostgreSQL servisi olursa, temizlik yapmak için şu scripti çalıştırabilirsin:

```powershell
.\stop.ps1
```

Bu script ilgili tüm portları (20128, 20129, 5433, 5444) boşaltır ve veritabanlarını durdurur.
