#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "    Orion Router Native Kurulum Aracı     "
echo "=========================================="

# 1. Gereksinim Kontrolleri
echo "[1/5] Sistem gereksinimleri kontrol ediliyor..."
for cmd in git python3 npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Hata: $cmd bulunamadı! Lütfen kurup tekrar deneyin." >&2
    exit 1
  fi
done
echo "✔ Tüm bağımlılıklar mevcut (Git, Python, NPM)."

# 2. Repo Klonlama
echo -e "\n[2/5] Orion Router klonlanıyor..."
if [ ! -d "orion-router" ]; then
  git clone https://github.com/krstalacam/orion-router.git
else
  echo "✔ 'orion-router' klasörü zaten var, atlanıyor."
fi
cd orion-router

# 3. Python Bağımlılıkları
echo -e "\n[3/5] Python paketleri (pip) yükleniyor..."
python3 -m pip install -e .

# 4. Node.js Bağımlılıkları
echo -e "\n[4/5] Dashboard bağımlılıkları (NPM) yükleniyor..."
(cd dashboard && npm install)

# 5. Sistemi Başlat
echo -e "\n[5/5] Orion Router Prodüksiyon modunda başlatılıyor..."
python3 prod.py