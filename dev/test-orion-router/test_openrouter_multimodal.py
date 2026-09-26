"""
dev/test-orion-router/test_openrouter_multimodal.py
OpenRouter multimodal dönüşüm, model modalite denetimi,
bozuk anahtar ayıklama ve anahtar rotasyonu koruma testleri.
"""
import sys
from pathlib import Path

# Workspace kök dizinini sys.path'e en başa ekle
workspace_root = str(Path(__file__).resolve().parent.parent.parent)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

import asyncio
from unittest.mock import AsyncMock, patch

from core.security import decrypt, encrypt
from providers.openrouter.chat import (
    transform_openrouter_messages,
    extract_required_modalities,
    validate_model_modalities,
    _MODEL_CATALOG_CACHE,
)
from core.router.runners.chat import is_key_specific_error, ChatRunner


def test_mixed_attachments_transformation_and_order():
    """Karışık ek sırası, input_video -> video_url dönüşümü ve mevcut eklerin korunması."""
    input_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Başlangıç metni"},
                {
                    "type": "input_video",
                    "input_video": {
                        "data": "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZn==",
                        "format": "mp4",
                    },
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="},
                },
                {
                    "type": "input_image",
                    "input_image": {
                        "data": "iVBORw0KGgoAAAANSUhEUg==",
                        "format": "png",
                    },
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "https://example.com/preexisting.mp4"},
                },
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "UklGRiT5BgBXQVZFZm10IBAAAA==",
                        "format": "wav",
                    },
                },
                {"type": "text", "text": "Bitiş metni"},
            ],
        }
    ]

    transformed = transform_openrouter_messages(input_messages)
    content = transformed[0]["content"]

    # Sıra tam olarak 7 parça olmalı
    assert len(content) == 7

    # 1. Parça text
    assert content[0] == {"type": "text", "text": "Başlangıç metni"}

    # 2. Parça input_video -> video_url olmalı
    assert content[1]["type"] == "video_url"
    assert content[1]["video_url"]["url"].startswith("data:video/mp4;base64,AAAAIGZ0eXBpc29t")

    # 3. Parça var olan image_url bozulmadan kalmalı
    assert content[2] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="},
    }

    # 4. Parça input_image -> image_url olmalı
    assert content[3]["type"] == "image_url"
    assert content[3]["image_url"]["url"].startswith("data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==")

    # 5. Parça var olan video_url bozulmadan kalmalı
    assert content[4] == {
        "type": "video_url",
        "video_url": {"url": "https://example.com/preexisting.mp4"},
    }

    # 6. Parça input_audio bozulmadan kalmalı
    assert content[5]["type"] == "input_audio"
    assert content[5]["input_audio"]["format"] == "wav"

    # 7. Parça bitiş metni
    assert content[6] == {"type": "text", "text": "Bitiş metni"}


def test_mime_type_mappings_for_video():
    """Farklı video uzantılarının doğru MIME tiplerine çevrilmesi."""
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "input_video", "input_video": {"data": "abc", "format": "mov"}},
                {"type": "input_video", "input_video": {"data": "def", "format": "webm"}},
                {"type": "input_video", "input_video": {"data": "ghi", "format": "avi"}},
            ],
        }
    ]
    transformed = transform_openrouter_messages(msgs)
    parts = transformed[0]["content"]
    assert parts[0]["video_url"]["url"] == "data:video/quicktime;base64,abc"
    assert parts[1]["video_url"]["url"] == "data:video/webm;base64,def"
    assert parts[2]["video_url"]["url"] == "data:video/x-msvideo;base64,ghi"


async def test_validate_model_modalities_rejection_and_acceptance():
    """Desteklenmeyen modalitelerde açık ValueError fırlatılması."""
    fake_catalog = {
        "openai/gpt-oss-120b": {"text"},
        "gpt-oss-120b": {"text"},
        "google/gemma-4-31b-it": {"text", "image", "video"},
        "gemma-4-31b-it": {"text", "image", "video"},
        "google/gemini-2.5-flash": {"text", "image", "video", "audio"},
    }

    with patch("providers.openrouter.chat.fetch_openrouter_model_modalities", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_catalog

        # 1. Metin modeline video/görsel gönderimi engellenmeli
        text_only_request = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Açıkla"},
                    {"type": "input_video", "input_video": {"data": "...", "format": "mp4"}},
                ],
            }
        ]
        caught = False
        try:
            await validate_model_modalities("gpt-oss-120b", text_only_request)
        except ValueError as exc:
            caught = True
            assert "does not support video input" in str(exc)
            assert "['text']" in str(exc)
        assert caught, "gpt-oss-120b should have rejected video input"

        # 2. Gemma 4 video + görseli kabul etmeli
        gemma_valid_request = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Videoyu ve görseli incele"},
                    {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
                ],
            }
        ]
        # Hata vermeden geçmeli
        await validate_model_modalities("google/gemma-4-31b-it", gemma_valid_request)

        # 3. Gemma 4 ses desteklemediği için ses gönderildiğinde açıkça engellenmeli
        gemma_audio_request = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Ses kaydı"},
                    {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}},
                ],
            }
        ]
        caught_audio = False
        try:
            await validate_model_modalities("google/gemma-4-31b-it", gemma_audio_request)
        except ValueError as exc:
            caught_audio = True
            assert "does not support audio input" in str(exc)
        assert caught_audio, "gemma-4-31b-it should have rejected audio input"

        # 4. Gemini 2.5 Flash ses + video + görsel hepsini kabul etmeli
        gemini_all_request = [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": "..."}},
                    {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}},
                    {"type": "image_url", "image_url": {"url": "..."}},
                ],
            }
        ]
        await validate_model_modalities("google/gemini-2.5-flash", gemini_all_request)


def test_security_decrypt_corrupted_key():
    """Çözülemeyen bozuk Fernet anahtarlarının None dönmesi ve sistemin korunması."""
    corrupted_fernet_token = (
        "gAAAAABqMuS_4Fm01GwtZMX-xXkdMPGL6MDACbXsbQENP0GWX0I3mu6k-saPTz1dXtomHsih3bPROTwnIM42Ff73wFIjQkLGw-XRw66CmOJEjxN4_vsqoOGtlDjvC5i9-FHiVqWuRwqNJF9PHjiZJ_b7Lc4WG25FvHPzjeLmnBUUvPOllb2S2LM="
    )
    # Geçersiz/farklı key ile şifrelenmiş token None dönmeli
    assert decrypt(corrupted_fernet_token) is None

    # Düz metin (şifresiz) anahtarlar olduğu gibi dönmeli
    assert decrypt("sk-or-v1-my-key") == "sk-or-v1-my-key"

    # Geçerli şifreli token başarıyla çözülebilmeli
    valid_key = "sk-or-v1-test-valid-12345"
    encrypted = encrypt(valid_key)
    assert decrypt(encrypted) == valid_key


def test_is_key_specific_error_classification():
    """Hata sınıflandırması: model yetersizliği hatalarında anahtar tekrarı yapılmamalı."""
    # Model/modalite ve client hataları -> False (anahtar denenmemeli)
    assert is_key_specific_error("OpenRouter model 'gpt-oss-120b' does not support video input.") is False
    assert is_key_specific_error("No endpoints found that support image input") is False
    assert is_key_specific_error("Audio input modality is not enabled for this model") is False
    assert is_key_specific_error("OpenRouter HTTP Error 404: No endpoints found that support image input") is False
    assert is_key_specific_error("context_length_exceeded: maximum context length is 8192") is False

    # Kimlik doğrulama, kota ve sunucu hataları -> True (başka anahtar veya fallback denenmeli)
    assert is_key_specific_error("Missing Authentication header") is True
    assert is_key_specific_error("OpenRouter HTTP Error 401: Unauthorized") is True
    assert is_key_specific_error("Rate limit exceeded (code: 429)") is True
    assert is_key_specific_error("Insufficient credits or quota") is True
    assert is_key_specific_error("OpenRouter HTTP Error 503: Service Unavailable") is True


async def test_runner_stops_key_rotation_on_modality_error():
    """Model uyumsuzluğu hatasında ChatRunner'ın diğer anahtarları denemediğini ve asıl hatayı koruduğunu doğrular."""
    from unittest.mock import MagicMock
    from core.router.route_types import RoutePlan, ResolvedRoute

    mock_registry = MagicMock()
    mock_plugin = MagicMock()
    call_count = 0

    async def fake_stream_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise ValueError("OpenRouter model 'gpt-oss-120b' does not support video input.")
        yield ""

    mock_plugin.stream_chat = fake_stream_chat
    mock_registry.chat_providers = {"openrouter": mock_plugin}

    mock_resolver = AsyncMock()
    route_plan = RoutePlan(
        requested_provider="openrouter",
        routes=(ResolvedRoute(provider="openrouter", model="gpt-oss-120b"),),
    )
    mock_resolver.resolve.return_value = route_plan

    mock_key_pool = AsyncMock()
    mock_key_pool.get_keys_for_provider.return_value = [
        ("key_valid_1", "id_1"),
        ("key_corrupt_2", "id_2"),
    ]

    mock_telemetry = AsyncMock()
    mock_telemetry.create_processing_log.return_value = 123

    runner = ChatRunner(
        registry=mock_registry,
        route_resolver=mock_resolver,
        key_pool=mock_key_pool,
        telemetry=mock_telemetry,
    )

    chunks = []
    async for chunk in runner.run_combo(
        provider="openrouter",
        model="gpt-oss-120b",
        messages=[{"role": "user", "content": "test"}],
    ):
        chunks.append(chunk)

    # 1. stream_chat sadece 1 kere çağrılmalı (ikinci anahtar denenmemeli!)
    assert call_count == 1, f"Expected 1 call, got {call_count}"

    # 2. Keypool'a mark_key_error çağrılmamalı (çünkü anahtar değil model hatalı)
    mock_key_pool.mark_key_error.assert_not_called()

    # 3. Kullanıcıya dönen hata 401 değil, asıl model hatası olmalı
    all_text = "".join(chunks)
    assert "OpenRouter model 'gpt-oss-120b' does not support video input." in all_text


if __name__ == "__main__":
    print("Testing mixed attachments transformation...")
    test_mixed_attachments_transformation_and_order()
    print("  [PASS] Mixed attachments transformation and ordering")

    print("Testing MIME type mappings...")
    test_mime_type_mappings_for_video()
    print("  [PASS] MIME type mappings")

    print("Testing validate_model_modalities...")
    asyncio.run(test_validate_model_modalities_rejection_and_acceptance())
    print("  [PASS] Model modality validation and rejections")

    print("Testing security decrypt corrupted key...")
    test_security_decrypt_corrupted_key()
    print("  [PASS] Decrypt handles corrupted key safely")

    print("Testing is_key_specific_error classification...")
    test_is_key_specific_error_classification()
    print("  [PASS] Error classification preserves model errors and stops rotation")

    print("Testing runner stops key rotation on modality error...")
    asyncio.run(test_runner_stops_key_rotation_on_modality_error())
    print("  [PASS] Runner halted key retry loop and preserved true error")

    print("\nALL OPENROUTER MULTIMODAL TESTS PASSED!")
