import os
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
    
    resp = client.chat.completions.create(
        model='local-model',
        messages=messages,
        extra_body={"thinking_level": "low"},  # e.g. "low" | 1024
        stream = True
    )
    
    print("+ ", end="")
    full_content = ""
    
    if hasattr(resp, 'choices'):
        # Non-stream (Tek seferde dönen yanıt)
        msg = resp.choices[0].message
        reasoning = msg.model_extra.get("reasoning_content") if msg.model_extra else None
        if reasoning:
            print(f"\033[90m{reasoning}\033[0m", end="")
        full_content = msg.content or ""
        print(full_content, end="")
    else:
        # Stream (Parça parça dönen yanıt)
        for chunk in resp:
            delta = chunk.choices[0].delta
            reasoning = delta.model_extra.get("reasoning_content") if delta.model_extra else None
            content = delta.content
            if reasoning:
                print(f"\033[90m{reasoning}\033[0m", end="", flush=True)
            if content:
                full_content += content
                print(content, end="", flush=True)
    print("\n")
    messages.append({"role": "assistant", "content": full_content})