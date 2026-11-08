#!/usr/bin/env python3
"""One-command production compiler entrypoint.

Reads a small JSON production input, writes the compiler artifacts, and
exits non-zero when the production capability gate fails.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.production_records import initialize_records, apply_rework, bind_record_packages
    from scripts.compile_asset_graph import compile_asset_graph
    from scripts.compile_libtv_commands import compile_commands
    from scripts.compile_production_contract import compile_contract
    from scripts.compile_prompt_packages import compile_prompt_packages
    from scripts.compile_shot_graph import compile_shot_graph
    from scripts.production_capability_gate import evaluate
    from scripts.reverse_claim_lint import lint_payload
    from scripts.compile_text_input import parse_text_input
    from scripts.intent_handoff import IntentHandoffError, to_compiler_input
    from scripts.production_schema_validation import (
        validate_contract_result,
        validate_prompt_package,
        validate_shot_graph,
    )
    from scripts.production_task_profile import (
        project_task_graph,
        task_profile_result,
        task_type_for,
    )
except ImportError:
    from production_records import initialize_records, apply_rework, bind_record_packages
    from compile_asset_graph import compile_asset_graph
    from compile_libtv_commands import compile_commands
    from compile_production_contract import compile_contract
    from compile_prompt_packages import compile_prompt_packages
    from compile_shot_graph import compile_shot_graph
    from production_capability_gate import evaluate
    from reverse_claim_lint import lint_payload
    from compile_text_input import parse_text_input
    from intent_handoff import IntentHandoffError, to_compiler_input
    from production_schema_validation import (
        validate_contract_result,
        validate_prompt_package,
        validate_shot_graph,
    )
    from production_task_profile import (
        project_task_graph,
        task_profile_result,
        task_type_for,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _platform_plan(contract: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    steps = []
    for node in graph.get("nodes") or []:
        step = {
            "step": node["id"],
            "node_type": node["node_type"],
            "role": node["role"],
            "shot_id": node.get("shot_id"),
            "run": False,
            "ignition_allowed": False,
        }
        node_type = node.get("node_type")
        if node_type == "image":
            step["mode_type"] = node.get("mode_type", "text2image")
        elif node_type == "video":
            step["mode_type"] = node.get("mode_type", "mixed2video")
        elif node_type == "audio":
            step["mode_type"] = node.get("mode_type", "text2audio")
        steps.append(step)
    return {
        "project": {
            "name": contract.get("goal", "production"),
            "duration_sec": contract.get("duration_sec"),
            "ratio": contract.get("aspect_ratio"),
        },
        "steps": steps,
        "edges": graph.get("edges", []),
        "groups": graph.get("groups", []),
        "execution_boundary": {
            "compile_only": True,
            "run": False,
            "ignition_allowed": False,
        },
    }


def _claim_ledger(contract: dict[str, Any]) -> list[dict[str, Any]]:
    mode = contract.get("mode") or contract.get("production_mode") or "production_build"
    access = contract.get("source_access") or "none"
    evidence = contract.get("evidence_default") or "inferred"
    status = "verified" if evidence in {"source_readback", "copy_readback", "public_media", "text_explicit"} else "proposed"
    scope = {
        "source_replica": "original-level",
        "copy_reverse": "copy-level",
        "content_reverse": "content-level",
        "rule_distill": "rule-level",
        "production_build": "design-level",
    }.get(mode, "design-level")
    claim = {
        "claim_id": "mode_scope",
        "statement": "Task mode and source-access scope are explicitly declared.",
        "mode": mode,
        "deliverable": contract.get("deliverable") or "production_plan",
        "source_access": access,
        "evidence_class": evidence,
        "source_project_uuid": contract.get("source_project_uuid") or "",
        "copy_project_uuid": contract.get("copy_project_uuid") or "",
        "status": status,
        "scope": scope,
        "evidence": ["01_production_contract.json"],
        "replacement": "",
        "test": "reverse_claim_lint.py",
    }
    if mode == "rule_distill":
        claim["blind_test"] = contract.get("blind_test") or {}
    return [claim]


def _mirror_graph(contract: dict[str, Any]) -> dict[str, Any]:
    """Build a faithful mirror of a readback: one plan node per source node.

    Every node carries `source_node_id`, so `source_fidelity_lint --deliverable
    mirror` can prove 1:1 coverage instead of guessing from node counts.

    When `param_cache_dir` is given, each node also picks up the参数 from a cached
    `libtv node <id>` readback (model / modeType / settings / prompt / content).
    Without it the mirror is **structure-only** — that distinction is reported in
    `param_coverage` instead of being silently invisible.
    """
    path = contract.get("source_graph_path")
    if not path:
        return {"nodes": [], "edges": [], "deliverable": "mirror", "source_graph_path": None}
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    cache_dir = contract.get("param_cache_dir")
    with_params = 0
    missing_cache: list[str] = []
    nodes = []
    for node in source.get("nodes") or []:
        entry = {
            "id": node.get("id"),
            "source_node_id": node.get("id"),
            "node_type": node.get("type") or node.get("node_type"),
            "role": "mirror",
            "name": node.get("name"),
            "position": node.get("position"),
            "action": node.get("action"),
            "model": node.get("model"),
            "mode_type": node.get("modeType"),
            "settings": node.get("settings"),
            "run": False,
            "ignition_allowed": False,
        }
        if cache_dir:
            cached = Path(cache_dir) / ("%s.json" % node.get("id"))
            if cached.is_file():
                data = (json.loads(cached.read_text(encoding="utf-8")) or {}).get("data") or {}
                params = data.get("params") or {}
                entry.update(
                    {
                        "action": entry.get("action") or data.get("action"),
                        "model": params.get("model"),
                        "mode_type": params.get("modeType"),
                        "settings": params.get("settings"),
                        "prompt": params.get("prompt") or "",
                        "content": data.get("content"),
                        "params_readback": True,
                    }
                )
                if params.get("model") or params.get("modeType") or params.get("settings") or data.get("content"):
                    with_params += 1
            else:
                missing_cache.append(str(node.get("id")))
        nodes.append(entry)
    edges = [
        {
            "id": edge.get("id"),
            "source": edge.get("source"),
            "target": edge.get("target"),
            "kind": "mirror",
        }
        for edge in source.get("edges") or []
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "deliverable": "mirror",
        "source_graph_path": str(path),
        "param_cache_dir": str(cache_dir) if cache_dir else None,
        "param_coverage": {
            "enabled": bool(cache_dir),
            "nodes": len(nodes),
            "with_params": with_params,
            "missing_cache": len(missing_cache),
            "sample_missing": missing_cache[:10],
        },
    }


def compile_production(data: dict[str, Any], out_dir: Path, previous_graph: dict[str, Any] | None = None) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        _task_type = task_type_for(data) if isinstance(data, dict) else "full_film"
    except (TypeError, ValueError):
        _task_type = None
    if _task_type in ("prompt_only", "single_shot"):
        for _name in ("05_platform_execution_plan.json", "08_libtv_command_plan.json"):
            if (out_dir / _name).exists():
                raise ValueError("stale execution plan present: %s" % _name)

    contract_result = compile_contract(data)
    validate_contract_result(contract_result)
    contract = contract_result["production_contract"]
    task_type = task_type_for(contract) if isinstance(contract, dict) else "full_film"
    early_stop = task_type in ("prompt_only", "single_shot")
    deliverable = contract.get("deliverable") or "production_plan"
    if deliverable == "mirror":
        assets: dict[str, Any] = {"assets": [], "iteration_chains": []}
        graph = _mirror_graph(contract)
        prompts: list[dict[str, Any]] = []
    else:
        assets = compile_asset_graph(contract)
        graph = compile_shot_graph(contract, assets)
        if early_stop:
            graph = project_task_graph(contract, graph)
        prompts = compile_prompt_packages(contract, assets, graph)
        validate_shot_graph(graph)
        for package in prompts:
            validate_prompt_package(package)
    graph.update({
        "mode": contract.get("mode") or contract.get("production_mode"),
        "deliverable": deliverable,
        "source_access": contract.get("source_access"),
        "source_project_uuid": contract.get("source_project_uuid"),
        "copy_project_uuid": contract.get("copy_project_uuid"),
        "evidence_default": contract.get("evidence_default"),
    })
    if deliverable != "mirror":
        graph = (apply_rework(previous_graph, graph, prompts) if previous_graph is not None
                 else initialize_records(graph, prompts))
        prompts = bind_record_packages(graph, prompts)
    elif previous_graph is not None:
        raise ValueError("mirror rework is not supported by the production-record interface")
    gate = evaluate(contract, assets, graph, prompts)
    if early_stop:
        plan = {}
        commands = {"steps": [], "deliverable": deliverable}
    else:
        plan = _platform_plan(contract, graph)
        commands = compile_commands(graph, prompts) if deliverable != "mirror" else {"steps": [], "deliverable": "mirror"}
        commands.update({
            "mode": contract.get("mode") or contract.get("production_mode"),
            "deliverable": deliverable,
            "source_access": contract.get("source_access"),
            "source_project_uuid": contract.get("source_project_uuid"),
            "copy_project_uuid": contract.get("copy_project_uuid"),
            "evidence_default": contract.get("evidence_default"),
        })
    claims = _claim_ledger(contract)
    claim_errors = lint_payload(claims)
    claim_gate = {
        "status": "FAIL" if claim_errors else "PASS",
        "errors": claim_errors,
    }
    regression = {
        "compiler_version": "production-compiler-v1",
        "status": "FAIL" if gate["status"] == "FAIL" or claim_gate["status"] == "FAIL" else ("DRAFT" if contract_result["questions"] else "PASS"),
        "readiness": "draft" if (gate["status"] == "FAIL" or claim_gate["status"] == "FAIL" or contract_result["questions"]) else "ready",
        "assumptions": contract_result["assumptions"],
        "questions": contract_result["questions"],
        "claim_gate": claim_gate,
    }
    profile = task_profile_result(contract, regression)
    if deliverable != "mirror" and regression["status"] == "PASS":
        for node in graph["nodes"]:
            record = graph["production_records"][node["id"]]
            if record["state"] == "recovering":
                record["state"] = node["state"] = "graph_plan_ready"
                if "recovery" in record:
                    record["recovery"].update(status="plan_revalidated",
                        validated_gates=list(record["recovery"]["remaining_gates"]),remaining_gates=[])


    if deliverable != "mirror":
        validate_shot_graph(graph)
        for package in prompts:
            validate_prompt_package(package)

    _write_json(out_dir / "01_production_contract.json", contract_result)
    _write_json(out_dir / "02_asset_graph_plan.json", assets)
    _write_json(out_dir / "06_gate_results.json", gate)
    _write_json(out_dir / "07_regression_ledger.json", regression)
    _write_jsonl(out_dir / "09_claims.jsonl", claims)
    _write_json(out_dir / "10_claim_gate.json", claim_gate)
    _write_json(out_dir / "11_task_profile.json", profile)
    if claim_gate["status"] == "PASS":
        if deliverable == "mirror":
            _write_json(out_dir / "03_mirror_graph.json", graph)
            if not early_stop:
                _write_json(out_dir / "05_platform_execution_plan.json", plan)
        else:
            _write_json(out_dir / "03_shot_graph_plan.json", graph)
            _write_jsonl(out_dir / "04_prompt_packages.jsonl", prompts)
            if not early_stop:
                _write_json(out_dir / "05_platform_execution_plan.json", plan)
                _write_json(out_dir / "08_libtv_command_plan.json", commands)
    return {
        "gate": gate,
        "claim_gate": claim_gate,
        "contract": contract,
        "assets": assets,
        "graph": graph,
        "prompts": prompts,
        "task_profile": profile,
    }


def _load_input(input_path: Path) -> dict[str, Any]:
    """Load a compiler input from disk.

    Accepted inputs:
      * `.json` — a compiler input dict, or an `intent-handoff/v1` document
        (detected by its `intent_format` field and converted).
      * `.txt` / `.md` — plain prose. The text parser is deliberately
        conservative and is NOT a natural-language understanding engine; it
        only understands explicit `镜头N 时长 描述` lines. Use the intent
        handoff for anything else.
    """

    text = input_path.read_text(encoding="utf-8")
    if input_path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and data.get("intent_format"):
            try:
                return to_compiler_input(data)
            except IntentHandoffError as exc:
                raise ValueError("invalid intent handoff: %s" % exc) from exc
        return data
    return parse_text_input(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out", required=True)
    parser.add_argument("--previous-graph", help="Apply offline rework to this actual compiled record graph")
    parser.add_argument("--allow-gate-fail", action="store_true")
    args = parser.parse_args()
    input_path = Path(args.input)
    data = _load_input(input_path)
    previous = json.loads(Path(args.previous_graph).read_text(encoding="utf-8")) if args.previous_graph else None
    result = compile_production(data, Path(args.out), previous_graph=previous)
    print(json.dumps(result["gate"], ensure_ascii=False, indent=2))
    if (result["gate"]["status"] == "FAIL" or result["claim_gate"]["status"] == "FAIL") and not args.allow_gate_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
