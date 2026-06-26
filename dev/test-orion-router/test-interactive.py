"""
test-interactive.py - Orion Router 
"""
import time
import openai

print("Sistem başlatılıyor, lütfen bekleyin...")

client = openai.OpenAI(
    base_url='http://localhost:20128/v1', 
    api_key='sk-orion-T4wlYzqt11Af2omYK9IjKoj-qpUlwppFcyTpCRWfzOg'
)

# Bağlantıyı önden ısıtma (Warm-up) bu hiçbir işe yaramıyor olabilir?
try:
    client._client.get("/health", timeout=5.0)
except Exception:
    pass

print("Hazır! Orion Router'a bağlanıldı. Çıkmak için 'q' yazın.\n")

# İNTERAKTİF DÖNGÜ
while True:
    try:
        user_input = input("Sen: ").strip()
    except KeyboardInterrupt:
        break

    if user_input.lower() in ['q', 'çıkış', 'quit', 'exit']:
        break
    if not user_input:
        continue

    t_start = time.perf_counter()
    first_chunk = None
    
    try:
        resp = client.chat.completions.create(
            model='openai/gpt-oss-120b',
            messages=[{'role': 'user', 'content': user_input}],
            stream=True,
            extra_body={"thinking_level": "medium"} 
        )
        
        print("Orion: ", end="", flush=True)
        
        for chunk in resp:
            if first_chunk is None:
                t_first = time.perf_counter()
                first_chunk = chunk
            
            delta = chunk.choices[0].delta
            
            # Reasoning (Düşünce) verisini yakalama
            extra = getattr(delta, "model_extra", {}) or {}
            reasoning = getattr(delta, "reasoning_content", extra.get("reasoning_content", ""))
            
            if reasoning:
                print(f"\033[90m{reasoning}\033[0m", end="", flush=True)

            # Asıl içeriği yakalama
            if delta.content:
                print(delta.content, end="", flush=True)
                
        if first_chunk:
            t_end = time.perf_counter()
            print(f"\n\n[İstatistik -> İlk Harf (TTFB): {(t_first - t_start)*1000:.0f}ms | Toplam Süre: {(t_end - t_start)*1000:.0f}ms]\n")
            
    except Exception as e:
        print(f"\n[Hata]: {e}\n")

print("\nGörüşmek üzere!")