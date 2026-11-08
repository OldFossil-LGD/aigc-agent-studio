"""compile_graph_plan.py - adapt the production compiler's shot graph into the
frozen A-path Graph Plan schema (outputs/统一基准/graph_plan.schema.json).

Why this exists: `compile_shot_graph.py` emits its own role vocabulary
(`asset_refine` / `candidate_image` / `selection` / ...) and its own edge
purposes, so its plan is rejected by `scripts/graph_plan_lint.py`
(measured: 1155 structure + 730 reference failures). This adapter maps it onto
the 9-role / 4-edge-kind vocabulary so the frozen gate can validate the graph
before anything is built on the canvas.

Key mapping decision: text->text edges (storyboard->prompt, selection->ledger,
ledger->qa) become `dependency`, which by contract does **not** become a
platform edge. That also removes the text-node edges that no real canvas uses.

Read-only. Emits one JSON file; never talks to LibTV.

Usage:
  python compile_graph_plan.py <03_shot_graph_plan.json> --out graph_plan.json
                               [--project-id UUID] [--profile generic]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROLE_MAP = {
    "asset_anchor": "asset",
    "asset_refine": "asset",
    "scene_ref": "asset",
    "identity_ref": "asset",
    "composition_ref": "asset",
    "state_ref": "asset",
    "candidate_image": "asset",
    "refined_image": "asset",
    "storyboard": "storyboard",
    "prompt": "source",
    "video_candidate": "shot",
    "selection": "source",
    "audio": "audio",
    "assembly": "composite",
    "asset_manifest": "source",
    "production_ledger": "source",
    "final_composite": "composite",
    "qa": "qa",
    "group": "group",
}

# text -> text stays a planning dependency, never a platform edge
TEXT_ROLES = {"source", "qa", "storyboard"}

DERIVED_FIELDS = [
    "imageList",
    "videoList",
    "audioList",
    "imageListOrder",
    "videoListOrder",
    "audioListOrder",
    "mixedListOrder",
    "status",
    "taskInfo",
    "prevTaskInfo",
    "resourceMeta",
]

GROUP_ROLE_BY_PREFIX = {
    "group__assets": "assets",
    "group__global": "source",
}


def group_role(name: str) -> str:
    if name.startswith("group__assets") or "资产" in name:
        return "assets"
    if name.startswith("group__global") or "全局" in name or "契约" in name:
        return "source"
    if "生产批次" in name or name.startswith("group__shot_"):
        return "shots"
    return "source"


def edge_kind(source_role: str, target_role: str) -> str:
    if target_role == "composite":
        return "assembly"
    if source_role in TEXT_ROLES and target_role in TEXT_ROLES:
        return "dependency"
    return "reference"


def convert(graph: dict, project_id: str, profile: str) -> dict:
    version = graph.get("version", 1)
    if type(version) is not int or version < 1:
        raise ValueError("graph version must be a positive integer")
    node_group_role: dict[str, str] = {}
    for g in graph.get("groups", []):
        role = group_role(g.get("name", ""))
        for nid in g.get("node_ids", []):
            node_group_role[nid] = role

    nodes = []
    roles: dict[str, str] = {}
    for n in graph.get("nodes", []):
        node_version = n.get("version", 1)
        if type(node_version) is not int or node_version < 1:
            raise ValueError("node version must be a positive integer")
        raw_role = n.get("role") or "other"
        role = ROLE_MAP.get(raw_role, "source")
        roles[n["id"]] = role
        nodes.append(
            {
                "node_id": n["id"],
                "node_type": n.get("node_type", "text"),
                "role": role,
                "group_role": node_group_role.get(n["id"]),
                "source_record_id": n.get("source_record_id") or n.get("shot_id"),
                "version": node_version,
                "derived_fields": [],
            }
        )

    edges = []
    next_order: dict[str, int] = {}
    for e in graph.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s not in roles or t not in roles:
            raise SystemExit(f"edge endpoint missing from nodes: {s} -> {t}")
        kind = edge_kind(roles[s], roles[t])
        row = {"source_id": s, "target_id": t, "kind": kind}
        if kind in ("reference", "assembly"):
            row["order"] = next_order.get(t, 0)
            next_order[t] = row["order"] + 1
            row["authority_layer"] = "edge"
        else:
            row["order"] = None
            row["authority_layer"] = "prompt"
        edges.append(row)

    groups = []
    for g in graph.get("groups", []):
        groups.append(
            {
                "group_id": g["id"],
                "group_role": group_role(g.get("name", "")),
                "node_ids": list(dict.fromkeys(g.get("node_ids", []))),
                "parent_group_id": None,
            }
        )

    return {
        "plan_id": f"reverse-{project_id[:8] or 'plan'}-v{version}",
        "project_id": project_id or "unassigned-project",
        "profile": profile,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "authority_layers": {
            "reference_order": "edge",
            "assembly_order": "timeline",
            "planning_dependency": "prompt",
        },
        "derived_fields": DERIVED_FIELDS,
        "version": version,
        "source_revision": graph.get("source_revision"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--out", required=True)
    ap.add_argument("--project-id", default="")
    ap.add_argument("--profile", default="generic")
    args = ap.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    plan = convert(graph, args.project_id, args.profile)
    Path(args.out).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    kinds: dict[str, int] = {}
    for e in plan["edges"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    roles_count: dict[str, int] = {}
    for n in plan["nodes"]:
        roles_count[n["role"]] = roles_count.get(n["role"], 0) + 1
    print(
        json.dumps(
            {
                "nodes": len(plan["nodes"]),
                "edges": len(plan["edges"]),
                "edge_kinds": kinds,
                "roles": roles_count,
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
