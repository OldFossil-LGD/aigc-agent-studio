"""Shared task-scope policy for TASK-STOPS-01."""

from __future__ import annotations

import copy
from typing import Any

VALID_TASK_TYPES = ("full_film", "prompt_only", "single_shot")
EARLY_STOP_TASK_TYPES = ("prompt_only", "single_shot")
FORBIDDEN_EARLY_ROLES = {"assembly", "final_composite", "production_ledger", "qa"}


def _as_contract(contract):
    if not isinstance(contract, dict):
        raise TypeError("contract must be a dict")
    return contract


def task_type_for(contract: dict) -> str:
    contract = _as_contract(contract)
    if "task_type" not in contract:
        return "full_film"
    value = contract.get("task_type")
    if not isinstance(value, str) or value not in VALID_TASK_TYPES:
        raise ValueError("invalid task_type: %r" % value)
    return value


def validate_task_input(data: dict) -> str:
    if not isinstance(data, dict):
        raise TypeError("input must be a dict")
    task_type = task_type_for(data)
    if task_type == "single_shot":
        shots = data.get("shots")
        if not isinstance(shots, list) or len(shots) != 1:
            raise ValueError("single_shot requires exactly one explicit input shot")
        shot = shots[0]
        if not isinstance(shot, dict) or not str(shot.get("id", "")).strip():
            raise ValueError("single_shot requires exactly one explicit input shot")
    delivery = data.get("delivery")
    if not isinstance(delivery, dict):
        delivery = {}
    if task_type in EARLY_STOP_TASK_TYPES:
        if delivery.get("requires_media_generation") or delivery.get("requires_export"):
            raise ValueError("prompt task conflicts with media generation or export")
        if task_type == "single_shot" and str(data.get("deliverable") or "").strip() == "mirror":
            raise ValueError("single_shot conflicts with mirror deliverable")
    return task_type


def task_roles(contract: dict, roles) -> list:
    try:
        task_type = task_type_for(contract)
    except (TypeError, ValueError):
        task_type = None
    deliverable = contract.get("deliverable") if isinstance(contract, dict) else None
    early = task_type in EARLY_STOP_TASK_TYPES and deliverable != "mirror"
    result = []
    seen = set()
    for role in (roles or []):
        if early and role == "assembly":
            continue
        if role in seen:
            continue
        seen.add(role)
        result.append(role)
    return result


def task_terminal_roles(contract: dict, existing_roles) -> set:
    try:
        task_type = task_type_for(contract)
    except (TypeError, ValueError):
        task_type = None
    deliverable = contract.get("deliverable") if isinstance(contract, dict) else None
    if task_type in EARLY_STOP_TASK_TYPES and deliverable != "mirror":
        return {"selection", "audio", "video_candidate"}
    return set(existing_roles or [])


def project_task_graph(contract: dict, graph: dict) -> dict:
    if not isinstance(graph, dict):
        return graph
    result = copy.deepcopy(graph)
    try:
        task_type = task_type_for(contract)
    except (TypeError, ValueError):
        return result
    deliverable = contract.get("deliverable") if isinstance(contract, dict) else None
    if task_type not in EARLY_STOP_TASK_TYPES or deliverable == "mirror":
        return result

    nodes = result.get("nodes")
    if not isinstance(nodes, list):
        nodes = []
        result["nodes"] = nodes
    has_anchor_or_refine = any(
        isinstance(node, dict) and node.get("role") in ("asset_anchor", "refine")
        for node in nodes
    )
    removed_ids = set()
    remaining_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            remaining_nodes.append(node)
            continue
        role = node.get("role")
        if role in FORBIDDEN_EARLY_ROLES:
            removed_ids.add(node.get("id"))
            continue
        if role == "asset_manifest" and not has_anchor_or_refine:
            removed_ids.add(node.get("id"))
            continue
        remaining_nodes.append(node)
    result["nodes"] = remaining_nodes
    remaining_ids = {
        node.get("id") for node in remaining_nodes if isinstance(node, dict)
    }

    edges = result.get("edges")
    if isinstance(edges, list):
        new_edges = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source in removed_ids or target in removed_ids:
                continue
            if source not in remaining_ids or target not in remaining_ids:
                continue
            new_edges.append(edge)
        selections_by_shot = {}
        videos_by_shot = {}
        for node in remaining_nodes:
            if not isinstance(node, dict):
                continue
            role = node.get("role")
            shot_id = node.get("shot_id")
            if role == "selection":
                selections_by_shot.setdefault(shot_id, []).append(node.get("id"))
            elif role == "video_candidate":
                videos_by_shot.setdefault(shot_id, []).append(node.get("id"))
        existing_pairs = {
            (edge.get("source"), edge.get("target"))
            for edge in new_edges
            if isinstance(edge, dict)
        }
        for shot_id, videos in videos_by_shot.items():
            for selection_id in selections_by_shot.get(shot_id, []):
                for video_id in videos:
                    if (video_id, selection_id) not in existing_pairs:
                        new_edges.append({"source": video_id, "target": selection_id, "purpose": "candidate_input"})
                        existing_pairs.add((video_id, selection_id))
        result["edges"] = new_edges

    groups = result.get("groups")
    if isinstance(groups, list):
        new_groups = []
        for group in groups:
            if not isinstance(group, dict):
                new_groups.append(group)
                continue
            node_ids = group.get("node_ids")
            if isinstance(node_ids, list):
                group = copy.deepcopy(group)
                group["node_ids"] = [nid for nid in node_ids if nid in remaining_ids]
                if group["node_ids"]:
                    new_groups.append(group)
            else:
                new_groups.append(group)
        result["groups"] = new_groups

    shots = result.get("shots")
    if isinstance(shots, list):
        new_shots = []
        for shot in shots:
            if not isinstance(shot, dict):
                new_shots.append(shot)
                continue
            shot = copy.deepcopy(shot)
            for key in ("roles", "required_roles"):
                value = shot.get(key)
                if isinstance(value, list):
                    shot[key] = [role for role in value if role != "assembly"]
            new_shots.append(shot)
        result["shots"] = new_shots

    policy = result.get("policy")
    if not isinstance(policy, dict):
        policy = {}
        result["policy"] = policy
    link_grammar = policy.get("link_grammar")
    if not isinstance(link_grammar, dict):
        link_grammar = {}
        policy["link_grammar"] = link_grammar
    existing_terminal = set(link_grammar.get("terminal_nodes") or [])
    link_grammar["terminal_nodes"] = sorted(task_terminal_roles(contract, existing_terminal))
    return result


def task_profile_failures(contract: dict, graph: dict) -> list[dict]:
    failures = []
    try:
        task_type = task_type_for(contract)
    except (TypeError, ValueError):
        failures.append({"code": "INVALID_TASK_TYPE", "task_type": contract.get("task_type") if isinstance(contract, dict) else None})
        return failures
    if not isinstance(graph, dict):
        graph = {}
    deliverable = contract.get("deliverable") if isinstance(contract, dict) else None
    if deliverable == "mirror":
        return failures
    if task_type not in EARLY_STOP_TASK_TYPES:
        return failures

    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        nodes = []
    if any(isinstance(node, dict) and node.get("role") in FORBIDDEN_EARLY_ROLES for node in nodes):
        failures.append({"code": "TASK_STAGE_EXCEEDED"})

    selections_by_shot = {}
    videos_by_shot = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        role = node.get("role")
        shot_id = node.get("shot_id")
        if role == "selection":
            selections_by_shot.setdefault(shot_id, []).append(node.get("id"))
        elif role == "video_candidate":
            videos_by_shot.setdefault(shot_id, []).append(node.get("id"))

    edge_set = set()
    edges = graph.get("edges")
    if isinstance(edges, list):
        for edge in edges:
            if isinstance(edge, dict):
                edge_set.add((edge.get("source"), edge.get("target")))

    for shot_id, videos in videos_by_shot.items():
        for selection_id in selections_by_shot.get(shot_id, []):
            for video_id in videos:
                if (video_id, selection_id) not in edge_set:
                    failures.append(
                        {
                            "code": "TASK_SELECTION_INPUT_MISSING",
                            "shot_id": shot_id,
                            "video_node_id": video_id,
                            "selection_node_id": selection_id,
                        }
                    )
    return failures


def task_profile_result(contract: dict, regression: dict) -> dict:
    try:
        task_type = task_type_for(contract if isinstance(contract, dict) else {})
    except (TypeError, ValueError):
        task_type = contract.get("task_type") if isinstance(contract, dict) else "full_film"
        if not isinstance(task_type, str):
            task_type = "full_film"
    deliverable = contract.get("deliverable") if isinstance(contract, dict) else None
    if deliverable == "mirror":
        target_state = "graph_plan_ready"
    elif task_type == "prompt_only":
        target_state = "graph_plan_ready"
    elif task_type == "single_shot":
        target_state = "prompt_package_ready"
    else:
        target_state = "delivered"
    if not isinstance(regression, dict):
        regression = {}
    compiler_state = regression.get("status")
    if compiler_state not in ("PASS", "DRAFT", "FAIL"):
        compiler_state = "DRAFT"
    return {
        "task_type": task_type,
        "target_state": target_state,
        "compiler_state": compiler_state,
        "production_complete": False,
    }