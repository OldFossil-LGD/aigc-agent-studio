"""Compile a simple production goal into a production contract.

This module intentionally does not call LibTV or create media. It turns a
small input document into explicit production decisions and assumptions.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

try:
    from scripts.reverse_contract import (
        evidence_default,
        infer_source_access,
        mode_errors,
        normalize_mode,
    )
    from scripts.production_task_profile import validate_task_input
except ImportError:
    from reverse_contract import evidence_default, infer_source_access, mode_errors, normalize_mode
    from production_task_profile import validate_task_input


DEFAULT_DURATION_SEC = 120
DEFAULT_RATIO = "16:9"
DEFAULT_STYLE = "写实电影纪录片"

# mirror          = 忠实镜像源画布，结构只许 1:1，必须带 source_node_id 血缘
# production_plan = 可重构的规范化生产计划，允许拆批次/加契约层，但不许声明源级忠实
DELIVERABLES = ("mirror", "production_plan")
MIRROR_MODES = ("source_replica", "copy_reverse")


def _coerce_positive_number(value: Any, field_name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError("%s must be a positive number" % field_name)
    try:
        number = float(value) if isinstance(value, str) else value
        number = float(number)
    except (TypeError, ValueError):
        raise ValueError("%s must be a positive number" % field_name)
    if not math.isfinite(number):
        raise ValueError("%s must be a finite positive number" % field_name)
    if number <= 0:
        raise ValueError("%s must be positive" % field_name)
    if number.is_integer():
        return int(number)
    return number


try:
    from scripts.production_timing import resolve_shot_timing
except ImportError:
    from production_timing import resolve_shot_timing


def _normalise_shots(data: dict[str, Any], duration_sec: int) -> tuple[list[dict[str, Any]], list[str]]:
    shots = copy.deepcopy(data.get("shots") or [])
    assumptions: list[str] = []
    if not shots:
        shots = [
            {
                "id": "shot_01",
                "duration_sec": duration_sec,
                "description": data.get("goal", "未命名生产目标"),
                "risk": "medium",
            }
        ]
        assumptions.append("未提供镜头表，已生成单镜占位；正式生产前必须由分镜编译补齐。")
    else:
        for shot in shots:
            if not isinstance(shot, dict):
                raise ValueError("shot must be an object")
            if "duration_sec" in shot and shot.get("duration_sec") not in (None, ""):
                shot["duration_sec"] = _coerce_positive_number(
                    shot.get("duration_sec"), "shot duration_sec"
                )
            if "generation_duration_sec" in shot:
                shot["generation_duration_sec"] = _coerce_positive_number(
                    shot.get("generation_duration_sec"), "shot generation_duration_sec"
                )
            if "cut_range" in shot:
                cut_value = shot.get("cut_range")
                if cut_value in (None, ""):
                    raise ValueError("shot cut_range must be an object")
                if not isinstance(cut_value, dict):
                    raise ValueError("shot cut_range must be an object")
            explicit_generation = (
                "generation_duration_sec" in shot
                and shot.get("generation_duration_sec") not in (None, "")
            )
            explicit_cut = "cut_range" in shot
            timing = resolve_shot_timing(shot)
            if timing["cut_range"] is not None:
                shot["cut_range"] = timing["cut_range"]
            if (
                explicit_generation
                and not explicit_cut
                and timing["cut_range"] is not None
            ):
                assumptions.append(
                    "shot %s: generation_duration_sec provided without cut_range; defaulted cut_range to [0, %s]."
                    % (shot.get("id"), timing["cut_range"]["end_sec"])
                )
    return shots, assumptions


def _normalise_constraints(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalise constraints to dict records.

    Legacy plain strings stay supported (they become `user_explicit` prompt
    constraints). Dict constraints keep their kind / delivery / source so the
    compiler can prove *where* each constraint is consumed.
    """

    raw = data.get("constraints")
    if raw in (None, ""):
        return [], []
    if not isinstance(raw, list):
        raise ValueError("constraints must be a list")
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            out.append(
                {
                    "id": "constraint_%02d" % index,
                    "kind": "other",
                    "text": text,
                    "delivery": "prompt",
                    "source": "user_explicit",
                    "locked": True,
                    "shots": [],
                    "semantics": {},
                }
            )
            continue
        if not isinstance(item, dict):
            raise ValueError("constraint %d must be an object or a string" % index)
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        record = {
            "id": str(item.get("id") or "constraint_%02d" % index),
            "kind": str(item.get("kind") or "other"),
            "text": text,
            "delivery": str(item.get("delivery") or "prompt"),
            "source": str(item.get("source") or "user_explicit"),
            "locked": bool(item.get("locked")),
            "shots": list(item.get("shots") or []),
            "semantics": dict(item.get("semantics") or {}),
        }
        if record["delivery"] == "settings":
            warnings.append(
                "约束 %s 声明交付到 settings（生成参数），当前编译器只在提示词与图参数层兑现；"
                "未落到实际参数前不得视为已兑现。" % record["id"]
            )
        out.append(record)
    return out, warnings


def _normalise_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    entities = copy.deepcopy(data.get("entities") or [])
    for entity in entities:
        entity.setdefault("id", entity.get("name") or "entity")
        entity.setdefault("kind", "other")
        entity.setdefault("reuse_count", 1)
        entity.setdefault("state_versions", 1)
    return entities


def compile_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Return a production contract plus explicit assumptions and questions."""

    if not isinstance(data, dict):
        raise TypeError("input must be a dict")
    task_type = validate_task_input(data)
    goal = str(data.get("goal") or "").strip()
    if not goal:
        raise ValueError("goal is required")

    assumptions: list[str] = []
    questions: list[str] = []

    raw_duration = data.get("duration_sec", None)
    if raw_duration in (None, ""):
        duration_sec = DEFAULT_DURATION_SEC
        assumptions.append(f"未提供时长，按 {duration_sec} 秒规划。")
    else:
        duration_sec = _coerce_positive_number(raw_duration, "duration_sec")

    ratio = data.get("aspect_ratio") or DEFAULT_RATIO
    if not data.get("aspect_ratio"):
        assumptions.append(f"未提供画幅，按 {ratio} 规划。")

    visual_style = data.get("visual_style") or DEFAULT_STYLE
    if not data.get("visual_style"):
        assumptions.append(f"未提供视觉风格，按「{visual_style}」规划。")

    source_project_uuid = data.get("source_project_uuid")
    copy_project_uuid = data.get("copy_project_uuid")
    requested_mode = data.get("mode") or data.get("production_mode")
    if requested_mode:
        production_mode, mode_warnings = normalize_mode(requested_mode)
        assumptions.extend(mode_warnings)
    elif copy_project_uuid:
        production_mode, mode_warnings = normalize_mode("copy_reverse")
        assumptions.extend(mode_warnings)
    elif source_project_uuid:
        production_mode, mode_warnings = normalize_mode("source_replica")
        assumptions.extend(mode_warnings)
    elif data.get("source_film"):
        production_mode, mode_warnings = normalize_mode("content_reverse")
        assumptions.extend(mode_warnings)
    else:
        production_mode, _ = normalize_mode("production_build")
        assumptions.append("未声明任务模式，默认按 production_build 规划。")

    source_access = infer_source_access({**data, "source_project_uuid": source_project_uuid, "copy_project_uuid": copy_project_uuid}, production_mode)
    evidence = data.get("evidence_default") or evidence_default(production_mode, source_access)
    work_profile = copy.deepcopy(data.get("work_profile") or {})
    if not work_profile and data.get("work_profile_path"):
        work_profile = json.loads(Path(data["work_profile_path"]).read_text(encoding="utf-8"))
    blind_test = copy.deepcopy(data.get("blind_test") or {})

    requested_deliverable = (data.get("deliverable") or "").strip()
    if requested_deliverable and requested_deliverable not in DELIVERABLES:
        raise ValueError("invalid deliverable: %s" % requested_deliverable)
    if requested_deliverable:
        deliverable = requested_deliverable
    elif production_mode in MIRROR_MODES:
        deliverable = None
        questions.append(
            "%s 必须声明 deliverable：mirror（忠实镜像源画布）或 production_plan（可重构的生产计划）。"
            % production_mode
        )
    else:
        deliverable = "production_plan"

    if production_mode == "source_replica" and source_access != "original_readback":
        questions.append("source_replica 只有 original_readback 才能成立；副本请改用 copy_reverse。")
    if production_mode == "copy_reverse" and not copy_project_uuid:
        questions.append("copy_reverse 必须提供 copy_project_uuid。")
    if production_mode == "content_reverse" and not data.get("source_film"):
        questions.append("content_reverse 必须提供 source_film 或可读成片路径。")
    if production_mode in {"source_replica", "copy_reverse"} and not source_project_uuid:
        questions.append("%s 必须提供 source_project_uuid（推定原项目 UUID）。" % production_mode)
    if deliverable == "mirror" and not data.get("source_graph_path"):
        questions.append("mirror 必须以 source_graph_path 指向只读回读文件，否则无法建立 source_node_id 血缘。")
    if production_mode in ("content_reverse", "copy_reverse", "source_replica", "rule_distill") and not work_profile:
        questions.append(
            "%s 必须先产出该作品自己的 work_profile（scripts/work_profile.py --units ...），"
            "不得套用别的作品数值。" % production_mode
        )

    shots, shot_assumptions = _normalise_shots(data, duration_sec)
    assumptions.extend(shot_assumptions)

    constraints, constraint_warnings = _normalise_constraints(data)
    assumptions.extend(constraint_warnings)

    # Decision provenance: an explicit user value is never replaced by a
    # default, and a value the compiler had to supply is marked `proposed`
    # (never `locked`). The decision log is the audit trail for that.
    decision_log = list(data.get("decision_log") or [])
    decision_by_field = {
        item.get("field"): item for item in decision_log if isinstance(item, dict)
    }
    for field, actual in (
        ("duration_sec", duration_sec),
        ("aspect_ratio", ratio),
        ("visual_style", visual_style),
    ):
        if field in decision_by_field:
            continue
        decision_by_field[field] = {
            "field": field,
            "value": actual,
            "source": "default",
            "locked": False,
            "status": "proposed",
            "material": True,
        }
    resolved_decision_log = [decision_by_field[field] for field in sorted(decision_by_field)]
    proposed_fields = [
        item["field"] for item in resolved_decision_log if item.get("source") != "user_explicit"
    ]

    if "no_dialogue" in data and not isinstance(data.get("no_dialogue"), bool):
        raise ValueError("no_dialogue must be a boolean")
    for _shot in shots:
        if isinstance(_shot, dict) and "no_dialogue" in _shot and not isinstance(_shot.get("no_dialogue"), bool):
            raise ValueError("no_dialogue must be a boolean")

    sound = copy.deepcopy(data.get("sound")) if isinstance(data.get("sound"), dict) else None

    delivery = copy.deepcopy(data.get("delivery") or {})
    delivery.setdefault("ignition_allowed", False)
    delivery.setdefault("requires_media_generation", False)
    delivery.setdefault("requires_export", False)
    delivery.setdefault("artifacts", ["production_contract", "asset_graph_plan", "shot_graph_plan", "prompt_packages", "capability_gate"])

    contract = {
        "goal": goal,
        "task_type": task_type,
        "mode": production_mode,
        "production_mode": production_mode,
        "deliverable": deliverable,
        "source_access": source_access,
        "evidence_default": evidence,
        "duration_sec": duration_sec,
        "aspect_ratio": ratio,
        "fps": int(data.get("fps") or 24),
        "visual_style": visual_style,
        "source_project_uuid": source_project_uuid,
        "copy_project_uuid": copy_project_uuid,
        "source_film": data.get("source_film"),
        "source_graph_path": data.get("source_graph_path"),
        "param_cache_dir": data.get("param_cache_dir"),
        "fidelity_claim": data.get("fidelity_claim"),
        "entities": _normalise_entities(data),
        "shots": shots,
        "audio": copy.deepcopy(data.get("audio") or []),
        "work_profile": work_profile,
        "blind_test": blind_test,
        "delivery": delivery,
        "constraints": constraints,
        "decision_log": resolved_decision_log,
        "proposed_decisions": proposed_fields,
    }
    if "world_state_initial" in data:
        contract["world_state_initial"] = copy.deepcopy(data["world_state_initial"])
    if "version" in data:
        if type(data["version"]) is not int or data["version"] < 1:
            raise ValueError("graph version must be a positive integer")
        contract["version"] = data["version"]
    if data.get("visual_style_register"):
        contract["visual_style_register"] = str(data["visual_style_register"])
    if data.get("visual_style_technique"):
        contract["visual_style_technique"] = str(data["visual_style_technique"])
    if sound is not None:
        contract["sound"] = sound
    if data.get("intent_format"):
        contract["intent_format"] = str(data["intent_format"])
    if "no_dialogue" in data:
        contract["no_dialogue"] = data["no_dialogue"]
    for error in mode_errors(contract):
        if error not in questions:
            questions.append(error)
    # A material decision the user never made is a question, not a settled
    # default: the contract must not claim READY while a value is still a
    # proposal the user has not seen.
    if proposed_fields and task_type in ("prompt_only", "single_shot"):
        questions.append(
            "以下关键决定尚未由用户确认，当前为拟订值（未锁定）：%s；确认前不得宣称创作已定。"
            % "、".join(proposed_fields)
        )
    status = "DRAFT" if questions else "READY"
    contract["status"] = status
    contract["readiness"] = "draft" if questions else "ready"
    return {"production_contract": contract, "assumptions": assumptions, "questions": questions, "status": status}


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out")
    args = parser.parse_args()
    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    result = compile_contract(data)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
