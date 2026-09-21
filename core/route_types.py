from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedRoute:
    """A concrete provider/model route returned by the model registry."""

    provider: str
    model: str
    temperature: float | None = None
    thinking_level: str | int | None = None
    system_prompt: str | None = None
    default_config: dict[str, Any] | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ResolvedRoute":
        provider = record.get("provider")
        model = record.get("name")
        if not provider or not model:
            raise ValueError("Model route must include both provider and model name.")
        return cls(
            provider=provider,
            model=model,
            temperature=record.get("temperature"),
            thinking_level=record.get("thinking_level"),
            system_prompt=record.get("system_prompt"),
            default_config=record.get("default_config"),
        )


@dataclass(frozen=True)
class RoutePlan:
    """Resolved fallback routes plus the provider selected for initial logging."""

    routes: tuple[ResolvedRoute, ...]
    requested_provider: str | None = None

    @classmethod
    def direct(cls, model: str, provider: str | None) -> "RoutePlan":
        routes = (ResolvedRoute(provider=provider, model=model),) if provider else ()
        return cls(routes=routes, requested_provider=provider)

    @property
    def primary_provider(self) -> str | None:
        return self.routes[0].provider if self.routes else self.requested_provider
