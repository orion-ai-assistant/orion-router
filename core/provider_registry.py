import importlib
import inspect
import logging
import pathlib

import providers
from providers.base import BaseChat, BaseEmbed, BaseFileUpload, BaseSTT, BaseTTS

logger = logging.getLogger("service-router.dynamic")

ALLOWED_CAPABILITIES: list[str] = [
    "chat",
    "embeddings",
    "tts",
    "stt",
    "files",
    "image",
    "audio",
    "video",
]


class ProviderRegistry:
    """Discovers provider capability implementations under providers/."""

    def __init__(self) -> None:
        self.chat_providers: dict[str, BaseChat] = {}
        self.embed_providers: dict[str, BaseEmbed] = {}
        self.tts_providers: dict[str, BaseTTS] = {}
        self.stt_providers: dict[str, BaseSTT] = {}
        self.file_providers: dict[str, BaseFileUpload] = {}
        self.load()

    def load(self) -> None:
        base_classes = (BaseChat, BaseEmbed, BaseTTS, BaseSTT, BaseFileUpload)
        providers_path = pathlib.Path(providers.__path__[0])

        for provider_dir in providers_path.iterdir():
            if not provider_dir.is_dir() or provider_dir.name == "__pycache__":
                continue

            name = provider_dir.name
            modules_to_scan = []
            try:
                modules_to_scan.append(importlib.import_module(f"providers.{name}"))
            except ImportError:
                pass
            except Exception as exc:
                logger.error("Failed to import provider package 'providers.%s': %s", name, exc)

            for cap in ALLOWED_CAPABILITIES:
                if not (provider_dir / f"{cap}.py").exists():
                    continue
                try:
                    modules_to_scan.append(importlib.import_module(f"providers.{name}.{cap}"))
                except Exception as exc:
                    logger.error(
                        "Failed to import submodule 'providers.%s.%s': %s",
                        name,
                        cap,
                        exc,
                    )

            seen_classes: set[type] = set()
            for mod in modules_to_scan:
                for _, obj in inspect.getmembers(mod, inspect.isclass):
                    if obj in seen_classes:
                        continue
                    if not any(issubclass(obj, base) for base in base_classes):
                        continue
                    seen_classes.add(obj)
                    self._register(obj, name)

    def _register(self, obj: type, default_name: str) -> None:
        pname = getattr(obj, "provider_name", None) or default_name
        if not pname:
            return

        if issubclass(obj, BaseChat) and obj is not BaseChat and pname not in self.chat_providers:
            self.chat_providers[pname] = obj()
            logger.info("Loaded chat provider: %s (%s)", pname, obj.__name__)

        if issubclass(obj, BaseEmbed) and obj is not BaseEmbed and pname not in self.embed_providers:
            self.embed_providers[pname] = obj()
            logger.info("Loaded embed provider: %s (%s)", pname, obj.__name__)

        if issubclass(obj, BaseTTS) and obj is not BaseTTS and pname not in self.tts_providers:
            self.tts_providers[pname] = obj()
            logger.info("Loaded TTS provider: %s (%s)", pname, obj.__name__)

        if issubclass(obj, BaseSTT) and obj is not BaseSTT and pname not in self.stt_providers:
            self.stt_providers[pname] = obj()
            logger.info("Loaded STT provider: %s (%s)", pname, obj.__name__)

        if (
            issubclass(obj, BaseFileUpload)
            and obj is not BaseFileUpload
            and pname not in self.file_providers
        ):
            self.file_providers[pname] = obj()
            logger.info("Loaded file provider: %s (%s)", pname, obj.__name__)

    def get_capabilities(self) -> dict:
        all_providers = (
            set(self.chat_providers)
            | set(self.embed_providers)
            | set(self.tts_providers)
            | set(self.stt_providers)
            | set(self.file_providers)
        )
        return {
            provider: {
                "chat": provider in self.chat_providers,
                "embed": provider in self.embed_providers,
                "tts": provider in self.tts_providers,
                "stt": provider in self.stt_providers,
                "file_upload": provider in self.file_providers,
            }
            for provider in sorted(all_providers)
        }
