"""
dev/test-orion-router/test_deepseek.py
--------------------------------------
DeepSeek sağlayıcısı için birim ve entegrasyon testleri:
  - ProviderRegistry keşfi ve chat yeteneği
  - Model kataloğu ve fiyatlandırma doğrulaması
  - Thinking Mode (Açık, Kapalı, Seviye eşlemeleri, Bütçe)
  - Modalite denetimleri (deepseek-flash görsel destekler, deepseek-v4-pro reddeder, ses/video reddedilir)
  - Model takma adları (deepseek-chat, deepseek-reasoner, deepseek-v4-flash)
  - SSE akış ayrıştırma (reasoning_content, content, tool_calls, usage)
  - HTTP ve stream hata yönetimi
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.model_catalog import bundled_model, load_model_catalog
from core.router.provider_registry import ProviderRegistry
from core.router.runners.chat import ChatRunner
from core.router.route_types import RoutePlan, ResolvedRoute
from core.router.telemetry import TelemetryService
from core.thinking import ThinkingConfig
from providers.deepseek.chat import (
    DeepSeekChatProvider,
    MODEL_ALIASES,
    transform_deepseek_messages,
    validate_deepseek_modalities,
)


class FakeResponse:
    def __init__(self, status=200, lines=(), error=b""):
        self.status_code = status
        self.lines = lines
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def aread(self):
        return self.error

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.last_request = None

    def stream(self, method, url, json=None, headers=None, timeout=None):
        self.last_request = {"method": method, "url": url, "json": json, "headers": headers}
        return self.response


def test_registry_discovery():
    print("Testing DeepSeek ProviderRegistry discovery...")
    registry = ProviderRegistry()
    assert "deepseek" in registry.chat_providers
    assert isinstance(registry.chat_providers["deepseek"], DeepSeekChatProvider)
    caps = registry.get_capabilities()
    assert caps["deepseek"]["chat"] is True
    assert caps["deepseek"]["embed"] is False
    assert caps["deepseek"]["tts"] is False
    assert caps["deepseek"]["stt"] is False
    print("  [PASS] DeepSeek registered in ProviderRegistry with chat capability")


def test_model_catalog_and_pricing():
    print("Testing DeepSeek models in models.json catalog...")
    catalog = load_model_catalog()
    models = {m["name"]: m for m in catalog["models"]}

    # 1. deepseek-flash
    assert "deepseek-flash" in models
    flash = models["deepseek-flash"]
    assert flash["provider"] == "deepseek"
    assert flash["capability"] == "chat"
    assert flash["pricing"]["input"] == 0.15
    assert flash["pricing"]["output"] == 0.6
    assert flash["pricing"]["think"] == 0.6

    # 2. deepseek-v4-pro
    assert "deepseek-v4-pro" in models
    pro = models["deepseek-v4-pro"]
    assert pro["provider"] == "deepseek"
    assert pro["capability"] == "chat"
    assert pro["pricing"]["input"] == 0.66
    assert pro["pricing"]["output"] == 1.98
    assert pro["pricing"]["think"] == 1.98

    # 3. bundled_model lookup
    bundled = bundled_model("deepseek", "chat")
    assert bundled["name"] == "deepseek-flash"
    print("  [PASS] deepseek-flash and deepseek-v4-pro correctly defined with pricing")


def test_thinking_mode_payloads():
    print("Testing DeepSeek thinking mode payload generation...")
    provider = DeepSeekChatProvider()

    # Disabled
    p_off = {}
    provider.apply_thinking(p_off, ThinkingConfig.from_value("off"))
    assert p_off["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in p_off

    # Level: low
    p_low = {}
    provider.apply_thinking(p_low, ThinkingConfig.from_value("low"))
    assert p_low["thinking"] == {"type": "enabled"}
    assert p_low["reasoning_effort"] == "low"

    # Level: high
    p_high = {}
    provider.apply_thinking(p_high, ThinkingConfig.from_value("high"))
    assert p_high["thinking"] == {"type": "enabled"}
    assert p_high["reasoning_effort"] == "high"

    # Level: minimal -> maps to low
    p_min = {}
    provider.apply_thinking(p_min, ThinkingConfig.from_value("minimal"))
    assert p_min["thinking"] == {"type": "enabled"}
    assert p_min["reasoning_effort"] == "low"

    # Level: xhigh / ultra -> maps to high / max
    p_xhigh = {}
    provider.apply_thinking(p_xhigh, ThinkingConfig.from_value("xhigh"))
    assert p_xhigh["reasoning_effort"] == "high"

    p_ultra = {}
    provider.apply_thinking(p_ultra, ThinkingConfig.from_value("ultra"))
    assert p_ultra["reasoning_effort"] == "max"

    # Budget <= 2048 -> low; > 2048 -> high
    p_b1 = {}
    provider.apply_thinking(p_b1, ThinkingConfig.from_value(1024))
    assert p_b1["reasoning_effort"] == "low"

    p_b2 = {}
    provider.apply_thinking(p_b2, ThinkingConfig.from_value(4096))
    assert p_b2["reasoning_effort"] == "high"

    # Unspecified
    p_unspec = {}
    provider.apply_thinking(p_unspec, ThinkingConfig.from_value(None))
    assert "thinking" not in p_unspec
    assert "reasoning_effort" not in p_unspec
    print("  [PASS] All thinking mode configurations produce correct payload structures")


def test_modality_validation():
    print("Testing DeepSeek modality validations...")
    # deepseek-flash allows images
    validate_deepseek_modalities(
        "deepseek-flash",
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://ex.com/img.jpg"}}]}]
    )

    # deepseek-v4-pro rejects images
    try:
        validate_deepseek_modalities(
            "deepseek-v4-pro",
            [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://ex.com/img.jpg"}}]}]
        )
        assert False, "deepseek-v4-pro should have rejected image input"
    except ValueError as e:
        assert "does not support vision/image input" in str(e)

    # Audio rejected by both
    for m in ("deepseek-flash", "deepseek-v4-pro"):
        try:
            validate_deepseek_modalities(
                m,
                [{"role": "user", "content": [{"type": "input_audio", "audio": {"data": "..."}}]}]
            )
            assert False, f"{m} should have rejected audio input"
        except ValueError as e:
            assert "does not support audio input" in str(e)

    # Video rejected by both
    for m in ("deepseek-flash", "deepseek-v4-pro"):
        try:
            validate_deepseek_modalities(
                m,
                [{"role": "user", "content": [{"type": "input_video", "video": {"data": "..."}}]}]
            )
            assert False, f"{m} should have rejected video input"
        except ValueError as e:
            assert "does not support video input" in str(e)

    print("  [PASS] Modality checks enforce deepseek-flash vision and reject unsupported audio/video")


def test_message_transformation_and_aliases():
    print("Testing message transformations and aliases...")
    # input_image -> image_url
    transformed = transform_deepseek_messages([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe:"},
                {"type": "input_image", "image": {"url": "https://ex.com/test.png"}},
            ],
        }
    ])
    assert transformed[0]["content"][1]["type"] == "image_url"
    assert transformed[0]["content"][1]["image_url"]["url"] == "https://ex.com/test.png"

    # Aliases
    assert MODEL_ALIASES["deepseek-chat"] == "deepseek-flash"
    assert MODEL_ALIASES["deepseek-reasoner"] == "deepseek-flash"
    assert MODEL_ALIASES["deepseek-v4-flash"] == "deepseek-flash"
    print("  [PASS] Message attachments and aliases normalized properly")


async def test_streaming_and_usage():
    print("Testing DeepSeek streaming SSE response parsing and usage metrics...")
    sse_lines = [
        # 1. Delta with reasoning_content
        'data: {"choices":[{"delta":{"reasoning_content":"Let me calculate..."}}]}',
        # 2. Delta with content
        'data: {"choices":[{"delta":{"content":"The answer is 42."}}]}',
        # 3. Delta with tool_calls
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"calc","arguments":"{}"}}]}}]}',
        # 4. Usage chunk
        'data: {"usage":{"prompt_tokens":15,"completion_tokens":25,"completion_tokens_details":{"reasoning_tokens":10}}}',
        'data: [DONE]',
    ]

    fake_resp = FakeResponse(status=200, lines=sse_lines)
    fake_client = FakeClient(fake_resp)

    provider = DeepSeekChatProvider()
    with patch("providers.deepseek.chat.get_http_client", return_value=fake_client):
        chunks = [
            chunk async for chunk in provider.stream_chat(
                model="deepseek-flash",
                messages=[{"role": "user", "content": "What is the answer?"}],
                api_key="sk-deepseek-test-key",
                thinking_level="high",
            )
        ]

    # Check request payload
    req = fake_client.last_request
    assert req["url"] == "https://api.deepseek.com/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer sk-deepseek-test-key"
    assert req["json"]["model"] == "deepseek-flash"
    assert req["json"]["thinking"] == {"type": "enabled"}
    assert req["json"]["reasoning_effort"] == "high"

    # Check streamed items
    assert any("reasoning_content" in c for c in chunks if isinstance(c, str))
    assert any("The answer is 42." in c for c in chunks if isinstance(c, str))
    assert any("call_1" in c for c in chunks if isinstance(c, str))

    # Check usage item
    usage_chunk = next(c for c in chunks if isinstance(c, dict) and "internal_usage" in c)
    internal_usage = usage_chunk["internal_usage"]
    assert internal_usage["prompt_tokens"] == 15
    assert internal_usage["thoughts_tokens"] == 10
    # completion_tokens should be net output (25 - 10 = 15)
    assert internal_usage["completion_tokens"] == 15
    print("  [PASS] Streaming chunks, reasoning_content, tool calls and usage extracted correctly")


async def test_auth_error_and_missing_key():
    print("Testing DeepSeek error handling (missing key and HTTP errors)...")
    provider = DeepSeekChatProvider()

    # Missing API key
    try:
        async for _ in provider.stream_chat("deepseek-flash", [{"role": "user", "content": "hi"}]):
            pass
        assert False, "Should raise ValueError on missing API key"
    except ValueError as e:
        assert "No API key provided" in str(e)

    # HTTP 401 error from API
    fake_resp = FakeResponse(status=401, error=b'{"error":{"message":"Invalid API key"}}')
    fake_client = FakeClient(fake_resp)
    with patch("providers.deepseek.chat.get_http_client", return_value=fake_client):
        try:
            async for _ in provider.stream_chat(
                "deepseek-flash",
                [{"role": "user", "content": "hi"}],
                api_key="bad-key",
            ):
                pass
            assert False, "Should raise RuntimeError on HTTP 401"
        except RuntimeError as e:
            assert "DeepSeek HTTP Error 401" in str(e)
            assert "Invalid API key" in str(e)

    print("  [PASS] Missing key and HTTP error handling validated")


def main():
    print("==================================================")
    print("   Orion Router DeepSeek Provider Test Suite      ")
    print("==================================================")
    test_registry_discovery()
    test_model_catalog_and_pricing()
    test_thinking_mode_payloads()
    test_modality_validation()
    test_message_transformation_and_aliases()
    asyncio.run(test_streaming_and_usage())
    asyncio.run(test_auth_error_and_missing_key())
    print("\nALL DEEPSEEK PROVIDER TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
