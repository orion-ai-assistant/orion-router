import openai

client = openai.OpenAI(
    base_url="http://localhost:20128/v1",
    api_key="sk-orion-yw-4dcSmGgitl2H6lTFaUdAZqlIzK3IEEmNNDhzqbtE"
)

response = client.chat.completions.create(
    model="gemini-2.5-flash", 
    messages=[{"role": "user", "content": "Merhaba nasılsın!"}],
    temperature=0.7,
    extra_body={
        "thinking_level": "0" 
    },
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content, end="", flush=True)