import openai

client = openai.OpenAI(
    base_url="http://localhost:20128/v1",
    api_key="sk-orion-xNOm_Ndcp0xKZqZazJxChwHCsi3DoAAqMRyDpd8H9Pg"
)

response = client.chat.completions.create(
    model="gemini-3.1-flash-lite", 
    messages=[{"role": "user", "content": "Merhaba nasılsın!"}],
    temperature=0.7,
    extra_body={
        "thinking_level": "medium" 
    },
)

for chunk in response:
    print(chunk.choices[0].delta.content, end="", flush=True)