#!/usr/bin/env bash
# macOS / Linux Orion Router CLI Uninstaller
# Bu betik, orionrouter CLI aracının sisteminizde bıraktığı ortam değişkenlerini, profil ayarlarını ve standalone dosyaları temizler.

INSTALL_DIR="$HOME/.orion-router"

echo "Orion Router CLI kalıntıları temizleniyor..."

# 1. CLI dosyasını temizle
if [ -f "$INSTALL_DIR/orionrouter" ]; then
    rm -f "$INSTALL_DIR/orionrouter"
    echo "Silindi: orionrouter"
fi
if [ -f "$INSTALL_DIR/orion-router" ]; then
    rm -f "$INSTALL_DIR/orion-router"
    echo "Silindi: orion-router"
fi

# 2. Profillerden PATH ayarını ve eski fonksiyonları temizle
PROFILES=("$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile")

for PROFILE in "${PROFILES[@]}"; do
    if [ -f "$PROFILE" ]; then
        # Profil içindeki blokları ve satırları sil
        sed -i.bak '/# --- ORION ROUTER CLI START ---/,/# --- ORION ROUTER CLI END ---/d' "$PROFILE" 2>/dev/null || true
        sed -i.bak '/^[[:space:]]*orion-router\([[:space:]]\+start\)\?[[:space:]]*$/d' "$PROFILE" 2>/dev/null || true
        sed -i.bak '/^[[:space:]]*orionrouter\([[:space:]]\+start\)\?[[:space:]]*$/d' "$PROFILE" 2>/dev/null || true
        rm -f "${PROFILE}.bak"
        echo "[OK] Profil temizlendi: $PROFILE"
    fi
done

echo "[OK] Temizlik tamamlandı! Değişikliklerin geçerli olması için terminalinizi kapatıp açabilir veya 'source ~/.bashrc' (veya kullandığınız kabuk profili) komutunu çalıştırabilirsiniz."
