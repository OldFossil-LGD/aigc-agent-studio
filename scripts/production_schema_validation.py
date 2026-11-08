"""Small, single-purpose validator for production compiler artifacts.

Call sites:
- scripts/compile_production.py validates the contract result, shot graph and
  every prompt package before writing artifacts (compile entry boundary).
- Tests in tests/test_production_semantics.py exercise these validators.

This module intentionally delegates to the installed jsonschema package instead
of reimplementing JSON Schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - dependency is required by task
    raise RuntimeError("jsonschema is required for production schema validation") from exc


_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    with (_SCHEMA_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_contract_result(payload: Any) -> None:
    jsonschema.validate(payload, _load_schema("production_contract.schema.json"))


def validate_shot_graph(payload: Any) -> None:
    jsonschema.validate(payload, _load_schema("shot_graph_plan.schema.json"))


def validate_prompt_package(payload: Any) -> None:
    jsonschema.validate(payload, _load_schema("prompt_package.schema.json"))


__all__ = ["validate_contract_result", "validate_shot_graph", "validate_prompt_package"]