"""prune_asset_links.py - keep only the asset->shot edges the film actually shows.

`compile_shot_graph.py` wires every asset chain-end into **every** shot
(measured: 3 assets x 17 shots = 51 edges), because the contract carries no
per-shot entity information. Reverse engineering is exactly the place where
that information exists: reading the film tells you which asset appears in
which shot.

This script takes a shot->entities map and deletes the cross-product edges that
the map does not support. Read-only with respect to LibTV; edits one JSON file.

Usage:
  python prune_asset_links.py <03_shot_graph_plan.json> --map shot_assets.json --out pruned.json

map format:
  {"shot_01": [], "shot_03": ["traveler", "suitcase"], ...}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def split_id(node_id: str) -> tuple[str, str]:
    for suffix in ("__asset_refine_b", "__asset_refine_a", "__asset_anchor"):
        if node_id.endswith(suffix):
            return node_id[: -len(suffix)], "asset"
    return node_id, ""


def shot_of(node_id: str) -> str:
    return node_id.split("__", 1)[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    shot_assets = json.loads(Path(args.map).read_text(encoding="utf-8"))
    allowed = {s: set(v) for s, v in shot_assets.items()}
    by_id = {n["id"]: n for n in graph.get("nodes", [])}

    kept, dropped = [], []
    dropped_text_video = []
    for e in graph.get("edges", []):
        src, tgt = e.get("source", ""), e.get("target", "")
        s_node, t_node = by_id.get(src, {}), by_id.get(tgt, {})
        entity, kind = split_id(src)
        if kind == "asset" and "__candidate_image" in tgt:
            sid = shot_of(tgt)
            if sid in allowed and entity not in allowed[sid]:
                dropped.append((src, tgt))
                continue
        # The platform does not accept a text node as a video reference source
        # (real canvases: 97/98 text nodes carry zero edges; a `prompt`->`video`
        # link is rejected with 该节点未连接到本节点). Drop it and the matching
        # placeholder disappears when prompts are rebuilt from this graph.
        if s_node.get("node_type") == "text" and t_node.get("node_type") == "video":
            dropped_text_video.append((src, tgt))
            continue
        kept.append(e)

    pruned = dict(graph)
    pruned["edges"] = kept
    Path(args.out).write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "edges_before": len(graph.get("edges", [])),
                "edges_after": len(kept),
                "asset_shot_edges_dropped": len(dropped),
                "text_to_video_edges_dropped": len(dropped_text_video),
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
