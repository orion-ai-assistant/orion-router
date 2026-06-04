#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"

echo "=========================================="
echo "    Orion Router Native Kurulum Aracı     "
echo "=========================================="

if [ "$MODE" != "local" ] && [ "$MODE" != "docker" ]; then
  echo -e "\nHATA: Kurulum modunu belirtmediniz!"
  echo "Lütfen terminalde scripti aşağıdaki gibi parametre vererek çalıştırın:\n"
  echo "  1. Local Kurulum:"
  echo "     ./install.sh local\n"
  echo "  2. Docker Kurulum:"
  echo "     ./install.sh docker\n"
  exit 1
fi

echo "Kurulum Modu: $MODE"
INSTALL_DIR="$HOME/.orion-router"
REPO_URL="https://github.com/krstalacam/orion-router.git"
echo "Hedef Dizin:  $INSTALL_DIR"

# 1. Gereksinim Kontrolleri
echo -e "\n[1/5] Sistem gereksinimleri kontrol ediliyor..."
if [ "$MODE" = "local" ]; then
  REQUIRED_CMDS=(git python3 npm)
else
  REQUIRED_CMDS=(git docker)
fi

for cmd in "${REQUIRED_CMDS[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Hata: '$cmd' bulunamadı! Lütfen kurup tekrar deneyin." >&2
    exit 1
  fi
done
echo "✔ Gereksinimler karşılandı (${REQUIRED_CMDS[*]})."

# 2. Repo Klonlama veya Güncelleme
echo -e "\n[2/5] Orion Router klasörüne ayarlanıyor..."

PID_FILE="$INSTALL_DIR/.orion.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        pkill -P "$OLD_PID" 2>/dev/null || true
        kill -9 "$OLD_PID" 2>/dev/null || true
        sleep 1
        echo "[!] Arka planda çalışan eski Orion Router durduruldu."
    fi
    rm -f "$PID_FILE"
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
  fi
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  echo "✔ Klasör var, GitHub'daki en güncel kodlar zorla çekiliyor..."
  cd "$INSTALL_DIR"
  git fetch origin main || { echo "[HATA] git fetch başarısız oldu. Bağlantı sorunu olabilir."; exit 1; }
  git reset --hard origin/main || { echo "[HATA] Kodları güncelleme (reset) başarısız oldu."; exit 1; }
fi
cd "$INSTALL_DIR"

# --- Akıllı .env Kontrolü ---
echo -e "\n[*] .env dosyası kontrol ediliyor..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✔ .env dosyası bulunamadı. Docker uyarılarını engellemek için .env.example dosyasından yeni bir .env üretildi."
    else
        echo "[!] .env.example bulunamadı, boş bir .env dosyası oluşturuluyor..."
        touch .env
    fi
else
    echo "✔ Mevcut .env dosyası tespit edildi. Konfigürasyonlarınızın ezilmemesi için değişiklik yapılmadı."
fi

# 3 & 4. Bağımlılıklar
if [ "$MODE" = "local" ]; then
    echo -e "\n[3/5] Python paketleri (pip) yükleniyor..."
    python3 -m pip install -e .
    echo -e "\n[4/5] Dashboard bağımlılıkları (NPM) yükleniyor..."
    if [ -d "dashboard" ]; then
        (cd dashboard && npm install)
    fi
else
    echo -e "\n[3/5] ve [4/5] Adımları Atlanıyor..."
    echo "Docker modu seçildiği için local bağımlılıklar indirilmeyecek. Sadece GHCR imajları çekilecek."
fi

# 5. Global Komutun Yüklenmesi
echo -e "\n[5/5] Global 'orion-router' komutu sisteme yükleniyor..."

if [ -n "${ZSH_VERSION:-}" ]; then
  PROFILE="$HOME/.zshrc"
elif [ -n "${BASH_VERSION:-}" ]; then
  PROFILE="$HOME/.bashrc"
else
  PROFILE="$HOME/.profile"
fi

# Eski kalıntıları temizle
if [ -f "$PROFILE" ]; then
  sed -i.bak '/# --- ORION ROUTER CLI START ---/,/# --- ORION ROUTER CLI END ---/d' "$PROFILE" 2>/dev/null || true
  sed -i.bak '/^[[:space:]]*orion-router\([[:space:]]\+start\)\?[[:space:]]*$/d' "$PROFILE" 2>/dev/null || true
  rm -f "${PROFILE}.bak"
fi

# Moduna göre ilgili CLI fonksiyonunu profile bas
if [ "$MODE" = "local" ]; then
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
            fi
            rm -f "$PID_FILE"
        fi

        echo "Orion Router local olarak başlatılıyor..."
        cd "$PROJECT_DIR"
        nohup python3 orion.py prod > "$LOG_FILE" 2> "$ERROR_LOG_FILE" &
        echo $! > "$PID_FILE"
        
        echo "[OK] Orion Router arka planda çalışmaya başladı!"
        echo "[OK] Artik su komutlari kullanabilirsiniz: orion-router start | stop | logs | help"
        echo "----------------------------------------------------"
        echo "  Canlı loglar başlıyor... (Çıkmak için Ctrl+C basabilirsiniz)"
        echo "----------------------------------------------------"
        tail -f "$LOG_FILE"
    elif [ "$ACTION" = "stop" ]; then
        if [ -f "$PID_FILE" ]; then
            local PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                pkill -P "$PID" 2>/dev/null || true
                kill -9 "$PID" 2>/dev/null || true
                echo "[OK] Orion Router ana süreci ve alt süreçleri durduruldu."
            else
                echo "Süreç zaten sonlanmış."
            fi
            rm -f "$PID_FILE"
        else
            echo "Çalışan etkin bir Orion Router süreci (.orion.pid) bulunamadı."
        fi
    elif [ "$ACTION" = "logs" ]; then
        if [ -f "$ERROR_LOG_FILE" ]; then
            echo -e "\n[!] SON HATALAR (orion_error.log):"
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
else
cat >> "$PROFILE" << 'EOF'

# --- ORION ROUTER CLI START ---
orion-router() {
    local ACTION="${1:-help}"
    local PROJECT_DIR="$HOME/.orion-router"
    local COMPOSE_FILE="docker-compose.ghcr.yml"

    if [ "$ACTION" = "help" ] || [ -z "$ACTION" ]; then
        echo ""
        echo "  Orion Router CLI (Docker Mode)"
        echo "  --------------------------------"
        echo "  Kullanım: orion-router <komut>"
        echo ""
        echo "  Komutlar:"
        echo "    start   Container'ı arka planda başlatır"
        echo "    stop    Çalışan container'ı durdurur"
        echo "    logs    Container loglarını canlı olarak gösterir"
        echo "    help    Bu yardım menüsünü gösterir"
        echo ""
    elif [ "$ACTION" = "start" ]; then
        echo "Docker durumu kontrol ediliyor..."
        local DOCKER_READY=0
        if docker info >/dev/null 2>&1; then
            DOCKER_READY=1
        else
            echo "[!] Docker Daemon aktif değil. Başlatılmaya çalışılıyor..."
            if command -v systemctl >/dev/null 2>&1; then
                sudo systemctl start docker || true
            elif [ "$(uname)" = "Darwin" ]; then
                open -a Docker || true
            fi

            echo "[*] Docker Engine hazır olması bekleniyor (max 30 saniye)..."
            for i in {1..6}; do
                sleep 5
                if docker info >/dev/null 2>&1; then
                    DOCKER_READY=1
                    echo "[OK] Docker Engine aktif ve hazır!"
                    break
                fi
                echo "    Hazırlanıyor... ($((i * 5)) saniye geçen süre)"
            done
        fi

        if [ $DOCKER_READY -eq 0 ]; then
            echo -e "\n[HATA] Docker otomatik olarak başlatılamadı veya motor zamanında yanıt vermedi."
            echo "Lütfen Docker uygulamanızı açın ve komutu tekrar deneyin.\n"
            return 1
        fi

        echo "Orion Router Docker üzerinde (GHCR İmajlarla) başlatılıyor..."
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" -p orion-router up -d
        echo "[OK] Container başladı! Kapatmak icin 'orion-router stop' yazabilirsiniz."
        echo "[OK] Artik su komutlari kullanabilirsiniz: orion-router start | stop | logs | help"
        echo "----------------------------------------------------"
        echo "  Canlı loglar başlıyor... (Çıkmak için Ctrl+C basabilirsiniz)"
        echo "----------------------------------------------------"
        docker compose -f "$COMPOSE_FILE" -p orion-router logs -f
    elif [ "$ACTION" = "stop" ]; then
        echo "Orion Router Docker üzerinde durduruluyor..."
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" -p orion-router stop
        echo "[OK] Container başarıyla durduruldu."
    elif [ "$ACTION" = "logs" ]; then
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" -p orion-router logs -f
    else
        echo "Geçersiz komut. Yardım için 'orion-router help' yazabilirsiniz."
    fi
}
# --- ORION ROUTER CLI END ---
EOF
fi

# Değişiklikleri mevcut oturuma yansıt
# shellcheck source=/dev/null
source "$PROFILE"

echo ""
echo "[OK] Kurulum tamamlandı."
echo "[OK] 'orion-router' komutu bu terminalde ve yeni terminallerde hazır."
echo "     Kullanabileceğiniz komutlar: orion-router start | stop | logs | help"
echo "     Başlattıktan sonra bu terminali kapatabilirsiniz."
echo "[OK] Orion Router başlatılıyor..."

orion-router start