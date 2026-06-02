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
INSTALL_DIR="$HOME/.orion-router"
if [ ! -d "$INSTALL_DIR" ]; then
  git clone https://github.com/krstalacam/orion-router.git "$INSTALL_DIR"
else
  echo "✔ Klasör var, en güncel kodlar çekiliyor (git pull)..."
  cd "$INSTALL_DIR"
  git pull
fi
cd "$INSTALL_DIR"

# 3. Python Bağımlılıkları
echo -e "\n[3/5] Python paketleri (pip) yükleniyor..."
python3 -m pip install -e .

# 4. Node.js Bağımlılıkları
echo -e "\n[4/5] Dashboard bağımlılıkları (NPM) yükleniyor..."
(cd dashboard && npm install)

# 5. Global Komutun Yüklenmesi
echo -e "\n[5/5] Global 'orion-router' komutu sisteme yükleniyor..."

# Shell profile'ı belirle
if [ -n "$ZSH_VERSION" ]; then
  PROFILE="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ]; then
  PROFILE="$HOME/.bashrc"
else
  PROFILE="$HOME/.profile"
fi

# Eski kirli kalıntıları temizle
if [ -f "$PROFILE" ]; then
  sed -i '/# --- ORION ROUTER CLI START ---/,/# --- ORION ROUTER CLI END ---/d' "$PROFILE" 2>/dev/null || true
  sed -i '/^[[:space:]]*orion-router\([[:space:]]\+start\)\?[[:space:]]*$/d' "$PROFILE" 2>/dev/null || true
fi

# Yeni fonksiyonu ekle
cat >> "$PROFILE" << 'EOF'

# --- ORION ROUTER CLI START ---
orion-router() {
    local ACTION="${1:-help}"
    local PROJECT_DIR="$HOME/.orion-router"
    local PID_FILE="$PROJECT_DIR/.orion.pid"
    local LOG_FILE="$PROJECT_DIR/orion_output.log"
    local ERROR_LOG_FILE="$PROJECT_DIR/orion_error.log"

    if [ "$ACTION" = "help" ] || [ -z "$ACTION" ]; then
        echo ""
        echo "  Orion Router CLI"
        echo "  --------------------------------"
        echo "  Kullanım: orion-router <komut>"
        echo ""
        echo "  Komutlar:"
        echo "    start   Sunucuyu arka planda başlatır"
        echo "    stop    Çalışan sunucuyu ve tüm alt süreçleri durdurur"
        echo "    logs    Arka plan loglarını ve hataları gösterir"
        echo "    help    Bu yardım menüsünü gösterir"
        echo ""
    elif [ "$ACTION" = "start" ]; then
        if [ -f "$PID_FILE" ]; then
            local PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "[OK] Orion Router zaten arka planda çalışıyor!"
                echo "Logları görmek için: orion-router logs"
                return
            else
                rm -f "$PID_FILE"
            fi
        fi

        echo "Orion Router local olarak başlatılıyor..."
        cd "$PROJECT_DIR"
        nohup python3 orion.py prod > "$LOG_FILE" 2> "$ERROR_LOG_FILE" &
        echo $! > "$PID_FILE"
        
        echo "[OK] Orion Router arka planda çalışmaya başladı!"
        echo "[OK] Artik su komutlari kullanabilirsiniz: orion-router start | stop | logs | help"
        echo "[OK] Bu terminali kapatabilirsiniz; Orion Router arka planda calismaya devam eder."
        echo "----------------------------------------------------"
        echo "  Canlı loglar başlıyor... (Çıkmak için Ctrl+C basabilirsiniz)"
        echo "----------------------------------------------------"
        tail -f "$LOG_FILE"
    elif [ "$ACTION" = "stop" ]; then
        if [ -f "$PID_FILE" ]; then
            local PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -TERM "$PID"
                echo "[OK] Orion Router ana süreci durduruldu."
            else
                echo "Süreç zaten sonlanmış."
            fi
            rm -f "$PID_FILE"
        else
            echo "Çalışan etkin bir Orion Router süreci (.orion.pid) bulunamadı."
        fi
    elif [ "$ACTION" = "logs" ]; then
        if [ -f "$ERROR_LOG_FILE" ]; then
            echo ""
            echo "[!] SON HATALAR (orion_error.log):"
            tail -15 "$ERROR_LOG_FILE"
            echo "----------------------------------------------------"
        fi
        if [ -f "$LOG_FILE" ]; then
            echo "  Canlı loglar başlıyor... (Çıkmak için Ctrl+C basabilirsiniz)"
            tail -f "$LOG_FILE"
        else
            echo "Henüz bir log dosyası yok."
        fi
    else
        echo "Geçersiz komut. Yardım için 'orion-router help' yazabilirsiniz."
    fi
}
# --- ORION ROUTER CLI END ---
EOF

# Mevcut oturuma yükle
source "$PROFILE"

echo ""
echo "[OK] Kurulum tamamlandı."
echo "[OK] 'orion-router' komutu bu terminalde ve yeni terminallerde hazir."
echo "     Kullanabileceginiz komutlar: orion-router start | stop | logs | help"
echo "     Baslattiktan sonra bu terminali kapatabilirsiniz."
echo "[OK] Orion Router başlatılıyor..."

orion-router start
