# Orion Custom Service Router — AI Gateway

[English](README.md) | [Türkçe](README.tr.md) | **中文**

Orion 项目的 **AI 网关 (Router)** 层。它将来自客户端和 worker 的所有 AI 请求（LLM、嵌入、TTS、文件上传）集中收集、授权并动态路由到相关的提供商（OpenAI、OpenRouter、Gemini、Local）。

要安装并开始在您的系统上使用 Orion Router，请访问我们的网站。 *(注意：我们的网站提供更多语言的文档！)*

👉 **[官方网站 (安装和使用指南)](https://krstalacam.github.io/orion-router/)** 👈

---

## 🤔 这个项目是什么及其目的是什么？

Orion Router 允许您为基于 AI 的应用程序和团队建立**您个人的“OpenAI”网关**。

* **单一 API，所有模型：** 仅将您的应用程序连接到 Orion Router。在后台，您可以使用 OpenAI、Anthropic、Gemini、OpenRouter 或您自己的本地服务器模型。您可以更改提供商而无需更改代码，或者从崩溃的 API 即时回退到备份 (Fallback)。
* **安全与隐私：** 您的实际 API 密钥 (Upstream Keys) 在您的服务器上保持安全。您仅向客户端和队友提供您定义的**虚拟密钥 (Virtual Keys)**。
* **成本管理：** 您可以跟踪每个用户或项目的支出，并设置预算限制。
* **内置仪表板：** 它提供了一个现代化的界面，您可以在其中跟踪请求、成本、日志并测试模型。

## 💡 如何使用？

Orion Router 旨在**完全兼容 OpenAI API**。在任何 OpenAI 库（Python、Node.js、LangChain 等）中，您只需更改 `base_url` 和 `api_key` 即可立即将 Orion 集成到您的系统中！

**Python (OpenAI SDK) 使用示例：**

```python
import openai

# 将 OpenAI 客户端路由到 Orion Router
client = openai.OpenAI(
    base_url="http://localhost:20128/v1", # 您的 Orion Router 服务器地址
    api_key="your-orion-virtual-key"      # 您通过仪表板生成的虚拟密钥
)

response = client.chat.completions.create(
    model="gemini-3.1-flash-lite", 
    messages=[{"role": "user", "content": "你好 Orion！"}],
    temperature=0.7, 
    tools=[], 
    extra_body={
        "thinking_level": "medium" # 思考能力； "low" - "high" 或 token 预算：1024、8192 等（必须由模型支持）
    }
)

print(response.choices[0].message.content)
```

> **🧠 高级参数转换：** Orion Router 普遍支持诸如 `temperature`、`tools`（函数调用）和 `thinking_level`（思考预算）等功能。您只需以标准格式发送请求，Orion Router 即可在后台自动将这些参数调整为目标提供商（如 *reasoning_effort*、*thinking_budget*）能够理解的正确结构！

## ✨ 主要特点

* **动态路由：** 当 API 崩溃时，自动回退到备份提供商。
* **预算和限制控制：** 通过向客户端分配自定义虚拟密钥来限制支出。
* **注重隐私：** 绝不泄露您的实际 API 密钥 (Upstream Keys)。
* **可扩展架构：** 只需添加一个 Python 文件即可将新的 AI 提供商集成到系统中。
* **内置仪表板：** 提供内置测试区 (Playground) 并跟踪请求、成本和日志的现代界面。

---

## 🛠 面向开发者

面向希望自定义系统或添加新功能的开发者的基本指南。

### CLI 工具 (`orion.py`)

您可以使用根目录中的 `orion.py` 文件来管理开发过程：

* `python orion.py dev` : 启动热重载 (hot-reload) 活跃开发环境（PostgreSQL: 5444，API: 20129，UI: 3001）。
* `python orion.py prod` : 构建生产版本并在单一端口上运行。
* `python orion.py stop` : 清理所有在后台挂起的端口和服务。

### 🔌 添加新的提供商

`dynamic_router.py` 会自动扫描并加载 `providers/` 下的文件夹。

**功能文件映射：**
您只需在 `providers/<provider_name>/` 文件夹下为您想要支持的功能创建文件：
* `chat.py` ➔ 继承自 `BaseChat` 类的 Chat 提供商
* `embeddings.py` ➔ 继承自 `BaseEmbed` 类的 Embedding 提供商
* `tts.py` ➔ 继承自 `BaseTTS` 类的 Text-to-Speech 提供商
* `files.py` ➔ 继承自 `BaseFileUpload` 类的 File Upload 提供商

**示例：Anthropic 集成 (Chat)**

1. 创建 `providers/anthropic/chat.py` 文件并继承 `BaseChat` 类：

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
        # 1. 获取 API 密钥 (auth_header, api_key 或 env_key fallbacks)
        resolved_key = self._resolve_api_key(
            auth_header=auth_header,
            api_key=api_key,
            env_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        
        if not resolved_key:
            raise ValueError("Anthropic Error: No API key provided.")
        
        # 2. 使用 HTTPX AsyncClient 向目标 API 发送请求
        # 3. 以标准格式 yield 数据:
        # yield 'data: {"choices":[{"delta":{"content":"..."}}]}\n\n'
        pass

```

当 FastAPI/Gateway 重新启动时，`anthropic` 提供商和 `chat` 功能将被自动发现并可以使用。
