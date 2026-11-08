#!/usr/bin/env python3
"""Compute canvas coordinates for a node list — the library's layout rule, executable.

Why this exists (E233, 实测 2026-10-12):
  · `-x/-y` 只在 `create` 时生效；已建节点**无法移动**（单独跑 --x/--y 是空操作，
    `-u position={...}` 也 exit 0 而不生效）→ 坐标必须**建之前**算好。
  · 绑定普通分组会把坐标变成**组内相对**并重排节点（实测重叠对 0 → 24）
    → 不要"先排好再入组"。

规则：节点约 620×350 → 列距 820、行距 760；按依赖分行，引线方向一致。
  资产行 y=0     A*（按 x 递增）
  分镜行 y=760   T* S* I*（按 x 递增）
  镜头行 y=1520  V* X*（按 x 递增）

用法：
  python scripts/canvas_layout.py --spec spec.json --out layout.json
  python scripts/canvas_layout.py --spec spec.json            # 只打印
  python scripts/canvas_layout.py --self-test

退出码：0 无重叠 · 1 检出重叠/同坐标 · 2 用法 · 3 没扫到节点
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


COL_X = 820
ROW_Y = {"asset": 0, "board": 760, "shot": 1520}
NODE_W, NODE_H = 620, 350


def row_of(node_type: str, node_id: str) -> str:
    if node_type == "image" and node_id.startswith("A"):
        return "asset"
    if node_type == "script" or node_id.startswith(("T", "S", "I")):
        return "board"
    return "shot"


def plan(nodes: list[dict]) -> list[dict]:
    """Return [{id, name, nodeType, x, y}] with one slot per node."""
    buckets: dict[str, list[dict]] = {"asset": [], "board": [], "shot": []}
    for node in nodes:
        buckets[row_of(node.get("nodeType", ""), node.get("id", ""))].append(node)
    out: list[dict] = []
    for row, items in buckets.items():
        for index, node in enumerate(items):
            out.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "nodeType": node.get("nodeType"),
                "row": row,
                "x": index * COL_X,
                "y": ROW_Y[row],
            })
    return out


def overlaps(slots: list[dict]) -> tuple[list, list]:
    boxes = [(s["x"], s["y"], s["x"] + NODE_W, s["y"] + NODE_H, s["id"]) for s in slots]
    pairs, seen = [], {}
    for box in boxes:
        key = (box[0], box[1])
        seen.setdefault(key, []).append(box[4])
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                pairs.append((a[4], b[4]))
    return pairs, [v for v in seen.values() if len(v) > 1]


def self_test() -> int:
    cases = []
    nodes = [{"id": "A%d" % i, "name": "A%d" % i, "nodeType": "image"} for i in range(1, 7)]
    nodes += [{"id": x, "name": x, "nodeType": "script" if x == "T1" else "image"} for x in ("T1", "S1", "I1")]
    nodes += [{"id": "V%d" % i, "name": "V%d" % i, "nodeType": "video"} for i in range(1, 6)]
    nodes += [{"id": "X1", "name": "X1", "nodeType": "video-clip"}]
    slots = plan(nodes)
    pairs, shared = overlaps(slots)
    cases.append(("slots_cover_all_nodes", len(slots) == len(nodes)))
    cases.append(("no_overlap", not pairs))
    cases.append(("no_shared_slot", not shared))
    cases.append(("rows_ordered", ROW_Y["asset"] < ROW_Y["board"] < ROW_Y["shot"]))
    cases.append(("asset_row_starts_at_origin", min(s["x"] for s in slots) == 0))
    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail",
                      "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec")
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.spec:
        parser.error("--spec is required unless --self-test")

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    nodes = [n for n in (spec.get("nodes") or []) if n.get("nodeType")]
    if not nodes:
        print(json.dumps({"status": "NOT_VERIFIED", "reason": "no nodes in spec"}, ensure_ascii=False))
        return 3
    slots = plan(nodes)
    pairs, shared = overlaps(slots)
    result = {"status": "PASS" if not pairs and not shared else "FAIL",
              "grid": {"node": [NODE_W, NODE_H], "col_x": COL_X, "row_y": ROW_Y},
              "slots": slots, "overlapping_pairs": pairs, "shared_slots": shared}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
