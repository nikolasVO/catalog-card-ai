"""Examples are fixtures, not responses from a paid LLM call."""
import json
from pathlib import Path

import pytest

from app.schemas import ProductInput

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def products():
    return [ProductInput.model_validate(obj) for obj in json.loads((ROOT / "examples/products.json").read_text(encoding="utf-8"))]


@pytest.fixture
def example_cards():
    return [json.loads((ROOT / "examples/outputs" / (slug + ".json")).read_text(encoding="utf-8"))
            for slug in ("tachometer", "temperature-monitor")]
