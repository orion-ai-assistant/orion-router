"""
test-basic.py - Orion Router hiz testi (httpx, SDK-free)
"""
import httpx, json, time

KEY   = "sk-orion-T4wlYzqt11Af2omYK9IjKoj-qpUlwppFcyTpCRWfzOg"
URL   = "http://localhost:3001/v1/chat/completions"

payload = {
    "model": "gemini-2.5-flash-lite",
    "messages": [{"role": "user", "content": "sadece 'selam' yaz"}],
    "stream": True,
    "thinking_level": "0",
}

t0 = time.perf_counter()
first_chunk_time = None

try:
    with httpx.Client(timeout=60) as client:
        with client.stream("POST", URL, json=payload,
                           headers={"Authorization": f"Bearer {KEY}"}) as r:

            if r.status_code != 200:
                body = r.read().decode()
                print(f"[HTTP {r.status_code}] {body}")
            else:
                for line in r.iter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    try:
                        chunk = json.loads(line[6:])
                    except Exception:
                        continue

                    # Hata chunk'u
                    if "error" in chunk:
                        err = chunk["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        print(f"\n[HATA] {msg}")
                        break

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        if first_chunk_time is None:
                            first_chunk_time = time.perf_counter()
                        print(content, end="", flush=True)

except httpx.ConnectError:
    print("[HATA] Sunucuya bağlanılamadı (127.0.0.1:20128). Orion çalışıyor mu?")
except Exception as e:
    print(f"[HATA] {e}")

t1 = time.perf_counter()
ttfb = (first_chunk_time - t0) * 1000 if first_chunk_time else -1
if ttfb >= 0:
    print(f"\n[TTFB: {ttfb:.0f}ms | toplam: {(t1-t0)*1000:.0f}ms]")
else:
    print(f"[toplam: {(t1-t0)*1000:.0f}ms | içerik gelmedi]")