"""
Orion Dashboard - Otomatik Çeviri Scripti
Bu script, dashboard/public/locales dizinindeki eksik çevirileri (İngilizce ile aynı kalan veya olmayan)
Google Translate kullanarak otomatik olarak çevirir ve ilgili dil dosyalarına yazar.

Kullanım:
    python dev/translate_dashboard.py

Gereksinimler:
    pip install deep-translator
"""

import os
import sys
import json
import time

try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("Hata: 'deep-translator' kütüphanesi bulunamadı.")
    print("Lütfen yüklemek için şu komutu çalıştırın:")
    print("pip install deep-translator")
    sys.exit(1)

def main():
    # Yollar
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "dashboard", "public", "locales")
    en_path = os.path.join(locales_dir, "en.json")

    if not os.path.exists(en_path):
        print(f"Hata: İngilizce referans dosyası bulunamadı -> {en_path}")
        return

    # İngilizce dosyayı oku
    with open(en_path, "r", encoding="utf-8-sig") as f:
        en_data = json.load(f)

    # Çevrilecek diller listesi (İngilizce hariç)
    supported_locales = [
        'ar', 'bg', 'bn', 'cs', 'da', 'de', 'el', 'es', 'fa', 'fi', 'fr', 'he', 'hi',
        'hr', 'hu', 'id', 'it', 'ja', 'ko', 'mr', 'ms', 'nl', 'no', 'pl', 'pt-BR', 'pt-PT',
        'ro', 'ru', 'sk', 'sr', 'sv', 'sw', 'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur', 'vi',
        'zh-CN', 'zh-TW'
    ]

    # deep-translator dil kodları eşleştirmesi
    locale_to_deep_lang = {
        'pt-BR': 'pt',
        'pt-PT': 'pt',
        'zh-CN': 'zh-CN',
        'zh-TW': 'zh-TW',
        'he': 'iw'  # İbranice için Google API kodu
    }

    total_translated = 0

    print("Orion Otomatik Çeviri Başlıyor...")
    print("-" * 50)

    for locale in supported_locales:
        file_name = f"{locale}.json"
        file_path = os.path.join(locales_dir, file_name)
        
        # Dosya yoksa veya okunamazsa boş sözlükle başla
        if not os.path.exists(file_path):
            data = {}
        else:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print(f"[{locale}] Okuma hatası: {e}")
                    data = {}
        
        target_lang = locale_to_deep_lang.get(locale, locale)
        
        # Çevrilmemiş (en.json ile aynı veya eksik) anahtarları bul
        keys_to_translate = []
        for key, en_val in en_data.items():
            # Eğer değer İngilizceyle tamamen aynıysa (ve boş değilse) çeviriye gönder
            if key not in data or (data[key] == en_val and en_val.strip() != ""):
                keys_to_translate.append((key, en_val))
                
        if not keys_to_translate:
            print(f"[{locale}] Tüm çeviriler zaten tamam.")
            continue
            
        print(f"[{locale}] -> {len(keys_to_translate)} anahtar çeviriliyor ('{target_lang}' diline)...")
        
        translator = GoogleTranslator(source='en', target=target_lang)
        updated = False
        
        for key, en_val in keys_to_translate:
            try:
                translated_val = translator.translate(en_val)
                # ascii() kullanarak Windows terminalinde karakter çökmesini engelliyoruz
                print(f"  - {key}: {ascii(en_val)} -> {ascii(translated_val)}")
                data[key] = translated_val
                updated = True
                total_translated += 1
                
                # Google Translate engeline (rate-limit) takılmamak için kısa bekleme
                time.sleep(0.15)
            except Exception as e:
                print(f"  [!] Hata: '{key}' çevrilemedi -> {ascii(e)}")
                
        if updated:
            # BOM (utf-8-sig) ile tekrar dosyaya kaydet
            with open(file_path, "w", encoding="utf-8-sig") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[{locale}] Başarıyla kaydedildi.")

    print("-" * 50)
    print(f"İşlem tamamlandı! Toplam {total_translated} anahtar çevirildi.")

if __name__ == "__main__":
    main()
