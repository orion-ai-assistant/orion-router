import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:20128/v1",
    api_key='sk-orion-T4wlYzqt11Af2omYK9IjKoj-qpUlwppFcyTpCRWfzOg'
)

messages = []

while True:
    try: user_input = input("- ")
    except (KeyboardInterrupt, EOFError): break
    
    if user_input.lower() in ('q', 'quit'): break
    if not user_input.strip(): continue
    
    messages.append({"role": "user", "content": user_input})
    
    resp = client.chat.completions.create(
        model='gemini-3.1-flash-lite',
        messages=messages,
        extra_body={"thinking_level": "high"}  # e.g. "low" | 1024
    )
    
    print("+ ", end="")
    full_content = ""
    for chunk in resp:
        delta = chunk.choices[0].delta
        reasoning = delta.model_extra.get("reasoning_content")
        content = delta.content
        if reasoning:
            print(f"\033[90m{reasoning}\033[0m", end="", flush=True)
        if content:
            full_content += content
            print(content, end="", flush=True)
            
    print("\n")
    messages.append({"role": "assistant", "content": full_content})