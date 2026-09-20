"""
dev/test-orion-router/test_thinking.py
---------------------------------------
Orion Router Thinking / Reasoning mimarisi için kapsamlı birim ve entegrasyon testleri.
- ThinkingConfig girdi normalizasyonu
- Local, Gemini, OpenAI ve OpenRouter sağlayıcı adaptörlerinin doğrulanması
- Canlı yerel llama.cpp / local model üzerinde düşünmenin ("0" ve "off") kapandığının testi
"""
import os
import sys
import json
import urllib.request

# Repo kök dizinini sys.path'e ekle
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.thinking import ThinkingConfig
from providers.local.chat import LocalChatProvider
from providers.gemini.chat import GeminiChatProvider
from providers.openai.chat import OpenAIChatProvider
from providers.openrouter.chat import OpenRouterChatProvider


def test_thinking_config_normalization():
    print("\n--- 1. Testing ThinkingConfig Normalization ---")
    
    # Kapatma (Disabled) testleri - standart ve net değerler
    for off_val in ["off", "OFF", "0", 0, "false", "False", False, "none", "NONE"]:
        cfg = ThinkingConfig.from_value(off_val)
        assert cfg.is_disabled, f"Failed: {off_val} should be disabled"
        assert not cfg.is_active, f"Failed: {off_val} should not be active"
        assert not cfg.is_unspecified, f"Failed: {off_val} should not be unspecified"
        assert cfg.budget == 0, f"Failed: {off_val} budget should be 0"
    print("  [PASS] Standard disabled inputs ('off', '0', 0, 'none', 'false', False) correctly detected as is_disabled=True, budget=0.")

    # Sayısal bütçe testleri
    for b_val in ["1024", 1024, "4096", 4096]:
        cfg = ThinkingConfig.from_value(b_val)
        assert not cfg.is_disabled, f"Failed: {b_val} should not be disabled"
        assert cfg.is_active, f"Failed: {b_val} should be active"
        assert cfg.budget == int(b_val), f"Failed: {b_val} budget mismatch"
    print("  [PASS] Numeric budgets ('1024', 1024, '4096') correctly detected as active with integer budget.")

    # String seviye testleri - dönüştürülmeden doğrudan geçirilir (pass-through)
    for lvl in ["minimal", "low", "medium", "high", "xhigh"]:
        cfg = ThinkingConfig.from_value(lvl)
        assert not cfg.is_disabled, f"Failed: {lvl} should not be disabled"
        assert cfg.is_active, f"Failed: {lvl} should be active"
        assert cfg.level == lvl.lower(), f"Failed: {lvl} level mismatch"
    print("  [PASS] Levels ('low', 'medium', 'high', 'minimal', 'xhigh') directly preserved without artificial alias mapping.")

    # Boş / Tanımsız testleri
    for none_val in [None, "", "   "]:
        cfg = ThinkingConfig.from_value(none_val)
        assert cfg.is_unspecified, f"Failed: {none_val} should be unspecified"
        assert not cfg.is_disabled, f"Failed: {none_val} should not be disabled"
        assert not cfg.is_active, f"Failed: {none_val} should not be active"
    print("  [PASS] Unspecified inputs (None, '') correctly detected as is_unspecified=True.")


def test_local_chat_provider():
    print("\n--- 2. Testing LocalChatProvider apply_thinking ---")
    provider = LocalChatProvider()

    # Case A: "off"
    payload_off = {"model": "local-model"}
    cfg_off = provider.extract_thinking_config({"thinking_level": "off"})
    provider.apply_thinking(payload_off, cfg_off)
    assert payload_off.get("chat_template_kwargs", {}).get("enable_thinking") is False
    assert payload_off.get("thinking_budget_tokens") == 0
    assert payload_off.get("reasoning_effort") == "none"
    print("  [PASS] Local provider with thinking_level='off' sets enable_thinking=False, thinking_budget_tokens=0, reasoning_effort='none'")

    # Case B: "0"
    payload_zero = {"model": "local-model"}
    cfg_zero = provider.extract_thinking_config({"thinking_level": "0"})
    provider.apply_thinking(payload_zero, cfg_zero)
    assert payload_zero.get("chat_template_kwargs", {}).get("enable_thinking") is False
    assert payload_zero.get("thinking_budget_tokens") == 0
    print("  [PASS] Local provider with thinking_level='0' sets enable_thinking=False, thinking_budget_tokens=0")

    # Case C: "low"
    payload_low = {"model": "local-model"}
    cfg_low = provider.extract_thinking_config({"thinking_level": "low"})
    provider.apply_thinking(payload_low, cfg_low)
    assert payload_low.get("chat_template_kwargs", {}).get("enable_thinking") is True
    assert payload_low.get("reasoning_effort") == "low"
    print("  [PASS] Local provider with thinking_level='low' sets enable_thinking=True, reasoning_effort='low'")

    # Case D: "1024"
    payload_budget = {"model": "local-model"}
    cfg_budget = provider.extract_thinking_config({"thinking_level": "1024"})
    provider.apply_thinking(payload_budget, cfg_budget)
    assert payload_budget.get("chat_template_kwargs", {}).get("enable_thinking") is True
    assert payload_budget.get("thinking_budget_tokens") == 1024
    print("  [PASS] Local provider with thinking_level='1024' sets enable_thinking=True, thinking_budget_tokens=1024")

    # Case E: Unspecified (None)
    payload_none = {"model": "local-model"}
    cfg_none = provider.extract_thinking_config({})
    provider.apply_thinking(payload_none, cfg_none)
    assert "chat_template_kwargs" not in payload_none
    assert "thinking_budget_tokens" not in payload_none
    print("  [PASS] Local provider with no thinking param leaves payload untouched (model default)")


def test_gemini_chat_provider():
    print("\n--- 3. Testing GeminiChatProvider apply_thinking ---")
    provider = GeminiChatProvider()

    # Case A: "off"
    cfg_off = provider.extract_thinking_config({"thinking_level": "off"})
    kwargs_off = {}
    provider.apply_thinking(kwargs_off, cfg_off)
    tc_off = kwargs_off.get("thinking_config")
    assert tc_off is not None
    assert tc_off.include_thoughts is False
    assert tc_off.thinking_budget == 0
    print("  [PASS] Gemini provider with 'off' sets include_thoughts=False, thinking_budget=0 (clean off, no SDK warning)")

    # Case B: "0"
    cfg_zero = provider.extract_thinking_config({"thinking_level": "0"})
    kwargs_zero = {}
    provider.apply_thinking(kwargs_zero, cfg_zero)
    tc_zero = kwargs_zero.get("thinking_config")
    assert tc_zero is not None
    assert tc_zero.include_thoughts is False
    assert tc_zero.thinking_budget == 0
    print("  [PASS] Gemini provider with '0' sets include_thoughts=False, thinking_budget=0")

    # Case C: "low"
    cfg_low = provider.extract_thinking_config({"thinking_level": "low"})
    kwargs_low = {}
    provider.apply_thinking(kwargs_low, cfg_low)
    tc_low = kwargs_low.get("thinking_config")
    assert tc_low is not None
    assert tc_low.include_thoughts is True
    assert str(tc_low.thinking_level).upper() in ("LOW", "THINKINGLEVEL.LOW")
    print("  [PASS] Gemini provider with 'low' sets include_thoughts=True, thinking_level='low'")

    # Case D: "1024"
    cfg_budget = provider.extract_thinking_config({"thinking_level": "1024"})
    kwargs_budget = {}
    provider.apply_thinking(kwargs_budget, cfg_budget)
    tc_budget = kwargs_budget.get("thinking_config")
    assert tc_budget is not None
    assert tc_budget.include_thoughts is True
    assert tc_budget.thinking_budget == 1024
    print("  [PASS] Gemini provider with '1024' sets include_thoughts=True, thinking_budget=1024")

    # Case E: "xhigh" doğrudan string olarak Gemini thinking_config'e aktarılır (müdahale/dönüştürme yapılmaz)
    cfg_xhigh = provider.extract_thinking_config({"thinking_level": "xhigh"})
    kwargs_xhigh = {}
    provider.apply_thinking(kwargs_xhigh, cfg_xhigh)
    tc_xhigh = kwargs_xhigh.get("thinking_config")
    assert tc_xhigh is not None
    assert str(tc_xhigh.thinking_level).lower().endswith("xhigh")
    print("  [PASS] Gemini provider passes 'xhigh' directly to SDK without modifying user intent")


def test_openai_and_openrouter_providers():
    print("\n--- 4. Testing OpenAI and OpenRouter Providers apply_thinking ---")
    openai_prov = OpenAIChatProvider()
    openrouter_prov = OpenRouterChatProvider()

    # OpenAI off -> omits reasoning_effort
    payload_oai_off = {}
    openai_prov.apply_thinking(payload_oai_off, openai_prov.extract_thinking_config({"thinking_level": "off"}))
    assert "reasoning_effort" not in payload_oai_off
    print("  [PASS] OpenAI provider omits reasoning_effort when thinking is 'off'")

    # OpenAI low -> reasoning_effort="low"
    payload_oai_low = {}
    openai_prov.apply_thinking(payload_oai_low, openai_prov.extract_thinking_config({"thinking_level": "low"}))
    assert payload_oai_low.get("reasoning_effort") == "low"
    print("  [PASS] OpenAI provider sets reasoning_effort='low'")

    # OpenRouter off -> include_reasoning=False, enable_thinking=False, max_tokens=0
    payload_or_off = {}
    openrouter_prov.apply_thinking(payload_or_off, openrouter_prov.extract_thinking_config({"thinking_level": "off"}))
    assert payload_or_off.get("include_reasoning") is False
    assert payload_or_off.get("chat_template_kwargs", {}).get("enable_thinking") is False
    assert payload_or_off.get("reasoning", {}).get("max_tokens") == 0
    print("  [PASS] OpenRouter provider disables include_reasoning and sets enable_thinking=False, max_tokens=0")

    # OpenRouter xhigh -> Doğrudan 'xhigh' geçer (OpenRouter yerel olarak xhigh destekler)
    payload_or_xhigh = {}
    openrouter_prov.apply_thinking(payload_or_xhigh, openrouter_prov.extract_thinking_config({"thinking_level": "xhigh"}))
    assert payload_or_xhigh.get("include_reasoning") is True
    assert payload_or_xhigh.get("reasoning_effort") == "xhigh"
    assert payload_or_xhigh.get("reasoning", {}).get("effort") == "xhigh"
    print("  [PASS] OpenRouter provider passes 'xhigh' directly through as native effort='xhigh'")


def test_live_local_llama_cpp():
    print(f"\n--- 5. Testing Live Local Model Endpoint (port {LLM_PORT}) ---")
    active_port = None
    try:
        req = urllib.request.Request(f"http://{LLM_HOST}:{LLM_PORT}/v1/models")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                active_port = LLM_PORT
    except Exception:
        pass

    if not active_port:
        print(f"  [SKIP] No local llama-cpp runner active on {LLM_PORT}.")
        return

    print(f"  [INFO] Found active local llama-cpp server on port {active_port}")

    prov = LocalChatProvider()
    url = f"http://127.0.0.1:{active_port}/v1/chat/completions"

    for test_val in ["off", "0"]:
        payload = {
            "model": "local-model",
            "messages": [{"role": "user", "content": "Calculate 5*5 and reply with only the number."}],
            "stream": True,
        }
        cfg = prov.extract_thinking_config({"thinking_level": test_val})
        prov.apply_thinking(payload, cfg)

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        received_reasoning = ""
        received_content = ""
        with urllib.request.urlopen(req, timeout=10) as resp:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: ") and line_str != "data: [DONE]":
                    try:
                        data = json.loads(line_str[6:])
                        delta = data["choices"][0].get("delta", {})
                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            received_reasoning += delta["reasoning_content"]
                        if "content" in delta and delta["content"]:
                            received_content += delta["content"]
                    except Exception:
                        pass

        print(f"  [RESULT for '{test_val}'] Content: '{received_content.strip()}', Reasoning chars: {len(received_reasoning)}")
        assert len(received_reasoning) == 0, f"Error: Local model emitted reasoning when thinking_level='{test_val}'! Reasoning was: {received_reasoning}"
        print(f"  [PASS] Live local model verified: ZERO reasoning tokens emitted when thinking_level='{test_val}'!")


if __name__ == "__main__":
    print("==================================================")
    print("   Orion Router Thinking System Test Suite        ")
    print("==================================================")
    try:
        test_thinking_config_normalization()
        test_local_chat_provider()
        test_gemini_chat_provider()
        test_openai_and_openrouter_providers()
        test_live_local_llama_cpp()
        print("\n==================================================")
        print("   ALL TESTS PASSED SUCCESSFULLY (100% OK)        ")
        print("==================================================")
    except AssertionError as e:
        print(f"\n[TEST FAILED]: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR]: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
