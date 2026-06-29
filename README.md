# Orion Custom Service Router — AI Gateway

**English** | [Türkçe](README.tr.md) | [中文](README.zh-CN.md)

Orion project's **AI Gateway (Router)** layer. It centrally collects, authorizes, and dynamically routes all AI requests (LLM, Embedding, TTS, File Upload) from clients and workers to the relevant providers (OpenAI, OpenRouter, Gemini, Local).

To install and start using Orion Router on your system, please visit our website. *(Note: Our website offers documentation in multiple languages!)*

👉 **[Website (Documentation & Installation)](https://orion-ai-assistant.github.io/orion-router/)** 👈

---

## 🤔 What is this project and its purpose?

Orion Router allows you to build **your own personal "OpenAI" gateway** for your AI-powered applications and teams.

* **Single API, All Models:** Connect your applications only to Orion Router. In the background, you can use OpenAI, Anthropic, Gemini, OpenRouter, or your own local server models. You can switch providers without changing your code or instantly fallback from crashed APIs.
* **Security and Privacy:** Your actual API keys (Upstream Keys) remain secure on your server. You only provide **Virtual Keys** that you define to your clients and teammates.
* **Cost Management:** You can track how much each user or project spends and set budget limits.
* **Built-in Dashboard:** It comes with a modern interface where you can track requests, costs, logs, and test models.

## 💡 How to Use?

Orion Router is designed to work **fully compatible with the OpenAI API**. In any OpenAI library (Python, Node.js, LangChain, etc.), you can instantly integrate Orion into your system by simply changing the `base_url` and `api_key`!

**Example Python (OpenAI SDK) Usage:**

```python
import openai

# Routing the OpenAI client to Orion Router
client = openai.OpenAI(
    base_url="http://127.0.0.1:20128/v1", # Your Orion Router server address
    api_key="your-orion-virtual-key"      # The virtual key you generated via Dashboard
)

response = client.chat.completions.create(
    model="gemini-3.1-flash-lite", 
    messages=[{"role": "user", "content": "Hello Orion!"}],
    temperature=0.7, 
    tools=[], 
    extra_body={
        "thinking_level": "high" # e.g. "low" | 1024
    }
)

print(response.choices[0].message.content)
```

> **🧠 Advanced Parameter Translation:** Orion Router universally supports features like `temperature`, `tools` (Function Calling), and `thinking_level` (Thinking Budget). You just send the request in standard format, and Orion Router automatically adapts these parameters in the background to the correct structure understood by the target provider (e.g., *reasoning_effort*, *thinking_budget*)!

## ✨ Key Features

* **Dynamic Routing:** Automatic fallback to backup providers for crashed APIs.
* **Budget and Limit Control:** Restricting expenses by assigning custom virtual keys to clients.
* **Privacy Focused:** Never leaks your actual API keys (Upstream Keys).
* **Extensible Architecture:** Ability to integrate a new AI provider into the system by adding a single Python file.
* **Built-in Dashboard:** A modern interface offering a built-in testing area (Playground) and tracking of requests, costs, and logs.

---

## 🛠 For Developers

A basic guide for developers who want to customize the system or add new features.

### CLI Tools (`orion.py`)

You can use the `orion.py` file in the root directory to manage the development process:

* `python orion.py dev` : Starts the hot-reload active development environment (PostgreSQL: 5444, API: 20129, UI: 3001).
* `python orion.py prod` : Builds the production version and runs it on a single port.
* `python orion.py stop` : Cleans up all background hanging ports and services.

### 🔌 Adding a New Provider

`dynamic_router.py` automatically scans and loads folders under `providers/`.

**Capability File Mappings:**
You just need to create the file for the capability you want to support under the `providers/<provider_name>/` folder:
* `chat.py` ➔ Chat provider inherited from `BaseChat` class
* `embeddings.py` ➔ Embedding provider inherited from `BaseEmbed` class
* `tts.py` ➔ Text-to-Speech provider inherited from `BaseTTS` class
* `files.py` ➔ File Upload provider inherited from `BaseFileUpload` class

**Example: Anthropic Integration (Chat)**

1. Create the `providers/anthropic/chat.py` file and inherit from the `BaseChat` class:

```python
import os
from typing import AsyncGenerator, Any
from providers.base import BaseChat

class AnthropicChatProvider(BaseChat):
    provider_name = "anthropic"

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str | None = None,
        auth_header: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        # 1. Get the API Key (auth_header, api_key or env_key fallbacks)
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
            env_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        
        if not resolved_key:
            raise ValueError("Anthropic Error: No API key provided.")
        
        # 2. Make request to target API using HTTPX AsyncClient
        # 3. Yield data in standard format:
        # yield 'data: {"choices":[{"delta":{"content":"..."}}]}\n\n'
        pass

```

When FastAPI/Gateway restarts, the `anthropic` provider and `chat` capability are automatically discovered and ready to use.
