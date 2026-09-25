# Model catalog pricing

`data/models.json` stores USD prices per **one million tokens** by default:

```json
{"name": "example-chat", "provider": "example", "capability": "chat", "pricing": {"input": 0.15, "output": 0.6, "think": 0.6}}
```

Character-billed TTS models override the unit on the model:

```json
{"name": "tts-1", "provider": "openai", "capability": "tts", "pricing_unit": "per_million_characters", "pricing": {"input": 15, "output": 0, "think": 0}}
```

Catalog and database store USD rates per **1,000,000 tokens / characters**. The
admin API and dashboard also display and accept prices per 1M units. Telemetry and
transcription cost calculation scales usage by dividing tokens / characters by 1,000,000
before multiplying by these rates.

- Chat: input, final output and thinking tokens are counted separately.
- Embeddings: input tokens are billable; vector dimensions are not output tokens.
- Token-billed TTS: provider-reported input/output token counts are used.
- Character-billed `tts-1`: input character count is used.
- STT: provider-reported token usage takes precedence over the existing fallback
  estimates. Without provider usage, counts remain estimates, not exact billing.

Missing prices remain unknown; explicit zero means free. Existing catalog prices
were rescaled without changing their monetary value or refreshing provider rates.

Only `per_million_tokens` and `per_million_characters` are currently supported.
Time-based prices require a duration billing implementation before adding them;
unsupported units are rejected rather than silently treated as token prices.
