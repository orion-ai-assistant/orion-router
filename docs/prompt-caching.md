# Prompt caching

A provider can reuse the work it already did for the start of a prompt. A chat that resends its
history therefore pays the cheap *cached input* rate for everything it sent before and the normal
rate only for what is new. Orion supports it end to end: requests keep the prompt prefix stable and
name the conversation, the Router reads the cache hits the provider reports, bills them at the
cached rate and shows the savings on the dashboard.

## What each provider needs

| Provider | Cache | What the Router does |
| --- | --- | --- |
| Gemini 2.5+ | automatic (implicit), no guarantee | nothing to send; reads `cached_content_token_count` |
| DeepSeek | automatic (disk), best effort | nothing to send; reads `prompt_cache_hit_tokens` |
| OpenAI | automatic, prompts of 1024+ tokens | sends `prompt_cache_key`; reads `cached_tokens` |
| OpenRouter | provider dependent | sends `session_id` (sticky routing) and, for `anthropic/*`, a top-level `cache_control`; reads `cached_tokens` and `cache_write_tokens` |
| Local | llama.cpp keeps its own KV cache | nothing |

A prompt is only cached while its **start stays byte-identical** between requests, so the Hub keeps the
system prompt and the older history unchanged (its history window slides in blocks of turns, not every turn;
see `HISTORY_SLIDE_TURNS`) and sorts tool definitions. Caches live minutes, so a chat that pauses
for a long time starts cold again.

## Naming a conversation

A client names the conversation with `prompt_cache_key` or `session_id` in the body, or the
`x-orion-session` / `x-session-id` header. The Router hashes it together with the caller's virtual
key id (chat ids never reach providers, and two callers cannot share a cache) and hands every
provider the same opaque key as the `cache_key` keyword. The key is only a routing hint: a provider
matches its cache on the start of the prompt, not on the chat. The Hub sends the user id, because all of a
user's chats begin with the same system prompt and tool definitions (about a thousand tokens), so a new chat can
already hit the cache of the previous one.

## Pricing

Prices are USD per 1M tokens: `cache_read` for cache hits and `cache_write` for tokens written into a
cache (some providers charge more than `input` for that). Both are optional; unset means "bill like
`input`", which is the cost before this feature. Set them in `providers/*/models.json`, or per model
in the dashboard's Models page / `POST|PUT /api/models` (`cache_read_price`, `cache_write_price`).

```
prompt cost = fresh tokens x input + cached tokens x cache_read + written tokens x cache_write
saving      = every prompt token at input - prompt cost
```

Request logs store `cached_tokens`, `cache_write_tokens` and `cache_saved_cost`; `/api/stats`,
`/api/usage` and `/api/logs` expose them, and the dashboard overview shows the savings.
Clients also get the OpenAI-shaped `usage.prompt_tokens_details.cached_tokens` in the final chunk.

## Adding a provider

* Request side: override `BaseChat.apply_cache(payload, model, cache)` (providers/base.py) when the
  API wants a hint or marker. The default adds nothing, which is right for automatic caches.
* Response side: yield `{"internal_usage": usage}` with `prompt_tokens` counting **all** prompt
  tokens, cached ones included, and the cached share in `prompt_tokens_details.cached_tokens` (or any
  shape `core/prompt_cache.py::extract_cache_usage` knows). No billing code is needed in the provider:
  `ChatRunner` normalizes the block and `TelemetryService` bills it.
