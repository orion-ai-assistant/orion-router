import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:20128/v1",
    api_key="sk-orion-T4wlYzqt11Af2omYK9IjKoj-qpUlwppFcyTpCRWfzOg"
)

response = client.chat.completions.create(
    model="gemini-2.5-flash", 
    messages=[{"role": "user", "content": "Merhaba nasılsın!"}],
    extra_body={
        "thinking_level": "0" 
    },
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content, end="", flush=True)