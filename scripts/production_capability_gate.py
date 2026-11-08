"""Gate a compiled production plan for production capability.

This is intentionally role-based. It does not demand a magic node count;
it fails plans that cannot carry assets, candidates, selection, sound and
assembly through to a runnable production graph.
"""

from __future__ import annotations

import math

from collections import Counter, defaultdict
from typing import Any

try:
    from scripts.compile_asset_graph import expand_entity_versions, _requires_iteration
    from scripts.reverse_contract import mode_errors, normalize_mode
    from scripts.compile_prompt_packages import REQUIRED_BLOCKS as PROMPT_REQUIRED_BLOCKS
    from scripts.compile_prompt_packages import _block_has_content as _prompt_block_has_content
    from scripts.compile_shot_graph import resolve_shot_roles
    from scripts.production_task_profile import (
        task_profile_failures,
        task_roles,
        task_terminal_roles,
    )
    from scripts.production_timing import resolve_shot_timing
    from scripts.verify_delivery_semantics import verify_delivery
except ImportError:
    from compile_asset_graph import expand_entity_versions, _requires_iteration
    from reverse_contract import mode_errors, normalize_mode
    from compile_prompt_packages import REQUIRED_BLOCKS as PROMPT_REQUIRED_BLOCKS
    from compile_prompt_packages import _block_has_content as _prompt_block_has_content
    from compile_shot_graph import resolve_shot_roles
    from production_task_profile import (
        task_profile_failures,
        task_roles,
        task_terminal_roles,
    )
    from production_timing import resolve_shot_timing
    from verify_delivery_semantics import verify_delivery


REQUIRED_SHOT_ROLES = {
    "storyboard",
    "prompt",
    "scene_ref",
    "identity_ref",
    "composition_ref",
    "candidate_image",
    "refined_image",
    "video_candidate",
    "selection",
    "audio",
    "assembly",
}

MIRROR_MODES = ("source_replica", "copy_reverse")
MIRROR_DELIVERABLE = "mirror"
PLAN_DELIVERABLE = "production_plan"
SOURCE_LEVEL_CLAIMS = ("source_level", "original_level", "source_replica", "original_readback")


def _graph_integrity_failures(contract, assets, graph):
    """Return structured integrity failures for a production plan graph."""
    failures = []

    if not isinstance(contract, dict):
        contract = {}
    if not isinstance(assets, dict):
        assets = {}
    if not isinstance(graph, dict):
        graph = {}

    _nodes_raw = graph.get("nodes")
    nodes = _nodes_raw if isinstance(_nodes_raw, list) else []
    _edges_raw = graph.get("edges")
    edges = _edges_raw if isinstance(_edges_raw, list) else []
    node_ids = [node.get("id") if isinstance(node, dict) else None for node in nodes]

    invalid_node_ids = [nid for nid in node_ids if not (isinstance(nid, str) and nid.strip())]
    if invalid_node_ids:
        failures.append({"code": "INVALID_NODE_ID", "ids": invalid_node_ids})

    valid_node_ids = [nid for nid in node_ids if isinstance(nid, str) and nid.strip()]
    duplicate_node_ids = [nid for nid, count in Counter(valid_node_ids).items() if count > 1]
    if duplicate_node_ids:
        failures.append({"code": "DUPLICATE_NODE_ID", "ids": duplicate_node_ids})

    contract_shots = contract.get("shots") or []
    shot_ids = [shot.get("id") if isinstance(shot, dict) else None for shot in contract_shots]
    invalid_shot_ids = [sid for sid in shot_ids if not (isinstance(sid, str) and sid.strip())]
    if invalid_shot_ids:
        failures.append({"code": "INVALID_SHOT_ID", "ids": invalid_shot_ids})
    valid_shot_ids = [sid for sid in shot_ids if isinstance(sid, str) and sid.strip()]
    duplicate_shot_ids = [sid for sid, count in Counter(valid_shot_ids).items() if count > 1]
    if duplicate_shot_ids:
        failures.append({"code": "DUPLICATE_SHOT_ID", "ids": duplicate_shot_ids})

    contract_entities = contract.get("entities") or []
    entity_ids = [entity.get("id") if isinstance(entity, dict) else None for entity in contract_entities]
    invalid_entity_ids = [eid for eid in entity_ids if not (isinstance(eid, str) and eid.strip())]
    if invalid_entity_ids:
        failures.append({"code": "INVALID_ENTITY_ID", "ids": invalid_entity_ids})
    valid_entity_ids = [eid for eid in entity_ids if isinstance(eid, str) and eid.strip()]
    duplicate_entity_ids = [eid for eid, count in Counter(valid_entity_ids).items() if count > 1]
    if duplicate_entity_ids:
        failures.append({"code": "DUPLICATE_ENTITY_ID", "ids": duplicate_entity_ids})

    existing_node_ids = {nid for nid in node_ids if isinstance(nid, str)}
    bad_endpoints = []
    for edge in edges:
        if not isinstance(edge, dict):
            bad_endpoints.append(None)
            continue
        source = edge.get("source")
        target = edge.get("target")
        if not (isinstance(source, str) and source in existing_node_ids):
            bad_endpoints.append(source)
        if not (isinstance(target, str) and target in existing_node_ids):
            bad_endpoints.append(target)
    # de-duplicate while preserving order
    deduped_bad = []
    for value in bad_endpoints:
        if value not in deduped_bad:
            deduped_bad.append(value)
    if deduped_bad:
        failures.append({"code": "DANGLING_EDGE", "ids": deduped_bad})

    # Iterative Kahn DAG validation (cycles + self loops).
    node_list = list(node_ids)
    adjacency = {nid: [] for nid in node_list if isinstance(nid, str)}
    in_degree = {nid: 0 for nid in node_list if isinstance(nid, str)}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if not (isinstance(source, str) and isinstance(target, str)):
            continue
        if source not in in_degree or target not in in_degree:
            continue
        adjacency.setdefault(source, []).append(target)
        in_degree[target] = in_degree.get(target, 0) + 1
    # ensure all nodes present
    for nid in node_list:
        if isinstance(nid, str) and nid not in in_degree:
            in_degree[nid] = 0
            adjacency[nid] = adjacency.get(nid, [])
    queue = [nid for nid, degree in in_degree.items() if degree == 0]
    from collections import deque
    dq = deque(queue)
    processed = 0
    while dq:
        current = dq.popleft()
        processed += 1
        for neighbor in adjacency.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                dq.append(neighbor)
    remaining = [nid for nid, degree in in_degree.items() if degree > 0]
    if remaining:
        failures.append({"code": "GRAPH_CYCLE", "ids": remaining})

    return failures


def _contract_coverage_failures(contract, assets, graph):
    failures = []
    if not isinstance(contract, dict):
        contract = {}
    if not isinstance(assets, dict):
        assets = {}
    if not isinstance(graph, dict):
        graph = {}
    _nodes_raw = graph.get("nodes")
    nodes = _nodes_raw if isinstance(_nodes_raw, list) else []
    _graph_shots_raw = graph.get("shots")
    graph_shots = _graph_shots_raw if isinstance(_graph_shots_raw, list) else []

    # Contract-to-artifact coverage (production plans only; mirror/skeleton skip this function).
    contract_shots = contract.get("shots") or []
    if not isinstance(contract_shots, list):
        contract_shots = []
    try:
        contract_entities = expand_entity_versions(contract)
    except (TypeError, ValueError) as exc:
        return [{"code": "ASSET_HISTORY_INVALID", "message": str(exc)}]
    if not isinstance(contract_entities, list):
        contract_entities = []

    valid_contract_shot_ids = [sid for sid in (s.get("id") if isinstance(s, dict) else None for s in contract_shots) if isinstance(sid, str) and sid.strip()]
    valid_contract_entity_ids = [eid for eid in (e.get("id") if isinstance(e, dict) else None for e in contract_entities) if isinstance(eid, str) and eid.strip()]

    # Empty production graph.
    if not nodes and not graph_shots:
        failures.append({"code": "EMPTY_PRODUCTION_GRAPH"})

    # Graph shot id validation and exact coverage.
    graph_shot_ids = []
    for gshot in graph_shots:
        if isinstance(gshot, dict):
            graph_shot_ids.append(gshot.get("id"))
        else:
            graph_shot_ids.append(None)
    invalid_graph_shot_ids = [sid for sid in graph_shot_ids if not (isinstance(sid, str) and str(sid).strip())]
    if invalid_graph_shot_ids:
        failures.append({"code": "INVALID_GRAPH_SHOT_ID", "ids": invalid_graph_shot_ids})
    valid_graph_shot_ids = [sid for sid in graph_shot_ids if isinstance(sid, str) and sid.strip()]
    duplicate_graph_shot_ids = [sid for sid, count in Counter(valid_graph_shot_ids).items() if count > 1]
    if duplicate_graph_shot_ids:
        failures.append({"code": "DUPLICATE_GRAPH_SHOT_ID", "ids": duplicate_graph_shot_ids})
    valid_graph_shot_set = set(valid_graph_shot_ids)
    valid_contract_shot_set = set(valid_contract_shot_ids)
    missing_graph_shots = sorted(valid_contract_shot_set - valid_graph_shot_set)
    if missing_graph_shots:
        failures.append({"code": "MISSING_GRAPH_SHOT", "ids": missing_graph_shots})
    extra_graph_shots = sorted(valid_graph_shot_set - valid_contract_shot_set)
    if extra_graph_shots:
        failures.append({"code": "EXTRA_GRAPH_SHOT", "ids": extra_graph_shots})

    # Asset coverage: asset ids must exactly match contract entity ids.
    asset_list = assets.get("assets") or []
    if not isinstance(asset_list, list):
        asset_list = []
    asset_ids = []
    for asset in asset_list:
        if isinstance(asset, dict):
            asset_ids.append(asset.get("id"))
        else:
            asset_ids.append(None)
    invalid_asset_ids = [aid for aid in asset_ids if not (isinstance(aid, str) and str(aid).strip())]
    if invalid_asset_ids:
        failures.append({"code": "INVALID_ASSET_ID", "ids": invalid_asset_ids})
    valid_asset_ids = [aid for aid in asset_ids if isinstance(aid, str) and aid.strip()]
    duplicate_asset_ids = [aid for aid, count in Counter(valid_asset_ids).items() if count > 1]
    if duplicate_asset_ids:
        failures.append({"code": "DUPLICATE_ASSET_ID", "ids": duplicate_asset_ids})
    valid_asset_set = set(valid_asset_ids)
    valid_entity_set = set(valid_contract_entity_ids)
    missing_assets = sorted(valid_entity_set - valid_asset_set)
    if missing_assets:
        failures.append({"code": "MISSING_ASSET_FOR_ENTITY", "ids": missing_assets})
    extra_assets = sorted(valid_asset_set - valid_entity_set)
    if extra_assets:
        failures.append({"code": "EXTRA_ASSET", "ids": extra_assets})

    # Historical definitions and activation are derived from the authoritative input.
    expected_assets = {e["id"]: e for e in contract_entities if isinstance(e,dict) and "id" in e}
    versioned = any("base_entity_id" in e for e in expected_assets.values())
    for asset in asset_list:
        if not isinstance(asset,dict):
            continue
        expected = expected_assets.get(asset.get("id"),{})
        if "base_entity_id" in expected and any(asset.get(k)!=expected.get(k) for k in
                ("base_entity_id","definition","active","version","description","state")):
            failures.append({"code":"ASSET_VERSION_METADATA_MISMATCH","asset_id":asset.get("id")})
    if versioned:
        by_reference = {(e.get("base_entity_id",e["id"]),e.get("version",1)):e for e in expected_assets.values()}
        node_by_id = {n.get("id"):n for n in nodes if isinstance(n,dict)}
        shots_by_id = {s["id"]:s for s in contract_shots if isinstance(s,dict) and "id" in s}
        for node in nodes:
            if not isinstance(node,dict) or node.get("role")!="candidate_image":
                continue
            raw_shot = shots_by_id.get(node.get("shot_id"),{})
            expected_sources = []
            for ref in raw_shot.get("asset_refs",[]):
                entity = by_reference[(ref["entity_id"],ref["version"])]
                expected_sources.append(entity["id"]+("__asset_refine_b" if _requires_iteration(entity)[0] else "__asset_anchor"))
            actual_sources = [e.get("source") for e in graph.get("edges") or [] if e.get("target")==node.get("id") and
                node_by_id.get(e.get("source"),{}).get("role") in ("asset_anchor","asset_refine")]
            if actual_sources!=expected_sources:
                failures.append({"code":"ASSET_VERSION_REFERENCE_MISMATCH","node_id":node.get("id"),
                                 "expected":expected_sources,"actual":actual_sources})

    # Foreign node references.
    foreign_shot_refs = []
    foreign_entity_refs = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        sid = node.get("shot_id")
        if sid not in (None, ""):
            if not (isinstance(sid, str) and sid.strip() and sid in valid_contract_shot_set):
                if sid not in foreign_shot_refs:
                    foreign_shot_refs.append(sid)
        eid = node.get("entity_id")
        if eid not in (None, ""):
            if not (isinstance(eid, str) and eid.strip() and eid in valid_entity_set):
                if eid not in foreign_entity_refs:
                    foreign_entity_refs.append(eid)
    if foreign_shot_refs:
        failures.append({"code": "FOREIGN_SHOT_REFERENCE", "ids": foreign_shot_refs})
    if foreign_entity_refs:
        failures.append({"code": "FOREIGN_ENTITY_REFERENCE", "ids": foreign_entity_refs})

    # Authoritative shot role coverage from contract + compiler resolver.
    by_shot: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        sid = node.get("shot_id")
        if sid not in (None, ""):
            by_shot[str(sid)].add(node.get("role"))
    processed_shot_ids: set[str] = set()
    for shot in contract_shots:
        if not isinstance(shot, dict):
            continue
        sid = shot.get("id")
        if not (isinstance(sid, str) and sid.strip()):
            continue
        processed_shot_ids.add(sid)
        try:
            expected_roles = set(task_roles(contract, resolve_shot_roles(shot)))
        except (TypeError, ValueError, AttributeError):
            failures.append({"code": "INVALID_SHOT_ROLES", "shot_id": sid})
            continue
        actual_roles = by_shot.get(sid, set())
        missing_roles = sorted(expected_roles - actual_roles)
        if missing_roles:
            failures.append({"code": "MISSING_SHOT_ROLE", "shot_id": sid, "missing": missing_roles})

    # Role coverage for graph-declared shots not present in contract (foreign/extra).
    for gshot in graph_shots:
        if not isinstance(gshot, dict):
            continue
        sid = gshot.get("id")
        if not (isinstance(sid, str) and sid.strip()):
            continue
        if sid in processed_shot_ids:
            continue
        processed_shot_ids.add(sid)
        try:
            expected_roles = set(task_roles(contract, resolve_shot_roles(gshot)))
        except (TypeError, ValueError, AttributeError):
            failures.append({"code": "INVALID_SHOT_ROLES", "shot_id": sid})
            continue
        actual_roles = by_shot.get(sid, set())
        missing_roles = sorted(expected_roles - actual_roles)
        if missing_roles:
            failures.append({"code": "MISSING_SHOT_ROLE", "shot_id": sid, "missing": missing_roles})

    # Asset aspect-ratio coverage: derive expected ratios from contract entities,
    # never trust audited metadata alone.
    project_ratio = contract.get("aspect_ratio") if isinstance(contract, dict) else None
    if not project_ratio:
        project_ratio = "16:9"
    project_ratio = str(project_ratio)

    def _valid_ratio(value: Any) -> bool:
        if not isinstance(value, str) or not value:
            return False
        parts = value.split(":")
        if len(parts) != 2:
            return False
        left, right = parts
        if not left or not right:
            return False
        if any(ch not in "0123456789" for ch in left + right):
            return False
        try:
            width = int(left)
            height = int(right)
        except ValueError:
            return False
        return width > 0 and height > 0

    entity_by_id: dict[str, dict[str, Any]] = {}
    for entity in contract_entities:
        if isinstance(entity, dict):
            eid = entity.get("id")
            if isinstance(eid, str) and eid.strip():
                entity_by_id[eid] = entity

    expected_by_entity: dict[str, tuple[Any, ...]] = {}
    for eid in valid_contract_entity_ids:
        entity = entity_by_id.get(eid)
        explicit = isinstance(entity, dict) and "aspect_ratio" in entity
        raw_ratio = entity.get("aspect_ratio") if isinstance(entity, dict) else None
        if explicit:
            if not _valid_ratio(raw_ratio):
                for code in ("INVALID_ENTITY_ASPECT_RATIO", "INVALID_ASSET_RATIO", "INVALID_ASPECT_RATIO"):
                    failures.append({"code": code, "entity_id": eid, "value": raw_ratio})
                expected_by_entity[eid] = (None, None, explicit, raw_ratio)
                continue
            expected_by_entity[eid] = (str(raw_ratio), "entity", explicit, raw_ratio)
        else:
            expected_by_entity[eid] = (project_ratio, "project_default", explicit, raw_ratio)

    for asset in asset_list:
        if not isinstance(asset, dict):
            continue
        aid = asset.get("id")
        if not (isinstance(aid, str) and aid.strip()):
            continue
        info = expected_by_entity.get(aid)
        if info is None:
            continue
        expected_ratio, expected_source, explicit, raw_ratio = info
        if expected_ratio is None:
            continue
        ar = asset.get("aspect_ratio")
        src = asset.get("aspect_ratio_source")
        metadata_ok = (
            _valid_ratio(ar)
            and ar == expected_ratio
            and src == expected_source
            and src in ("entity", "project_default")
        )
        if not metadata_ok:
            for code in ("ASSET_RATIO_METADATA_MISMATCH", "ASSET_RATIO_MISMATCH", "MISSING_ASSET_RATIO", "ASSET_PLAN_RATIO_MISMATCH"):
                failures.append(
                    {
                        "code": code,
                        "asset_id": aid,
                        "expected": expected_ratio,
                        "actual": ar,
                        "source": src,
                    }
                )

    for node in nodes:
        if not isinstance(node, dict):
            continue
        eid = node.get("entity_id")
        if not (isinstance(eid, str) and eid.strip() and eid in expected_by_entity):
            continue
        role = node.get("role")
        if role not in ("asset_anchor", "asset_refine"):
            continue
        expected_ratio, expected_source, explicit, raw_ratio = expected_by_entity[eid]
        if expected_ratio is None:
            continue
        settings = node.get("settings")
        settings_is_dict = isinstance(settings, dict)
        actual = settings.get("ratio") if settings_is_dict else None
        node_ok = (
            settings_is_dict
            and "ratio" in settings
            and _valid_ratio(actual)
            and actual == expected_ratio
        )
        if not node_ok:
            for code in ("RATIO_MISMATCH", "ASSET_NODE_RATIO_MISMATCH", "ASSET_RATIO_MISMATCH"):
                failures.append(
                    {
                        "code": code,
                        "node_id": node.get("id"),
                        "expected": expected_ratio,
                        "actual": actual,
                    }
                )

    return failures


def evaluate(
    contract: dict[str, Any],
    assets: dict[str, Any],
    graph: dict[str, Any],
    prompts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return PASS/FAIL plus machine-readable failures and warnings."""

    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(contract, dict):
        contract = {}
    if not isinstance(assets, dict):
        assets = {}
    if not isinstance(graph, dict):
        graph = {}
    if not isinstance(prompts, list):
        prompts = []
    failures.extend(task_profile_failures(contract, graph))
    mode, mode_warnings = normalize_mode(contract.get("mode") or contract.get("production_mode"), "production_build")
    for item in mode_warnings:
        warnings.append({"code": item})
    for error in mode_errors(contract):
        failures.append({"code": error})

    deliverable = contract.get("deliverable")
    if deliverable not in (MIRROR_DELIVERABLE, PLAN_DELIVERABLE):
        if mode in MIRROR_MODES:
            failures.append(
                {
                    "code": "DELIVERABLE_UNDECLARED",
                    "mode": mode,
                    "message": "%s 必须声明 deliverable: mirror 或 production_plan；未声明时不默认走生产计划路径。" % mode,
                }
            )
        deliverable = PLAN_DELIVERABLE
    if deliverable == MIRROR_DELIVERABLE:
        if not contract.get("source_graph_path"):
            failures.append(
                {
                    "code": "MIRROR_SOURCE_GRAPH_MISSING",
                    "message": "mirror 必须给出 source_graph_path，否则无从建立也不无从核验 source_node_id 血缘。",
                }
            )
        mirror_nodes = graph.get("nodes") or []
        if not mirror_nodes:
            failures.append({"code": "MIRROR_GRAPH_EMPTY"})
        unlinked = [node.get("id") for node in mirror_nodes if not node.get("source_node_id")]
        if unlinked:
            failures.append(
                {
                    "code": "MIRROR_LINEAGE_MISSING",
                    "count": len(unlinked),
                    "sample": unlinked[:10],
                    "message": "mirror 图里每个节点都必须带 source_node_id 指向源节点。",
                }
            )
    else:
        claim = str(contract.get("fidelity_claim") or "")
        if claim in SOURCE_LEVEL_CLAIMS:
            failures.append(
                {
                    "code": "FIDELITY_CLAIM_NOT_AUTHORIZED",
                    "fidelity_claim": claim,
                    "deliverable": deliverable,
                    "message": "production_plan 不得声明源级忠实；源级忠实只能由 mirror + source_fidelity_lint 证明。",
                }
            )

    fatal_failures = []
    coverage_failures = []
    integrity_skipped = False
    if deliverable == MIRROR_DELIVERABLE:
        integrity_skipped = True
        warnings.append(
            {
                "code": "MIRROR_GRAPH_INTEGRITY_SKIPPED",
                "message": "mirror 跳过生产图完整性门禁；仅由 source fidelity 核验。",
            }
        )
    elif mode == "content_reverse" and contract.get("skeleton_only"):
        integrity_skipped = True
    else:
        try:
            fatal_failures = _graph_integrity_failures(contract, assets, graph)
        except Exception as exc:  # pragma: no cover - defensive
            fatal_failures = [{"code": "CONTRACT_COVERAGE_ERROR", "message": str(exc)}]

    if fatal_failures:
        failures.extend(fatal_failures)
        return {
            "status": "FAIL",
            "mode": mode,
            "failures": failures,
            "warnings": warnings,
            "checks": {
                "deliverable_declared": deliverable in (MIRROR_DELIVERABLE, PLAN_DELIVERABLE),
                "mirror_lineage": not any(f.get("code") == "MIRROR_LINEAGE_MISSING" for f in failures),
                "fidelity_claim_authorized": not any(f.get("code") == "FIDELITY_CLAIM_NOT_AUTHORIZED" for f in failures),
                "shot_role_coverage": None,
                "asset_iteration": None,
                "link_downstream": None,
                "prompt_packages": None,
                "no_ignition": None,
                "graph_integrity": False,
                "graph_integrity_skipped": False,
            },
        }

    if not integrity_skipped and deliverable != MIRROR_DELIVERABLE:
        coverage_failures = _contract_coverage_failures(contract, assets, graph)
        failures.extend(coverage_failures)

    out_degree: dict[str, int] = defaultdict(int)
    in_degree: dict[str, int] = defaultdict(int)
    for edge in graph.get("edges") or []:
        out_degree[edge.get("source")] += 1
        in_degree[edge.get("target")] += 1
    existing_terminal_roles = set((graph.get("policy") or {}).get("link_grammar", {}).get("terminal_nodes", ["final_composite", "qa"]))
    terminal_roles = task_terminal_roles(contract, existing_terminal_roles)

    if deliverable == MIRROR_DELIVERABLE:
        warnings.append(
            {
                "code": "MIRROR_SKIPS_PRODUCTION_ROLES",
                "message": "mirror 只验结构忠实（source_fidelity_lint），不按生产角色门禁检查。",
            }
        )
    elif mode == "content_reverse" and contract.get("skeleton_only"):
        warnings.append(
            {
                "code": "SKELETON_ONLY",
                "message": "film_reverse skeleton is allowed, but it is not a production build.",
            }
        )
    else:
        for asset in assets.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            if asset.get("requires_iteration") and not asset.get("exemption_reason"):
                entity_id = asset.get("id")
                chain = next(
                    (c for c in assets.get("iteration_chains") or [] if c.get("entity_id") == entity_id),
                    None,
                )
                if not chain or len(chain.get("edges") or []) < 2:
                    failures.append(
                        {
                            "code": "MISSING_ASSET_ITERATION",
                            "entity_id": entity_id,
                            "message": "reused/stateful asset must have an anchor->refine_a->refine_b chain or explicit exemption.",
                        }
                    )
        asset_ids = {asset.get("id") for asset in assets.get("assets") or [] if isinstance(asset, dict) and asset.get("active", True)}
        asset_outgoing: dict[str, int] = defaultdict(int)
        for edge in graph.get("edges") or []:
            source = edge.get("source") or ""
            for asset_id in asset_ids:
                if source.startswith(f"{asset_id}__asset_"):
                    asset_outgoing[asset_id] += 1
        for asset_id in asset_ids:
            if asset_outgoing.get(asset_id, 0) == 0:
                failures.append(
                    {
                        "code": "MISSING_ASSET_TO_SHOT_LINK",
                        "entity_id": asset_id,
                        "message": "asset chain must link into shot candidate/reference nodes.",
                    }
                )
        for node in graph.get("nodes") or []:
            role = node.get("role")
            if role in terminal_roles or node.get("node_type") == "group":
                continue
            node_id = node.get("id")
            if out_degree.get(node_id, 0) == 0:
                failures.append(
                    {
                        "code": "LINK_NO_DOWNSTREAM",
                        "node_id": node_id,
                        "role": role,
                        "message": "non-terminal node must continue into downstream nodes.",
                    }
                )
            if in_degree.get(node_id, 0) == 0 and out_degree.get(node_id, 0) == 0:
                failures.append(
                    {"code": "LINK_ISOLATED", "node_id": node_id, "role": role}
                )

        prompt_by_node = {p.get("node_id"): p for p in prompts}
        for node in graph.get("nodes") or []:
            role = node.get("role")
            if role not in REQUIRED_SHOT_ROLES and role not in PROMPT_REQUIRED_BLOCKS:
                continue
            package = prompt_by_node.get(node.get("id"))
            if not package:
                failures.append({"code": "MISSING_PROMPT_PACKAGE", "node_id": node.get("id")})
                continue
            if package.get("missing_blocks"):
                failures.append(
                    {
                        "code": "PROMPT_BLOCKS_MISSING",
                        "node_id": node.get("id"),
                        "missing": package["missing_blocks"],
                    }
                )
            required = PROMPT_REQUIRED_BLOCKS.get(role, [])
            blocks = package.get("blocks") or {}
            empty_blocks = [
                name for name in required if name not in blocks or not _prompt_block_has_content(blocks.get(name))
            ]
            if empty_blocks:
                failures.append(
                    {
                        "code": "PROMPT_BLOCK_EMPTY",
                        "node_id": node.get("id"),
                        "missing": empty_blocks,
                    }
                )
            if package.get("unresolved"):
                failures.append(
                    {
                        "code": "PROMPT_UNRESOLVED",
                        "node_id": node.get("id"),
                        "unresolved": package["unresolved"],
                    }
                )
            if package.get("status") != "READY":
                failures.append(
                    {
                        "code": "PROMPT_NOT_READY",
                        "node_id": node.get("id"),
                        "status": package.get("status"),
                    }
                )
            if package.get("status") == "READY" and (
                package.get("missing_blocks") or package.get("unresolved") or empty_blocks
            ):
                failures.append(
                    {
                        "code": "PROMPT_STATUS_INCONSISTENT",
                        "node_id": node.get("id"),
                    }
                )

    if deliverable != MIRROR_DELIVERABLE:
        # Duration and cross-layer consistency checks.
        total_duration = contract.get("duration_sec")
        if isinstance(total_duration, bool) or not isinstance(total_duration, (int, float)) or not math.isfinite(total_duration) or total_duration <= 0:
            failures.append({"code": "INVALID_DURATION", "value": total_duration})
        contract_shots = contract.get("shots") or []
        if any(isinstance(s, dict) and s.get("duration_sec") is None for s in contract_shots):
            failures.append({"code": "SHOT_DURATION_MISSING"})
        for s in contract_shots:
            if not isinstance(s, dict):
                continue
            dur = s.get("duration_sec")
            if dur is None:
                continue
            if isinstance(dur, bool) or not isinstance(dur, (int, float)) or not math.isfinite(dur) or dur <= 0:
                failures.append({"code": "INVALID_SHOT_DURATION", "shot_id": s.get("id"), "value": dur})
        authoritative_timing = {}
        separate_timing_by_shot = {}
        for s in contract_shots:
            if not isinstance(s, dict):
                continue
            shot_id = s.get("id")
            key = str(shot_id) if shot_id is not None else None
            try:
                timing = resolve_shot_timing(s)
            except (ValueError, TypeError):
                failures.append({"code": "INVALID_SHOT_TIMING", "shot_id": shot_id})
                continue
            if key is not None:
                authoritative_timing[key] = timing
                separate_timing_by_shot[key] = bool(
                    timing.get("duration_sec") is not None
                    and (
                        timing.get("generation_duration_sec") != timing.get("duration_sec")
                        or timing.get("cut_range")
                        != {"start_sec": 0, "end_sec": timing.get("duration_sec")}
                    )
                )
        shot_durations = [s.get("duration_sec") for s in contract_shots if isinstance(s, dict) and s.get("duration_sec") is not None]
        if total_duration is not None and shot_durations and len(shot_durations) == len(contract_shots):
            shot_sum = sum(float(x) for x in shot_durations)
            if abs(shot_sum - float(total_duration)) > 1e-6:
                failures.append(
                    {
                        "code": "DURATION_TOTAL_MISMATCH",
                        "project_duration": total_duration,
                        "shot_duration_sum": shot_sum,
                    }
                )
        graph_shots = graph.get("shots") or []
        if any(isinstance(s, dict) and s.get("duration_sec") is None for s in graph_shots):
            failures.append({"code": "SHOT_DURATION_MISSING"})
        for s in graph_shots:
            if not isinstance(s, dict):
                continue
            dur = s.get("duration_sec")
            if dur is None:
                continue
            if isinstance(dur, bool) or not isinstance(dur, (int, float)) or not math.isfinite(dur) or dur <= 0:
                failures.append({"code": "INVALID_SHOT_DURATION", "shot_id": s.get("id"), "value": dur})
        graph_durations = [s.get("duration_sec") for s in graph_shots if isinstance(s, dict) and s.get("duration_sec") is not None]
        if total_duration is not None and graph_durations and len(graph_durations) == len(graph_shots):
            graph_sum = sum(float(x) for x in graph_durations)
            if abs(graph_sum - float(total_duration)) > 1e-6:
                failures.append(
                    {
                        "code": "DURATION_TOTAL_MISMATCH",
                        "project_duration": total_duration,
                        "shot_duration_sum": graph_sum,
                    }
                )

        for s in graph_shots:
            if not isinstance(s, dict):
                continue
            shot_id = s.get("id")
            key = str(shot_id) if shot_id is not None else None
            auth = authoritative_timing.get(key) if key is not None else None
            required = separate_timing_by_shot.get(key, False) if key is not None else False
            timing = s.get("shot_timing")
            if timing is None:
                if required:
                    failures.append({"code": "MISSING_SHOT_TIMING", "shot_id": shot_id})
                continue
            try:
                resolved = resolve_shot_timing(timing if isinstance(timing, dict) else {})
            except (ValueError, TypeError):
                failures.append({"code": "INVALID_SHOT_TIMING", "shot_id": shot_id})
                continue
            if auth is not None and resolved != auth:
                failures.append(
                    {
                        "code": "SHOT_TIMING_MISMATCH",
                        "shot_id": shot_id,
                        "expected": auth,
                        "actual": resolved,
                    }
                )
        shot_duration_by_id = {
            str(s.get("id")): s.get("duration_sec")
            for s in contract_shots
            if isinstance(s, dict) and s.get("id") is not None
        }
        aspect_ratio = contract.get("aspect_ratio")
        for node in graph.get("nodes") or []:
            if node.get("node_type") != "video":
                continue
            settings = node.get("settings") or {}
            shot_id = node.get("shot_id")
            if "duration" in settings:
                dur_val = settings.get("duration")
                if isinstance(dur_val, bool) or not isinstance(dur_val, (int, float)) or not math.isfinite(dur_val) or dur_val <= 0:
                    failures.append({"code": "DURATION_MISMATCH", "node_id": node.get("id"), "expected": None, "actual": dur_val})
            shot_dur = shot_duration_by_id.get(str(shot_id)) if shot_id is not None else None
            auth_timing = authoritative_timing.get(str(shot_id)) if shot_id is not None else None
            if node.get("role") == "video_candidate":
                expected_dur = auth_timing.get("generation_duration_sec") if isinstance(auth_timing, dict) else None
            else:
                expected_dur = shot_dur
            if "duration" in settings and expected_dur is not None:
                try:
                    if abs(float(settings.get("duration")) - float(expected_dur)) > 1e-6:
                        failures.append(
                            {
                                "code": "DURATION_MISMATCH",
                                "node_id": node.get("id"),
                                "expected": expected_dur,
                                "actual": settings.get("duration"),
                            }
                        )
                except (TypeError, ValueError):
                    failures.append(
                        {
                            "code": "DURATION_MISMATCH",
                            "node_id": node.get("id"),
                            "expected": expected_dur,
                            "actual": settings.get("duration"),
                        }
                    )
            if node.get("node_type") == "video" and node.get("role") == "video_candidate":
                required_timing = separate_timing_by_shot.get(str(shot_id), False) if shot_id is not None else False
                node_timing = node.get("shot_timing")
                if node_timing is None:
                    if required_timing:
                        failures.append(
                            {
                                "code": "MISSING_SHOT_TIMING",
                                "node_id": node.get("id"),
                                "shot_id": shot_id,
                            }
                        )
                else:
                    try:
                        resolved_timing = resolve_shot_timing(node_timing if isinstance(node_timing, dict) else {})
                    except (ValueError, TypeError):
                        failures.append(
                            {
                                "code": "INVALID_SHOT_TIMING",
                                "node_id": node.get("id"),
                                "shot_id": shot_id,
                            }
                        )
                        resolved_timing = None
                    if resolved_timing is not None and auth_timing is not None and resolved_timing != auth_timing:
                        failures.append(
                            {
                                "code": "SHOT_TIMING_MISMATCH",
                                "node_id": node.get("id"),
                                "shot_id": shot_id,
                                "expected": auth_timing,
                                "actual": resolved_timing,
                            }
                        )
                if "duration" not in settings and required_timing:
                    failures.append(
                        {
                            "code": "DURATION_MISMATCH",
                            "node_id": node.get("id"),
                            "expected": expected_dur,
                            "actual": None,
                        }
                    )
            if "ratio" in settings and aspect_ratio is not None:
                if settings.get("ratio") != aspect_ratio:
                    failures.append(
                        {
                            "code": "RATIO_MISMATCH",
                            "node_id": node.get("id"),
                            "expected": aspect_ratio,
                            "actual": settings.get("ratio"),
                        }
                    )
    delivery = contract.get("delivery") or {}
    if delivery.get("ignition_allowed") is True:
        failures.append(
            {
                "code": "IGNITION_NOT_AUTHORIZED_FOR_COMPILER",
                "message": "The compiler must not authorize ignition; generation requires a separate explicit approval.",
            }
        )

    if mode == "source_replica":
        if contract.get("source_access") != "original_readback":
            failures.append({"code": "SOURCE_ACCESS_NOT_ORIGINAL"})
        baseline = contract.get("source_baseline")
        if deliverable == MIRROR_DELIVERABLE:
            pass  # mirror 的基线就是 source_graph_path，由 source_fidelity_lint 逐节点核验
        elif not baseline:
            failures.append({"code": "SOURCE_BASELINE_MISSING"})
        else:
            source_nodes = int(baseline.get("node_total") or 0)
            plan_nodes = int(baseline.get("planned_node_total") or 0)
            if source_nodes and plan_nodes / source_nodes < 0.95:
                failures.append(
                    {
                        "code": "SOURCE_FIDELITY_TOO_LOW",
                        "source_nodes": source_nodes,
                        "plan_nodes": plan_nodes,
                        "minimum": 0.95,
                    }
                )

    if mode == "copy_reverse":
        if not contract.get("copy_project_uuid"):
            failures.append({"code": "COPY_UUID_MISSING"})
        if not contract.get("source_project_uuid"):
            failures.append({"code": "SOURCE_UUID_MISSING"})

    if mode == "content_reverse" and not contract.get("source_film"):
        failures.append({"code": "CONTENT_SOURCE_MISSING"})

    # --- delivery semantics: the delivered text must honour the constraints ---
    # Only contracts that carry judgeable semantics are checked. A legacy
    # contract without semantics is reported as unverified, never as a pass.
    semantic_failures: list[dict[str, Any]] = []
    semantic_status = None
    judgeable = [
        item
        for item in (contract.get("constraints") or [])
        if isinstance(item, dict)
        and item.get("delivery", "prompt") == "prompt"
        and item.get("semantics")
    ]
    if judgeable:
        verification = verify_delivery(contract, prompts, graph, None)
        semantic_status = verification["status"]
        for failure in verification["failures"]:
            semantic_failures.append(
                {
                    "code": failure.get("code"),
                    "constraint_id": failure.get("constraint_id"),
                    "role": failure.get("role"),
                    "node_id": failure.get("node_id"),
                    "shot_id": failure.get("shot_id"),
                    "message": failure.get("message")
                    or "交付正文未兑现该约束。",
                }
            )
        if semantic_failures:
            failures.extend(semantic_failures)
        elif semantic_status != "PASS":
            warnings.append(
                {
                    "code": "DELIVERY_SEMANTICS_UNVERIFIED",
                    "message": "部分约束没有可判定的语义标记，只能标未验证。",
                }
            )

    return {
        "status": "FAIL" if failures else "PASS",
        "mode": mode,
        "failures": failures,
        "warnings": warnings,
        "checks": {
            "deliverable_declared": deliverable in (MIRROR_DELIVERABLE, PLAN_DELIVERABLE),
            "mirror_lineage": not any(f["code"] == "MIRROR_LINEAGE_MISSING" for f in failures),
            "fidelity_claim_authorized": not any(f["code"] == "FIDELITY_CLAIM_NOT_AUTHORIZED" for f in failures),
            "shot_role_coverage": not any(f["code"] == "MISSING_SHOT_ROLE" for f in failures),
            "asset_iteration": not any(f["code"] == "MISSING_ASSET_ITERATION" for f in failures),
            "link_downstream": not any(f["code"].startswith("LINK_") for f in failures),
            "prompt_packages": not any(
                f["code"].startswith("PROMPT_")
                or f["code"] == "MISSING_PROMPT_PACKAGE"
                or f["code"] in {"PROMPT_BLOCK_EMPTY", "PROMPT_UNRESOLVED", "PROMPT_STATUS_INCONSISTENT"}
                for f in failures
            ),
            "delivery_semantics": semantic_status,
            "no_ignition": not any(f["code"] == "IGNITION_NOT_AUTHORIZED_FOR_COMPILER" for f in failures),
            "graph_integrity": None if integrity_skipped else True,
            "graph_integrity_skipped": integrity_skipped,
        },
    }


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("assets")
    parser.add_argument("graph")
    parser.add_argument("prompts")
    parser.add_argument("--out")
    args = parser.parse_args()
    with open(args.contract, "r", encoding="utf-8") as handle:
        contract_payload = json.load(handle)
    with open(args.assets, "r", encoding="utf-8") as handle:
        assets = json.load(handle)
    with open(args.graph, "r", encoding="utf-8") as handle:
        graph = json.load(handle)
    with open(args.prompts, "r", encoding="utf-8") as handle:
        prompts = [json.loads(line) for line in handle if line.strip()]
    contract = contract_payload.get("production_contract", contract_payload)
    result = evaluate(contract, assets, graph, prompts)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
