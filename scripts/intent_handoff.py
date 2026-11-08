"""Intent handoff (intent-handoff/v1) — the Agent-authored structured intent contract.

**Why this file exists.** Natural-language creative understanding belongs to the
Agent, not to a regex engine. A script that tries to guess "5 秒 / 9:16 / 剪纸"
out of free prose is pretending to understand; when it guesses wrong it
silently produces a *different* film (120 秒 / 16:9 / 写实 / full_film).

So the division of labour is:

* **Agent** — reads the user's prose, writes one `intent-handoff/v1` document.
  Every decision carries `source` (`user_explicit` / `agent_proposed` /
  `default`) and `locked`.
* **this module / the compiler** — validates that handoff, keeps explicit user
  values verbatim, marks anything it had to supply as *proposed* (never as
  locked), and converts it into the compiler input dict.

The user never has to write JSON; the Agent writes this file for them.

Rejected on purpose:
* extracting decisions from free prose by keyword (see `compile_text_input.py`);
* silently replacing an explicit user value with a library default.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


FORMAT = "intent-handoff/v1"

# Decisions that materially shape the delivered artefact. If one of them is
# not locked, the contract must stay DRAFT (see `compile_production_contract.py`).
MATERIAL_DECISIONS = ("duration_sec", "aspect_ratio", "visual_style")

DECISION_SOURCES = ("user_explicit", "agent_proposed", "default")

# Creative craft directives preserved from shot-level input.  Source/audit
# metadata and arbitrary fields are dropped here so they cannot reach the
# compiler prompt blocks.
CREATIVE_CRAFT_KEYS = frozenset(
    {
        "performance",
        "action_feedback",
        "continuity_state",
        "transition",
        "style_detail",
        "sound_craft",
        "motion_path",
        "style_notes",
    }
)
CONSTRAINT_KINDS = (
     "camera",
    "composition",
    "sound",
    "visual",
    "action",
    "negative",
    "duration",
    "ratio",
    "performance",
    "continuity",
    "transition",
    "style",
    "sound_craft",
    "craft",
    "other",
)

DELIVERY_TARGETS = ("prompt", "settings", "pending")

STYLE_REGISTERS = ("photoreal", "stylized", "illustration", "graphic")

SOUND_MODES = ("silent", "ambience_only", "dialogue_allowed", "unspecified")


class IntentHandoffError(ValueError):
    """Raised when an intent handoff cannot be trusted as the input contract."""


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload or payload[key] in (None, ""):
        raise IntentHandoffError("intent handoff missing required field: %s" % key)
    return payload[key]


def _decision_value(decisions: dict[str, Any], field: str) -> Any:
    record = decisions.get(field)
    if not isinstance(record, dict):
        raise IntentHandoffError("decision %s must be an object" % field)
    if "value" not in record:
        raise IntentHandoffError("decision %s has no value" % field)
    source = record.get("source")
    if source not in DECISION_SOURCES:
        raise IntentHandoffError(
            "decision %s has invalid source %r (allowed: %s)"
            % (field, source, ", ".join(DECISION_SOURCES))
        )
    locked = record.get("locked")
    if not isinstance(locked, bool):
        raise IntentHandoffError("decision %s locked must be a boolean" % field)
    if locked and source != "user_explicit":
        raise IntentHandoffError(
            "decision %s cannot be locked while its source is %r; only a user-explicit "
            "decision may be reported as locked" % (field, source)
        )
    if source == "user_explicit" and not locked:
        raise IntentHandoffError(
            "decision %s is user_explicit and must be locked" % field
        )
    return record


def validate_intent_handoff(payload: Any) -> dict[str, Any]:
    """Validate an intent handoff document; return it unchanged when valid."""

    if not isinstance(payload, dict):
        raise IntentHandoffError("intent handoff must be a JSON object")
    fmt = payload.get("intent_format")
    if fmt != FORMAT:
        raise IntentHandoffError(
            "unsupported intent_format %r (this compiler understands %r)"
            % (fmt, FORMAT)
        )

    allowed_top = {"intent_format", "goal", "task_type", "decisions", "shots", "constraints", "entities", "delivery", "sound", "world_state_initial", "version", "source", "evidence", "metadata", "audit", "notes", "provenance"}
    unknown = set(payload) - allowed_top
    if unknown:
        raise IntentHandoffError("unmapped task fields: %s; use declared decisions/constraints or keep unresolved" % ", ".join(sorted(unknown)))

    _require(payload, "goal")
    task_type = payload.get("task_type")
    if task_type not in ("prompt_only", "single_shot", "full_film"):
        raise IntentHandoffError("invalid task_type: %r" % (task_type,))

    decisions = payload.get("decisions")
    if not isinstance(decisions, dict):
        raise IntentHandoffError("decisions must be an object")
    for field in MATERIAL_DECISIONS:
        _decision_value(decisions, field)
    for field, record in decisions.items():
        if field not in MATERIAL_DECISIONS:
            _decision_value(decisions, field)

    style = decisions["visual_style"]["value"]
    if not isinstance(style, dict) or not str(style.get("text") or "").strip():
        raise IntentHandoffError("visual_style.value.text is required")
    register = style.get("register")
    if register not in STYLE_REGISTERS:
        raise IntentHandoffError(
            "visual_style.value.register must be one of %s" % ", ".join(STYLE_REGISTERS)
        )

    duration = decisions["duration_sec"]["value"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        raise IntentHandoffError("duration_sec decision must be a positive number")
    ratio = decisions["aspect_ratio"]["value"]
    if not isinstance(ratio, str) or ":" not in ratio:
        raise IntentHandoffError("aspect_ratio decision must look like 'W:H'")

    shots = payload.get("shots")
    if not isinstance(shots, list) or not shots:
        raise IntentHandoffError("shots must be a non-empty list")
    seen_ids = set()
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            raise IntentHandoffError("shot %d must be an object" % index)
        allowed_shot = set(CREATIVE_CRAFT_KEYS) | {"id", "duration_sec", "description", "shot_kind", "sound", "risk", "no_dialogue", "generation_duration_sec", "cut_range", "version", "asset_refs", "world_state_delta", "world_state_refs", "source", "evidence", "metadata", "audit", "notes", "provenance"}
        unknown = set(shot) - allowed_shot
        if unknown:
            raise IntentHandoffError("unmapped shot fields: %s; do not silently discard creative requirements" % ", ".join(sorted(unknown)))
        shot_id = str(shot.get("id") or "").strip()
        if not shot_id:
            raise IntentHandoffError("shot %d has no id" % index)
        if shot_id in seen_ids:
            raise IntentHandoffError("duplicate shot id: %s" % shot_id)
        seen_ids.add(shot_id)
        if not str(shot.get("description") or "").strip():
            raise IntentHandoffError("shot %s has no description" % shot_id)
        shot_duration = shot.get("duration_sec")
        if isinstance(shot_duration, bool) or not isinstance(shot_duration, (int, float)) or shot_duration <= 0:
            raise IntentHandoffError("shot %s duration_sec must be a positive number" % shot_id)
        if "sound" in shot and shot["sound"] is not None:
            validate_sound_intent(shot["sound"], "shot %s" % shot_id)
    if task_type == "single_shot" and len(shots) != 1:
        raise IntentHandoffError("single_shot requires exactly one shot")

    if "sound" in payload and payload["sound"] is not None:
        validate_sound_intent(payload["sound"], "project")

    constraints = payload.get("constraints")
    if constraints is None:
        constraints = []
    if not isinstance(constraints, list):
        raise IntentHandoffError("constraints must be a list")
    constraint_ids = set()
    for index, constraint in enumerate(constraints, start=1):
        if not isinstance(constraint, dict):
            raise IntentHandoffError("constraint %d must be an object" % index)
        cid = str(constraint.get("id") or "").strip()
        if not cid:
            raise IntentHandoffError("constraint %d has no id" % index)
        if cid in constraint_ids:
            raise IntentHandoffError("duplicate constraint id: %s" % cid)
        constraint_ids.add(cid)
        if not str(constraint.get("text") or "").strip():
            raise IntentHandoffError("constraint %s has no text" % cid)
        kind = constraint.get("kind")
        if kind not in CONSTRAINT_KINDS:
            raise IntentHandoffError(
                "constraint %s has invalid kind %r (allowed: %s)"
                % (cid, kind, ", ".join(CONSTRAINT_KINDS))
            )
        delivery = constraint.get("delivery")
        if delivery not in DELIVERY_TARGETS:
            raise IntentHandoffError(
                "constraint %s has invalid delivery %r (allowed: %s)"
                % (cid, delivery, ", ".join(DELIVERY_TARGETS))
            )
        source = constraint.get("source")
        if source not in DECISION_SOURCES:
            raise IntentHandoffError(
                "constraint %s has invalid source %r" % (cid, source)
            )
        locked = constraint.get("locked")
        if not isinstance(locked, bool):
            raise IntentHandoffError("constraint %s locked must be a boolean" % cid)
        semantics = constraint.get("semantics")
        if delivery == "prompt" and not isinstance(semantics, dict):
            raise IntentHandoffError(
                "constraint %s is delivered to the prompt and needs a semantics object "
                "(required_any / forbidden markers) so acceptance can judge meaning, "
                "not string equality" % cid
            )

    entities = payload.get("entities")
    if entities is None:
        entities = []
    if not isinstance(entities, list):
        raise IntentHandoffError("entities must be a list")

    delivery = payload.get("delivery")
    if delivery is not None and not isinstance(delivery, dict):
        raise IntentHandoffError("delivery must be an object")

    if "version" in payload and (type(payload["version"]) is not int or payload["version"] < 1):
        raise IntentHandoffError("version must be a positive integer")
    if "world_state_initial" in payload or any("world_state_delta" in shot or "world_state_refs" in shot for shot in shots):
        try:
            from scripts.compile_shot_graph import resolve_world_states
        except ImportError:
            from compile_shot_graph import resolve_world_states
        try:
            resolve_world_states(payload)
        except (ValueError, TypeError) as exc:
            raise IntentHandoffError("invalid world state: %s" % exc) from exc
    return payload


def validate_sound_intent(sound: Any, label: str) -> dict[str, Any]:
    """Validate a structured sound intent (mode / allowed / forbidden)."""

    if not isinstance(sound, dict):
        raise IntentHandoffError("%s sound intent must be an object" % label)
    mode = sound.get("mode")
    if mode not in SOUND_MODES:
        raise IntentHandoffError(
            "%s sound intent mode must be one of %s" % (label, ", ".join(SOUND_MODES))
        )
    for key in ("allowed", "forbidden"):
        value = sound.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise IntentHandoffError("%s sound intent %s must be a list of strings" % (label, key))
    source = sound.get("source")
    if source is not None and source not in DECISION_SOURCES:
        raise IntentHandoffError("%s sound intent has invalid source %r" % (label, source))
    locked = sound.get("locked")
    if locked is not None and not isinstance(locked, bool):
        raise IntentHandoffError("%s sound intent locked must be a boolean" % label)
    return sound


def decision_log(decisions: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a provenance record for every decision in the handoff."""

    log = []
    for field in sorted(decisions):
        record = decisions[field]
        source = record.get("source")
        locked = bool(record.get("locked"))
        log.append(
            {
                "field": field,
                "value": record.get("value"),
                "source": source,
                "locked": locked,
                "status": "locked" if locked else "proposed",
                "material": field in MATERIAL_DECISIONS,
            }
        )
    return log


def to_compiler_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a validated intent handoff into the compiler input dict.

    Explicit user values are copied verbatim; nothing is substituted.
    """

    validate_intent_handoff(payload)
    decisions = payload["decisions"]
    style = decisions["visual_style"]["value"]

    shots = []
    for shot in payload["shots"]:
        item = {
            "id": str(shot["id"]).strip(),
            "duration_sec": shot["duration_sec"],
            "description": str(shot["description"]).strip(),
        }
        kind = shot.get("shot_kind")
        if kind:
            item["shot_kind"] = str(kind).strip().lower()
        if shot.get("sound") is not None:
            item["sound"] = validate_sound_intent(shot["sound"], "shot %s" % item["id"])
        for key in ("risk", "no_dialogue", "generation_duration_sec", "cut_range", "version", "asset_refs", "world_state_delta", "world_state_refs"):
            if key in shot:
                item[key] = copy.deepcopy(shot[key])
        # Preserve task-specific creative craft directives (allowlist only).
        for key, value in shot.items():
            if key in ("id", "duration_sec", "description", "shot_kind", "sound", "risk",
                       "no_dialogue", "generation_duration_sec", "cut_range", "version", "asset_refs"):
                continue
            if key not in CREATIVE_CRAFT_KEYS:
                continue
            item[key] = value
        shots.append(item)

    data: dict[str, Any] = {
        "goal": str(payload["goal"]).strip(),
        "task_type": payload["task_type"],
        "duration_sec": decisions["duration_sec"]["value"],
        "aspect_ratio": decisions["aspect_ratio"]["value"],
        "visual_style": style["text"],
        "visual_style_register": style["register"],
        "shots": shots,
        "entities": list(payload.get("entities") or []),
        "constraints": list(payload.get("constraints") or []),
        "delivery": dict(payload.get("delivery") or {}),
        "intent_format": FORMAT,
        "decision_log": decision_log(decisions),
    }
    if style.get("technique"):
        data["visual_style_technique"] = style["technique"]
    if payload.get("sound") is not None:
        data["sound"] = validate_sound_intent(payload["sound"], "project")
    delivery = data["delivery"]
    delivery.setdefault("ignition_allowed", False)
    delivery.setdefault("requires_media_generation", False)
    delivery.setdefault("requires_export", False)
    for field in ("world_state_initial", "version"):
        if field in payload:
            data[field] = copy.deepcopy(payload[field])
    return data


def load_intent_handoff(path: str | Path) -> dict[str, Any]:
    """Read and validate an intent handoff file."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_intent_handoff(payload)


__all__ = [
    "FORMAT",
    "MATERIAL_DECISIONS",
    "CONSTRAINT_KINDS",
    "DELIVERY_TARGETS",
    "STYLE_REGISTERS",
    "SOUND_MODES",
    "IntentHandoffError",
    "decision_log",
    "load_intent_handoff",
    "to_compiler_input",
    "validate_intent_handoff",
    "validate_sound_intent",
]
