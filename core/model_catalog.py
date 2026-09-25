"""Bundled model definitions used to seed the database and resolve defaults."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


MODEL_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "models.json"


@lru_cache(maxsize=1)
def load_model_catalog() -> dict[str, Any]:
    catalog = json.loads(MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    if catalog.get("pricing_unit") != "per_usage_unit":
        raise ValueError("models.json pricing_unit must be per_usage_unit")
    models = catalog.get("models")
    if not isinstance(models, list):
        raise ValueError("models.json must contain a models list")
    names = [model.get("name") for model in models]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise ValueError("models.json model names must be nonempty and unique")
    for model in models:
        if model.get("seed", True) and (not model.get("provider") or not model.get("capability")):
            raise ValueError(f"Seed model {model['name']} needs provider and capability")
        pricing = model.get("pricing")
        if pricing is not None:
            if not isinstance(pricing, dict) or any(
                key not in ("input", "output", "think") or
                (value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0))
                for key, value in pricing.items()
            ):
                raise ValueError(f"Invalid pricing for {model['name']}")
    return catalog


def bundled_model(provider: str, capability: str) -> dict[str, Any]:
    for model in load_model_catalog()["models"]:
        if model.get("seed", True) and model.get("provider") == provider and model.get("capability") == capability:
            return model
    raise ValueError(f"No bundled {provider}/{capability} model in models.json")
