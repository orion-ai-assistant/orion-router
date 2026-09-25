"""Bundled model definitions used to seed the database and resolve defaults."""

import json
import math
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any


MODEL_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "models.json"


@lru_cache(maxsize=1)
def load_model_catalog() -> dict[str, Any]:
    catalog = json.loads(MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    if catalog.get("pricing_unit") != "per_million_tokens":
        raise ValueError("models.json pricing_unit must be per_million_tokens")
    models = catalog.get("models")
    if not isinstance(models, list):
        raise ValueError("models.json must contain a models list")
    names = [model.get("name") for model in models]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise ValueError("models.json model names must be nonempty and unique")
    for model in models:
        if model.get("seed", True) and (not model.get("provider") or not model.get("capability")):
            raise ValueError(f"Seed model {model['name']} needs provider and capability")
        unit = model.get("pricing_unit", catalog["pricing_unit"])
        if unit not in ("per_million_tokens", "per_million_characters"):
            raise ValueError(f"Unsupported pricing unit for {model['name']}: {unit}")
        if unit == "per_million_characters" and model.get("capability") != "tts":
            raise ValueError("Character pricing is only supported for TTS models")
        pricing = model.get("pricing")
        if pricing is not None:
            if not isinstance(pricing, dict) or any(
                key not in ("input", "output", "think") or
                (value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0))
                for key, value in pricing.items()
            ):
                raise ValueError(f"Invalid pricing for {model['name']}")
    return catalog


def bundled_model(provider: str, capability: str) -> dict[str, Any]:
    for model in load_model_catalog()["models"]:
        if model.get("seed", True) and model.get("provider") == provider and model.get("capability") == capability:
            return model
    raise ValueError(f"No bundled {provider}/{capability} model in models.json")


def unit_pricing(model: dict[str, Any]) -> dict[str, float | None] | None:
    """Return catalog rates per million tokens/characters as-is for DB storage.

    Prices in models.json are written per 1 million tokens (or characters for TTS).
    They are stored in the DB at that scale; telemetry divides by 1_000_000 when
    computing actual cost so that 200 tokens × (0.15 / 1_000_000) = $0.00000003.
    """
    pricing = model.get("pricing")
    if pricing is None:
        return None
    unit = model.get("pricing_unit", "per_million_tokens")
    if unit not in ("per_million_tokens", "per_million_characters"):
        raise ValueError(f"Unsupported pricing unit: {unit}")
    return {
        key: None if pricing.get(key) is None else float(Decimal(str(pricing[key])))
        for key in ("input", "output", "think")
    }
