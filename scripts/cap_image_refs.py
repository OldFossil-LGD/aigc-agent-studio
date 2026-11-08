"""Cap image2image reference counts at the platform limit (measured: 7).

Measured on canvas 1747407b (2026-10-10):
  `node create ... -t image -s modeType=image2image` with 8 `--left` values is
  rejected with "图片/图参考/参考图数量上限：当前模型最多 0~7 张".

When a candidate_image node has more than 7 incoming references, keep the ones
that carry the film's real content first:

    character assets > scene assets > prop assets > shot scene_ref
    > shot composition_ref > shot identity_ref > anything else

and drop the lowest-ranked overflow. Prompt packages must be rebuilt from the
output graph afterwards, otherwise the prompt still names the dropped nodes.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

LIMIT = 7


def rank(src_id: str, order: int) -> tuple[int, int, int]:
    if "__asset_" in src_id:
        prefix = src_id.split("__")[0]
        # kind is not in the id, so rank by the asset list order in the caller
        return (0, order, 0)
    if src_id.endswith("__scene_ref"):
        return (1, 0, order)
    if src_id.endswith("__composition_ref"):
        return (1, 1, order)
    if src_id.endswith("__identity_ref"):
        return (1, 2, order)
    return (2, 0, order)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--assets", required=True, help="02_asset_graph_plan.json (kind lookup)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    assets = json.loads(Path(args.assets).read_text(encoding="utf-8"))
    kind_of = {a["id"]: a["kind"] for a in assets.get("assets", [])}

    incoming: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for i, e in enumerate(graph.get("edges", [])):
        incoming[e["target"]].append((i, e["source"]))

    def asset_rank(src_id: str) -> tuple[int, int]:
        asset_id = src_id.split("__asset_", 1)[0]
        kind = kind_of.get(asset_id, kind_of.get(asset_id.split("__")[0], "other"))
        return ({"character": 0, "scene": 1, "prop": 2}.get(kind, 3), 0)

    drop: set[int] = set()
    capped: list[dict] = []
    for node in graph.get("nodes", []):
        if node.get("role") != "candidate_image":
            continue
        edges = incoming.get(node["id"], [])
        if len(edges) <= LIMIT:
            continue
        scored = []
        for order, (edge_index, src) in enumerate(edges):
            if "__asset_" in src:
                key = (0,) + asset_rank(src) + (order,)
            else:
                key = rank(src, order)
            scored.append((key, edge_index, src, order))
        scored.sort(key=lambda row: row[0])
        kept = scored[:LIMIT]
        removed = scored[LIMIT:]
        for _, edge_index, _, _ in removed:
            drop.add(edge_index)
        capped.append(
            {
                "node": node["id"],
                "before": len(edges),
                "dropped": [row[2] for row in removed],
                "kept": [row[2] for row in kept],
            }
        )

    pruned = dict(graph)
    pruned["edges"] = [e for i, e in enumerate(graph.get("edges", [])) if i not in drop]
    Path(args.out).write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "edges_before": len(graph.get("edges", [])),
        "edges_after": len(pruned["edges"]),
        "edges_dropped": len(drop),
        "capped_nodes": capped,
        "out": args.out,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
