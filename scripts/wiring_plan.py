#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上下游与连线顺序：把「谁喂谁、先建谁、入边怎么排」算清楚并给出理由。

两种顺序，别混：
  ① 节点创建顺序 = 拓扑序（上游先建；下游的 --left 才解析得到）
  ② 入边顺序     = imageListOrder（同一镜头的 --left 先后 = prompt 的 图1/图2/图3）

输入可以是清单（asset-system/2），也可以是已有画布（只读回读 imageListOrder）。

用法：
  python scripts/wiring_plan.py plan.json --report
  python scripts/wiring_plan.py plan.json --explain 资产_老周_脸部特写
  python scripts/wiring_plan.py --canvas <uuid> --report
  python scripts/wiring_plan.py --self-test
退出码：0 通过 ｜ 1 有违规 ｜ 2 用法错误 ｜ 3 没扫到节点
"""
from __future__ import print_function

import argparse
import json
import os
import subprocess
import sys

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY = 0, 1, 2, 3
try:
    from .apply_libtv_plan import resolve_libtv_binary
except ImportError:
    from apply_libtv_plan import resolve_libtv_binary

LIBTV = str(resolve_libtv_binary())
FACE_VIEWS = {"front", "left", "right"}
ROLE_CN = {"face": "脸部特写", "body": "无头身体", "anchor": "主图", "closeup": "近距版", "plan": "平面图"}
VIEW_CN = {"front": "前视", "back": "后视", "left": "左视", "right": "右视", "top": "俯视"}


def _names(doc):
    out = {}
    for key in ("characters", "props", "scenes"):
        for row in doc.get(key) or []:
            if row.get("id"):
                out[str(row["id"])] = str(row.get("name") or row["id"])
    return out


def node_name(a, names):
    subj = names.get(str(a.get("subject")), str(a.get("subject")))
    role = str(a.get("role") or "")
    tag = VIEW_CN.get(str(a.get("variant")), str(a.get("variant"))) if role == "view" else ROLE_CN.get(role, role)
    state = a.get("state")
    return "资产_%s_%s%s" % (subj, tag, ("_" + str(state)) if state else "")


def from_plan(doc):
    """返回 (nodes, edges)。nodes: label -> attrs；edges: (src, dst, kind, why)。"""
    names = _names(doc)
    nodes, edges = {}, []
    for a in doc.get("assets") or []:
        if a.get("role") == "design":
            continue
        label = node_name(a, names)
        nodes[label] = {"kind": a.get("kind"), "role": a.get("role"),
                        "subject": a.get("subject"), "layer": a.get("layer"),
                        "asset_id": a.get("asset_id")}
        parent = a.get("parent")
        if parent:
            p = next((x for x in doc["assets"] if x.get("asset_id") == parent), None)
            plabel = node_name(p, names) if p else parent
            why = "L2 派生自身份锚点" if a.get("kind") == "character" else \
                  ("近距版派生自主图" if a.get("role") == "closeup" else "机位视图派生自平面图")
            edges.append((plabel, label, "derive", why))
    for sh in doc.get("shots") or []:
        sid = "镜头_%s" % sh.get("id")
        nodes[sid] = {"kind": "shot", "role": "shot", "subject": sh.get("id")}
        plan = sh.get("reference_plan") or {}
        for i, aid in enumerate(plan.get("assets") or [], 1):
            a = next((x for x in doc["assets"] if x.get("asset_id") == aid), None)
            label = node_name(a, names) if a else aid
            edges.append((label, sid, "feed", "图%d（%s）" % (i, "主参考" if i == 1 else "补充")))
    return nodes, edges


def from_canvas(project):
    def call(*args):
        r = subprocess.run([LIBTV] + list(args), capture_output=True)
        out = r.stdout.decode("utf-8", "replace")
        return json.loads(out) if out.strip() else {}
    lst = call("node", "list", "-p", project)
    nodes, by_id = {}, {}
    for n in lst.get("nodes") or []:
        nodes[n["name"]] = {"kind": n["type"], "role": n["type"], "subject": ""}
        by_id[n["id"]] = n["name"]
    edges = []
    for n in lst.get("nodes") or []:
        d = call("node", n["name"], "-p", project)
        p = (d.get("data") or {}).get("params") or {}
        for ref in p.get("imageListOrder") or []:
            derive = n["type"] == "image"
            edges.append((by_id.get(ref, ref), n["name"],
                          "derive" if derive else "feed",
                          "画布边·图生图派生" if derive else "画布边·投喂"))
    return nodes, edges


def integrity_report(nodes, names, orders, edges):
    """画布体检：重名、参考无入边、顺序与边不一致、悬空端点。"""
    vals = list(names.values())
    dup = sorted({n for n in vals if vals.count(n) > 1})
    in_img = {}
    unknown = 0
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s not in nodes or t not in nodes:
            unknown += 1
            continue
        if nodes[s].get("type") == "image":
            in_img.setdefault(t, set()).add(s)
    refs_no_edge, mismatch = [], []
    for tid, order in orders.items():
        if not order:
            continue
        srcs = in_img.get(tid, set())
        if not srcs:
            refs_no_edge.append(tid)
        elif set(order) != srcs:
            mismatch.append(tid)
    return {"duplicate_names": dup, "duplicate_count": len(dup),
            "refs_without_edge": refs_no_edge, "order_mismatch": mismatch,
            "unknown_endpoints": unknown}


def canvas_integrity(project):
    from concurrent.futures import ThreadPoolExecutor

    def one(i):
        rr = subprocess.run([LIBTV, "node", i, "-p", project], capture_output=True)
        try:
            d = json.loads(rr.stdout.decode("utf-8", "replace"))
        except ValueError:
            return i, []
        return i, ((d.get("data") or {}).get("params") or {}).get("imageListOrder") or []

    r = subprocess.run([LIBTV, "project", project], capture_output=True)
    meta = json.loads(r.stdout.decode("utf-8", "replace"))
    nodes = {n["id"]: n for n in meta.get("nodes") or []}
    names = {i: nodes[i]["name"] for i in nodes}
    targets = [i for i in nodes if nodes[i].get("type") in ("video", "image")]
    orders = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, order in ex.map(one, targets):
            if order:
                orders[i] = order
    rep = integrity_report(nodes, names, orders, meta.get("edges") or [])
    print("画布体检：%d 节点 / %d 边" % (len(nodes), len(meta.get("edges") or [])))
    print("  重名节点：%d 个名字（%d 个节点受影响）" % (rep["duplicate_count"], len(rep["duplicate_names"])))
    for n in rep["duplicate_names"][:5]:
        print("    -", n[:50])
    print("  有参考但无入边：%d" % len(rep["refs_without_edge"]))
    for i in rep["refs_without_edge"][:5]:
        print("    -", names.get(i, i)[:50])
    print("  顺序与边不一致：%d" % len(rep["order_mismatch"]))
    for i in rep["order_mismatch"][:5]:
        print("    -", names.get(i, i)[:50])
    print("  悬空端点：%d 条边" % rep["unknown_endpoints"])
    bad = len(rep["refs_without_edge"]) + len(rep["order_mismatch"]) + rep["unknown_endpoints"]
    return RC_FAIL if bad else RC_OK


def waves(nodes, edges):
    """拓扑分层；有环返回 (None, 环上的节点)。"""
    indeg = {n: 0 for n in nodes}
    out = {n: [] for n in nodes}
    for s, d, _, _ in edges:
        if s in nodes and d in nodes:
            out[s].append(d)
            indeg[d] = indeg.get(d, 0) + 1
    q = [n for n in nodes if indeg[n] == 0]
    depth = {n: 0 for n in nodes}
    seen = 0
    while q:
        n = q.pop(0)
        seen += 1
        for m in out[n]:
            depth[m] = max(depth.get(m, 0), depth[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if seen != len(nodes):
        return None, sorted(n for n in nodes if indeg[n] > 0)
    out_w = {}
    for n, d in depth.items():
        out_w.setdefault(d, []).append(n)
    return out_w, depth


def explain(nodes, edges, target):
    up, down = {}, {}
    for s, d, k, w in edges:
        down.setdefault(s, []).append((d, k, w))
        up.setdefault(d, []).append((s, k, w))
    direct_up = up.get(target, [])
    direct_down = down.get(target, [])
    chain = []
    visited = {target}
    cycle = None
    cur = target
    while True:
        ups = up.get(cur, [])
        if not ups:
            break
        cur = ups[0][0]
        if cur in visited:
            cycle = cur
            break
        visited.add(cur)
        chain.append(cur)
    return {"target": target, "upstream_direct": direct_up, "downstream_direct": direct_down,
            "root_chain": list(reversed(chain)) + [target], "cycle": cycle}


def checks(doc, nodes, edges):
    problems = []
    ids = {str(a.get("asset_id")): a for a in doc.get("assets") or []}
    names = _names(doc)
    for a in doc.get("assets") or []:
        if a.get("role") in ("view", "body") and not a.get("parent"):
            problems.append("%s 没有 parent：派生件必须先有身份锚点" % node_name(a, names))
        if a.get("role") == "closeup" and not a.get("parent"):
            problems.append("%s 没有 parent：近距版必须指向主图" % node_name(a, names))
    for sh in doc.get("shots") or []:
        plan = sh.get("reference_plan") or {}
        faces = {}
        for aid in plan.get("assets") or []:
            a = ids.get(str(aid))
            if not a:
                problems.append("镜头_%s 引用了不存在的资产 %s" % (sh.get("id"), aid))
                continue
            if a.get("role") == "design":
                problems.append("镜头_%s 把设计板放进参考" % sh.get("id"))
            n = 1 if a.get("role") == "face" else (
                len([v for v in (a.get("covers") or [a.get("variant")]) if v in FACE_VIEWS]) if a.get("role") == "view" else 0)
            if n:
                faces[str(a.get("subject"))] = faces.get(str(a.get("subject")), 0) + n
        for s, n in faces.items():
            if n > 1:
                problems.append("镜头_%s 同一身份 %s 有 %d 张脸" % (sh.get("id"), s, n))
        if plan.get("primary_asset_id") != (plan.get("assets") or [None])[0]:
            problems.append("镜头_%s primary_asset_id 不是 assets[0]" % sh.get("id"))
    for source, target, _, _ in edges:
        if source not in nodes or target not in nodes:
            problems.append("连线 %s -> %s 存在悬空端点" % (source, target))
    # 连通性
    adj = {}
    for s, d, _, _ in edges:
        adj.setdefault(s, set()).add(d)
        adj.setdefault(d, set()).add(s)
    seen, comps = set(), 0
    for n in nodes:
        if n in seen:
            continue
        comps += 1
        q = [n]
        seen.add(n)
        while q:
            u = q.pop()
            for v in adj.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
    if comps > 1:
        problems.append("WARN: 图有 %d 个互不相连的分量：孤立链（如道具插入镜）要与主线分开确认" % comps)
    return problems


def report(doc, nodes, edges, show_waves=True):
    w, depth = waves(nodes, edges)
    if w is None:
        print("[FAIL] 有环，无法定顺序：", depth)
        return RC_FAIL
    problems = checks(doc, nodes, edges)
    if show_waves:
        print("=== 创建顺序（拓扑层）===")
        for d in sorted(w):
            print("  第 %d 层（%d）: %s" % (d, len(w[d]), "、".join(sorted(w[d]))))
        print("\n=== 边（%d 条）===" % len(edges))
        for s, dst, k, why in edges:
            print("  %-28s -> %-24s [%s] %s" % (s, dst, k, why))
    print("\n=== 检查 ===")
    fails = [p for p in problems if not p.startswith("WARN:")]
    warns = [p for p in problems if p.startswith("WARN:")]
    for p in warns:
        print("  [WARN]", p[5:].lstrip())
    for p in fails:
        print("  [FAIL]", p)
    if fails:
        return RC_FAIL
    print("  无违规：无环、每件派生件有父级、每镜同一身份 ≤1 张脸" + ("（有 %d 条提醒）" % len(warns) if warns else ""))
    return RC_OK


def _self_test():
    doc = {
        "characters": [{"id": "C1", "name": "老周", "states": ["基准"]}],
        "scenes": [{"id": "S1", "name": "屋"}],
        "props": [{"id": "P1", "name": "管"}],
        "assets": [
            {"asset_id": "F", "kind": "character", "subject": "C1", "role": "face", "layer": 1},
            {"asset_id": "VF", "kind": "character", "subject": "C1", "role": "view", "layer": 2, "parent": "F", "variant": "front"},
            {"asset_id": "VB", "kind": "character", "subject": "C1", "role": "body", "layer": 2, "parent": "F"},
            {"asset_id": "SP", "kind": "scene", "subject": "S1", "role": "plan", "layer": 1},
            {"asset_id": "SV", "kind": "scene", "subject": "S1", "role": "view", "layer": 2, "parent": "SP", "variant": "A"},
            {"asset_id": "PA", "kind": "prop", "subject": "P1", "role": "anchor", "layer": 1},
        ],
        "shots": [{"id": "V1", "reference_plan": {"primary_asset_id": "F", "assets": ["F", "PA", "SV"]}}],
    }
    bad = 0
    nodes, edges = from_plan(doc)
    w, depth = waves(nodes, edges)
    if w is None or w.get(0) is None:
        bad += 1
        print("[FAIL] 干净图被判有环")
    if depth.get("镜头_V1") != 2:
        bad += 1
        print("[FAIL] 镜头深度应为 2，实得", depth.get("镜头_V1"))
    e = explain(nodes, edges, "镜头_V1")
    if len(e["upstream_direct"]) != 3 or e["root_chain"][0] != "资产_老周_脸部特写":
        bad += 1
        print("[FAIL] 上下游解释不对：", e)
    # 环
    cyc = dict(doc)
    cyc["assets"] = list(doc["assets"]) + [{"asset_id": "X", "kind": "character", "subject": "C1", "role": "view", "layer": 2, "parent": "VF", "variant": "left"}]
    cyc["assets"] = [a if a["asset_id"] != "VF" else dict(a, parent="X") for a in cyc["assets"]]
    if waves(*from_plan(cyc))[0] is not None:
        bad += 1
        print("[FAIL] 环没有被发现")
    # 两张脸
    bad_doc = json.loads(json.dumps(doc))
    bad_doc["shots"][0]["reference_plan"]["assets"] = ["F", "VF"]
    if not checks(bad_doc, *from_plan(bad_doc)):
        bad += 1
        print("[FAIL] 两张脸没有被拦")
    # 画布体检的纯逻辑
    nodes2 = {"a": {"type": "image"}, "b": {"type": "video"}}
    ok_rep = integrity_report(nodes2, {"a": "A", "b": "B"}, {"b": ["a"]}, [{"source": "a", "target": "b"}])
    if ok_rep["refs_without_edge"] or ok_rep["order_mismatch"]:
        bad += 1
        print("[FAIL] 体检把干净画布判红：", ok_rep)
    bad_rep = integrity_report(nodes2, {"a": "A", "b": "B"}, {"b": ["a"]}, [])
    if not bad_rep["refs_without_edge"]:
        bad += 1
        print("[FAIL] 无入边没被发现")
    print("自检：%d 失败" % bad)
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="上下游分析 + 创建顺序 + 入边顺序")
    ap.add_argument("plan", nargs="?", help="asset-system/2 清单")
    ap.add_argument("--canvas", help="已有画布 uuid（只读回读）")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--explain", help="解释某个节点的上下游（用节点名）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--integrity", action="store_true", help="画布体检（需 --canvas）：重名/悬空/顺序与边不一致")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.canvas and args.integrity:
        return canvas_integrity(args.canvas)
    if args.canvas:
        nodes, edges = from_canvas(args.canvas)
        doc = {}
    elif args.plan and os.path.isfile(args.plan):
        with open(args.plan, encoding="utf-8") as f:
            doc = json.load(f)
        nodes, edges = from_plan(doc)
    else:
        ap.print_help()
        return RC_USAGE
    if not nodes:
        print("没有节点")
        return RC_EMPTY
    if args.explain:
        for source, target, _, _ in edges:
            if source not in nodes or target not in nodes:
                print("[FAIL] 连线 %s -> %s 存在悬空端点" % (source, target))
                return RC_FAIL
        layers, cyclic = waves(nodes, edges)
        if layers is None:
            print("[FAIL] 有环，无法解释依赖链：", cyclic)
            return RC_FAIL
        e = explain(nodes, edges, args.explain)
        if not e["upstream_direct"] and not e["downstream_direct"]:
            print("找不到该节点：%s" % args.explain)
            return RC_USAGE
        if args.json:
            print(json.dumps(e, ensure_ascii=False, indent=2))
            return RC_OK
        print("节点：%s" % e["target"])
        print("  根链：%s" % " → ".join(e["root_chain"]))
        print("  上游（%d）：" % len(e["upstream_direct"]))
        for s, k, w in e["upstream_direct"]:
            print("    ← %s [%s] %s" % (s, k, w))
        print("  下游（%d）：" % len(e["downstream_direct"]))
        for d, k, w in e["downstream_direct"]:
            print("    → %s [%s] %s" % (d, k, w))
        return RC_OK
    return report(doc, nodes, edges)


if __name__ == "__main__":
    sys.exit(main())
