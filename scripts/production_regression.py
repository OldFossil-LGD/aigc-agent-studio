#!/usr/bin/env python3
"""Static production-compiler regression.

This script intentionally does not call LibTV. It verifies that the recorded
work-profile baselines remain present as static fixtures and that a synthetic
two-minute fixture can compile into a role-complete production plan without
ignition. The baseline numbers are historical recorded fixtures, not live
source verification.
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

try:
    from scripts.compile_production import compile_production
except ImportError:
    from compile_production import compile_production


BASELINE_LABEL = "static recorded fixture (not live source verification)"

BASELINE = {
    "W1": {
        "nodes": 180,
        "edges": 775,
        "images": 42,
        "videos": 118,
        "groups": 19,
        "image_to_image": 0,
    },
    "W2": {
        "nodes": 762,
        "edges": 1926,
        "images": 220,
        "videos": 499,
        "groups": 27,
        "image_to_image": 89,
    },
    "W3": {
        "nodes": 581,
        "edges": 1550,
        "images": 178,
        "videos": 194,
        "groups": 81,
        "image_to_image": None,
    },
    "FANGYANG_SOURCE_COPY": {
        "nodes": 437,
        "edges": 377,
        "images": 319,
        "videos": 61,
        "groups": 49,
        "image_to_image": 286,
    },
}

REQUIRED_ARTIFACTS = [
    "01_production_contract.json",
    "02_asset_graph_plan.json",
    "03_shot_graph_plan.json",
    "04_prompt_packages.jsonl",
    "05_platform_execution_plan.json",
    "06_gate_results.json",
    "07_regression_ledger.json",
    "08_libtv_command_plan.json",
]


def _fixture() -> dict:
    shots = [
        {
            "id": "shot_%02d" % i,
            "duration_sec": 10,
            "risk": "high" if i % 3 == 0 else "medium",
            "description": (
                "村寨石桥上晨雾渐散，银发老人立于桥头望向放飞的纸鸢，"
                "女孩在桥下奔跑，纸鸢升空掠过吊脚楼屋檐"
                if i % 3 == 0
                else "吊脚楼廊下，老人与女孩并肩调试纸鸢骨架，"
                "竹篾、红绸与蓝白纸面在手间展开"
            ),
        }
        for i in range(1, 13)
    ]
    return {
        "goal": "两分钟合成生产验收片（合成测试数据，非真实来源声明）",
        "duration_sec": 120,
        "aspect_ratio": "16:9",
        "visual_style": "写实电影纪录片",
        "production_mode": "production_build",
        "entities": [
            {"id": "elder", "name": "elder", "kind": "character", "description": "银发老人，深色长衫，左脸疤痕，手持竹杖", "state": "站立于村口", "reuse_count": 8, "state_versions": 2},
            {"id": "child", "name": "child", "kind": "character", "description": "八岁女孩，红蓝拼接棉袄，双丫髻，手持纸鸢", "reuse_count": 4},
            {"id": "village", "name": "village", "kind": "scene", "description": "黔东南木结构吊脚楼村寨，青石板路，晨雾", "reuse_count": 6},
            {"id": "kite", "name": "kite", "kind": "prop", "description": "竹篾骨架纸鸢，蓝白红三色，尾部红绸", "state": "未放飞", "reuse_count": 5, "state_versions": 2},
        ],
        "shots": shots,
        "delivery": {"ignition_allowed": False, "requires_media_generation": False},
    }


def _negative_fixture() -> dict:
    fixture = copy.deepcopy(_fixture())
    for entity in fixture.get("entities") or []:
        if entity.get("id") == "elder":
            entity.pop("description", None)
    fixture["goal"] = "两分钟合成生产验收片（缺实体描述反例，合成测试数据）"
    return fixture


def _unresolved_from(result: dict) -> list:
    unresolved = []
    for package in result.get("prompts") or []:
        unresolved.extend(package.get("unresolved") or [])
    return sorted(set(unresolved))


def _artifact_issues(out: Path) -> list:
    issues = []
    for name in REQUIRED_ARTIFACTS:
        path = out / name
        if not path.exists():
            issues.append(name)
            continue
        if name.endswith(".json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                issues.append(name)
        elif name.endswith(".jsonl"):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
            except (OSError, json.JSONDecodeError):
                issues.append(name)
    return issues


def _run_flags(out: Path) -> tuple[bool, bool]:
    platform_run = False
    command_run = False
    platform_path = out / "05_platform_execution_plan.json"
    command_path = out / "08_libtv_command_plan.json"
    if platform_path.exists():
        try:
            payload = json.loads(platform_path.read_text(encoding="utf-8"))
            platform_run = any(bool(step.get("run")) for step in payload.get("steps") or [])
        except (OSError, json.JSONDecodeError):
            platform_run = True
    if command_path.exists():
        try:
            payload = json.loads(command_path.read_text(encoding="utf-8"))
            command_run = bool(payload.get("safety", {}).get("run")) or any(
                bool(command.get("run")) for command in payload.get("commands") or []
            )
        except (OSError, json.JSONDecodeError):
            command_run = True
    return platform_run, command_run


def _run_case(fixture: dict, expected_pass: bool) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "fixture"
        result = compile_production(fixture, out)
        gate = result["gate"]
        unresolved = _unresolved_from(result)
        gate_failures = [str(item.get("code")) for item in (gate.get("failures") or [])]
        artifact_issues = _artifact_issues(out)
        platform_run, command_run = _run_flags(out)

        blocked = gate.get("status") != "PASS"
        prompt_identity_codes = {"PROMPT_UNRESOLVED", "PROMPT_NOT_READY"}
        has_prompt_identity_failure = bool(prompt_identity_codes & set(gate_failures))
        has_identity_unresolved = any(
            "missing_entity_identity" in item or "missing_entity_description" in item
            for item in unresolved
        )

        if expected_pass:
            passed = (
                gate.get("status") == "PASS"
                and not artifact_issues
                and not platform_run
                and not command_run
                and not unresolved
                and not gate_failures
            )
        else:
            passed = (
                blocked
                and (has_prompt_identity_failure or has_identity_unresolved)
                and not artifact_issues
                and not platform_run
                and not command_run
            )

        failure_codes = list(gate_failures)
        if artifact_issues:
            failure_codes.append("MISSING_ARTIFACTS")
        if platform_run:
            failure_codes.append("IGNITION_IN_PLATFORM_PLAN")
        if command_run:
            failure_codes.append("IGNITION_IN_COMMAND_PLAN")
        if expected_pass and not passed:
            failure_codes.append("POSITIVE_FIXTURE_FAILED")
        if not expected_pass:
            if gate.get("status") == "PASS":
                failure_codes.append("NEGATIVE_FIXTURE_ACCEPTED")
            elif not (has_prompt_identity_failure or has_identity_unresolved):
                failure_codes.append("NEGATIVE_FIXTURE_NOT_REJECTED")

        return {
            "expected": "PASS" if expected_pass else "FAIL",
            "gate_status": gate.get("status"),
            "status": "PASS" if passed else "FAIL",
            "failure_codes": failure_codes,
            "artifact_issues": artifact_issues,
            "platform_run": platform_run,
            "command_run": command_run,
            "unresolved": unresolved,
        }


def run_regression() -> dict:
    failures = []
    for name, baseline in BASELINE.items():
        if baseline["nodes"] <= 0 or baseline["edges"] <= 0:
            failures.append({"code": "INVALID_BASELINE", "profile": name})

    positive = _run_case(_fixture(), True)
    negative = _run_case(_negative_fixture(), False)

    if positive["status"] != "PASS":
        failures.append({"code": "POSITIVE_FIXTURE_FAILED", "case": "positive"})
    if negative["status"] != "PASS":
        failures.append({"code": "NEGATIVE_FIXTURE_FAILED", "case": "negative"})

    no_ignition = (
        not positive["platform_run"]
        and not positive["command_run"]
        and not negative["platform_run"]
        and not negative["command_run"]
    )

    result = {
        "status": "PASS" if not failures else "FAIL",
        "baseline": BASELINE,
        "baseline_label": BASELINE_LABEL,
        "positive": positive,
        "negative": negative,
        "failures": failures,
        "no_ignition": no_ignition,
    }
    return result


def main() -> int:
    result = run_regression()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
