# Orion Custom Service Router — AI Gateway

**English** | [Türkçe](README.tr.md) | [中文](README.zh-CN.md)

Each native installation advertises its persistent UUID and actual HTTPS API port via `_orion-router-tls._tcp.local.` DNS-SD. Open the local dashboard at `https://localhost:9443/dashboard` (or your configured TLS port); see [Router TLS settings](docs/secure-router-tls.md).

On the Router PC, `http://localhost:20128/dashboard` is a guarded loopback-only
browser entry. Network connections and Hub traffic use pinned HTTPS on 9443.

Router runs independently of Hub on its own port. Clients discover installations by UUID; there is no shared browser alias or Router-owned port-80 entry service.

Secure Hub connections use the HTTPS listener (default port `9443`) and
`_orion-router-tls._tcp.local.` discovery. The local dashboard Settings page shows
the persistent SPKI fingerprint for pairing; see [Router TLS setup](docs/secure-router-tls.md).

Orion project's **AI Gateway (Router)** layer. It centrally collects, authorizes, and dynamically routes all AI requests (LLM, Embedding, TTS, File Upload) from clients and workers to the relevant providers (OpenAI, OpenRouter, Gemini, DeepSeek, Local).

To install and start using Orion Router on your system, please visit our website. *(Note: Our website offers documentation in multiple languages!)*

👉 **[Website (Documentation & Installation)](https://orion-ai-assistant.github.io/orion-router/)** 👈

---

## 🤔 What is this project and its purpose?

Orion Router allows you to build **your own personal "OpenAI" gateway** for your AI-powered applications and teams.

* **Single API, All Models:** Connect your applications only to Orion Router. In the background, you can use OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter, or your own local server models. You can switch providers without changing your code or instantly fallback from crashed APIs.
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
    base_url="https://127.0.0.1:9443/v1", # Trust the Router certificate explicitly in your HTTP client
    api_key="your-orion-virtual-key"      # The virtual key you generated via Dashboard
)

response = client.chat.completions.create(
    model="gemini-3.1-flash-lite", 
    messages=[{"role": "user", "content": "Hello Orion!"}],
    temperature=0.7, 
    tools=[], 
    extra_body={
        "thinking": 2048 # Budget: 2048 | -1 (Auto) | 0 (Off) or Level: "high" | "low"
    }
)

print(response.choices[0].message.content)
```

> **🧠 Advanced Parameter Translation & Thinking:** Orion Router universally supports `temperature`, `tools`, and a unified **`thinking`** parameter (`"thinking": 2048` or `"thinking": "high"`). It automatically translates thinking to the upstream provider's native format (`thinking_budget`, `reasoning_effort`, etc.).
> 
> **🛡️ Thinking in Model Groups:** When calling a model group (`model="group-name"`), runtime `thinking` cannot be specified at the request level because models within the group may feature heterogeneous reasoning architectures. Thinking configurations are set per model in the Group settings and applied automatically during fallback execution.
> 
> **⚡ Bypass Router Defaults:** If you want to bypass dashboard-configured model defaults and send raw requests directly to providers, pass `"bypass_defaults": true` in the body or use the `X-Orion-Bypass-Defaults: true` HTTP header. See [API Usage Guide](docs/api-usage.md) for full details and examples.

## ✨ Key Features

* **Dynamic Routing:** Automatic fallback to backup providers for crashed APIs.
* **Budget and Limit Control:** Restricting expenses by assigning custom virtual keys to clients.
* **Privacy Focused:** Never leaks your actual API keys (Upstream Keys).
* **Extensible Architecture:** Ability to integrate a new AI provider into the system by adding a single Python file.
* **Built-in Dashboard:** A modern interface offering a built-in testing area (Playground) and tracking of requests, costs, and logs.

---

## 🛠 For Developers

A basic guide for developers who want to customize the system or add new features.

### CLI Tools (`cli.py`)

You can use the `cli.py` file in the root directory to manage the development process:

* `python cli.py dev` : Starts the hot-reload active development environment (PostgreSQL: `POSTGRES_DEV_PORT`, API: `ROUTER_DEV_PORT`, UI: 3001).
* `python cli.py prod` : Runs production on a single port; rebuilds the dashboard only when its sources change or its output is missing.
* `python cli.py prod --build` (alias: `--force-build`) : Forces a dashboard rebuild before starting.
* `python cli.py stop` : Cleans up all background hanging ports and services.

Local installers and both update paths prepare the dashboard with the same source hash check. Unchanged dashboards skip npm entirely. A failed build preserves the previous output; its new hash is never recorded.

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
