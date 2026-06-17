"""
dev/test-orion-router/test-virtual-key.py
------------------------------------------
Virtual key ve temel API bağlantı testi.

Kullanım:
    python test-virtual-key.py --key sk-orion-XXXX [--url http://localhost:20128]
    python test-virtual-key.py --key sk-orion-XXXX --model gemini-2.5-flash
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

DEFAULT_URL = "http://127.0.0.1:20128"
DEFAULT_MODEL = "gemini-2.5-flash"


def test_virtual_key(base_url: str, api_key: str, model: str):
    print(f"\n{'='*55}")
    print(f"  Orion Router Virtual Key Testi")
    print(f"{'='*55}")
    print(f"  URL   : {base_url}")
    print(f"  Model : {model}")
    print(f"  Key   : {api_key[:15]}...{api_key[-6:]}")
    print(f"{'='*55}\n")

    # 1. Health check
    print("1️⃣  Health check...")
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=5) as r:
            body = json.loads(r.read())
            print(f"   ✔ Server OK: {body}")
    except Exception as e:
        print(f"   ✘ HATA: {e}")
        print("   Sunucu çalışmıyor olabilir!")
        sys.exit(1)

    # 2. Non-streaming chat (stream=True gerekiyor, bunu kontrol et)
    print("\n2️⃣  Stream chat testi...")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Merhaba, 1+1 kaçtır?"}],
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
            print(f"   HTTP Status: {status}")
            if status == 200:
                content_chars = 0
                for line_bytes in r:
                    line = line_bytes.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                print(content, end="", flush=True)
                                content_chars += len(content)
                        except Exception:
                            pass
                print(f"\n\n   ✔ Başarılı! {content_chars} karakter yanıt alındı.")
            else:
                body = r.read().decode("utf-8")
                print(f"   ✘ Beklenmeyen durum kodu: {status}\n   {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err_data = json.loads(body)
            detail = err_data.get("detail", body)
        except Exception:
            detail = body
        print(f"   ✘ HTTP {e.code} HATA: {detail}")
        if e.code == 401:
            print("\n   ⚠️  KEY GEÇERSİZ! Olası nedenler:")
            print("      - Bu key farklı bir ortamda (dev/prod) oluşturulmuş")
            print("      - Dashboard'dan yeni bir key oluşturun ve bu scripti güncelleyin")
        elif e.code == 400 and "model" in detail:
            print("\n   ⚠️  Model adı bulunamadı. Model groups veya models ayarlarınızı kontrol edin.")
    except Exception as e:
        print(f"   ✘ Bağlantı hatası: {e}")

    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orion Router Virtual Key Testi")
    parser.add_argument("--key", required=True, help="Virtual API key (sk-orion-...)")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Router URL (default: {DEFAULT_URL})")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model adı (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    if not args.key.startswith("sk-orion-"):
        print("HATA: Key 'sk-orion-' ile başlamalıdır.")
        sys.exit(1)

    test_virtual_key(args.url, args.key, args.model)
