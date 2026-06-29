import os
import time
import openai
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("ROUTER_API_KEY")

client = openai.OpenAI(
    base_url="http://127.0.0.1:20128/v1",
    api_key=api_key
)

messages = []

while True:
    try: user_input = input("- ")
    except (KeyboardInterrupt, EOFError): break
    
    if user_input.lower() in ('q', 'quit'): break
    if not user_input.strip(): continue
    
    messages.append({"role": "user", "content": user_input})
    
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model='gemini-2.5-flash-lite',
        messages=messages,
        stream=True,
        extra_body={"thinking_level": "1024"}
    )
    
    print("+ ", end="")
    full_content = ""
    ttfb = None
    for chunk in resp:
        delta = chunk.choices[0].delta
        reasoning = delta.model_extra.get("reasoning_content")
        content = delta.content
        
        if not ttfb and (content or reasoning):
            ttfb = (time.perf_counter() - t0) * 1000
        if reasoning:
            print(f"\033[90m{reasoning}\033[0m", end="", flush=True)
        if content:
            full_content += content
            print(content, end="", flush=True)
            
    print(f"\n\033[90m[TTFB: {ttfb:.0f}ms]\033[0m\n" if ttfb else "\n")
    messages.append({"role": "assistant", "content": full_content})