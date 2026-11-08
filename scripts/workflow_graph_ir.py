#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workflow Graph IR v2：图语义的唯一权威（节点 / 端口 / 边种类 / 顺序）。

为什么要有它（审查报告 P0-03、任务书 T-P1-02）：
旧仓库里三套图各说各话——`shot_graph_plan` 用 `source/target/purpose`，
`graph_plan_lint` 用 `source_id/target_id/kind`，`_mirror_graph` 又是一种；
而 `compile_libtv_commands` 把**每条边**都编成 `node_link`，等于默认"有边就要连"。
后果：逻辑依赖、血缘、合成顺序全被当成物理参考线。

本模块把图收敛成一份带类型的数据：

  build   ：旧图 → v2（不可无损的字段进 `loss_report`，不静默丢）
  validate：端点、端口、边种类、重复、自环、环、参考顺序
  linkable：**只有 `data_reference`（或显式批准的 assembly）** 允许落平台引用线
  diff    ：两次修订的节点/边/顺序差异（给影响分析用）

边界：不改真实画布、不调用平台、不猜测未知端口（`status=UNKNOWN` 一律不落线）。

退出码：0 通过 ｜ 1 有 BLOCK ｜ 2 用法错误 ｜ 4 只有 WARN/UNKNOWN

用法：
  python scripts/workflow_graph_ir.py build --in plan.json --out graph_ir.json
  python scripts/workflow_graph_ir.py validate --graph graph_ir.json
  python scripts/workflow_graph_ir.py summary --graph graph_ir.json
  python scripts/workflow_graph_ir.py diff --before a.json --after b.json
  python scripts/workflow_graph_ir.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys

try:
    from .error_contract import mk_error as _mk
except ImportError:
    try:
        from error_contract import mk_error as _mk
    except ImportError:  # 单文件运行兜底
        def _mk(code, severity, message, path=None, node_id=None, edge_id=None, fix=None):
            return {"code": code, "severity": severity, "message": message, "path": path,
                    "node_id": node_id, "edge_id": edge_id, "suggested_fix": fix}

RC_OK, RC_FAIL, RC_USAGE, RC_WARN = 0, 1, 2, 4
VERSION = "workflow-graph-ir/v2"

# 旧 purpose → v2 kind。未登记的一律 unknown（不假设成 data_reference）。
PURPOSE_TO_KIND = {
    "reference": "data_reference",
    "image_reference": "data_reference",
    "prompt": "data_reference",
    "compile": "control_dependency",
    "dependency": "control_dependency",
    "order": "control_dependency",
    "assembly": "assembly",
    "lineage": "lineage",
    "condition": "condition",
    "asset_refine": "data_reference",
    "asset_character": "data_reference", "asset_scene": "data_reference",
    "asset_location": "data_reference", "asset_prop": "data_reference",
    "asset_other": "data_reference",
    "scene": "data_reference", "identity": "data_reference",
    "composition": "data_reference", "state": "data_reference", "refine": "data_reference",
    "asset_manifest": "control_dependency", "qa": "control_dependency",
    "selection": "control_dependency", "selection_record": "lineage",
    "candidate_input": "assembly", "assemble": "assembly", "sound": "assembly",
}
LINKABLE_KINDS = {"data_reference"}


def _registry():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "schemas", "port_registry.json")
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f).get("types") or {}
    except (IOError, OSError, ValueError):
        return {}


PORT_REGISTRY = _registry()


def _ports(platform_type):
    entry = PORT_REGISTRY.get(platform_type)
    if entry and entry.get("status") == "KNOWN":
        return ([dict(p, status="KNOWN") for p in entry.get("input_ports") or []],
                [dict(p, status="KNOWN") for p in entry.get("output_ports") or []])
    if entry and entry.get("status") == "UNKNOWN":
        return [], []
    if platform_type == "video":  # 兜底（注册表缺失时）
        return ([{"port_id": "reference_images", "payload_type": "ImageAssetRef", "required": False,
                  "status": "KNOWN"}],
                [{"port_id": "video", "payload_type": "VideoAssetRef", "status": "KNOWN"}])
    if platform_type == "image":
        return ([{"port_id": "reference_image", "payload_type": "ImageAssetRef", "required": False,
                  "status": "KNOWN"}],
                [{"port_id": "image", "payload_type": "ImageAssetRef", "status": "KNOWN"}])
    if platform_type == "text":
        return ([], [{"port_id": "text", "payload_type": "Text", "status": "KNOWN"}])
    return ([], [])


def build_legacy_v1(graph, graph_id="GRAPH_001", revision=1):
    """旧图（nodes[id]/edges[source,target,purpose]）→ v2，附 loss_report。"""
    nodes, edges, loss = [], [], []
    for n in graph.get("nodes") or []:
        nid = n.get("id") or n.get("node_id")
        ptype = n.get("node_type") or "text"
        ins, outs = _ports(ptype)
        unknown_ports = ptype in ("audio", "video-clip")
        if unknown_ports:
            loss.append({"field": "ports", "node_uid": nid,
                         "reason": "该平台类型的端口契约未登记", "status": "UNKNOWN"})
        nodes.append({
            "node_uid": str(nid), "logical_id": str(nid), "logical_role": n.get("role"),
            "platform_type": ptype, "input_ports": ins, "output_ports": outs,
            "group_id": n.get("group_id"),
            "platform_mapping": {"libtv_uuid": None, "display_name": n.get("name"),
                                 "status": "UNVERIFIED"},
            "legacy": {k: v for k, v in n.items() if k not in ("id", "node_type", "role")},
        })
    for i, e in enumerate(graph.get("edges") or []):
        purpose = e.get("purpose") or e.get("kind")
        kind = PURPOSE_TO_KIND.get(str(purpose), "unknown")
        if kind == "unknown":
            loss.append({"field": "edge.kind", "edge_uid": e.get("edge_uid") or "E%03d" % i,
                         "reason": "旧 purpose=%r 未登记，标 unknown（不当作引用）" % purpose,
                         "status": "LOSSY"})
        edges.append({
            "edge_uid": e.get("edge_uid") or "E%03d" % (i + 1),
            "kind": kind,
            "source": {"node_uid": str(e.get("source") or e.get("source_id")),
                       "port_id": e.get("source_port")},
            "target": {"node_uid": str(e.get("target") or e.get("target_id")),
                       "port_id": e.get("target_port")},
            "payload_type": e.get("payload_type"),
            "reference_order": e.get("reference_order"),
            "condition": e.get("condition"),
            "platform_mapping": {"status": "UNVERIFIED"},
            "legacy": {k: v for k, v in e.items() if k not in
                       ("source", "target", "purpose", "kind", "source_id", "target_id")},
        })
    return {"schema_version": VERSION, "graph_id": graph_id, "revision": revision,
            "source": {"system": "legacy_v1", "legacy_format": "nodes[id]+edges[purpose]"},
            "groups": graph.get("groups") or [], "nodes": nodes, "edges": edges,
            "loss_report": loss, "allowed_cycles": graph.get("allowed_cycles") or []}


def validate(gir):
    issues = []
    nodes = {n.get("node_uid"): n for n in gir.get("nodes") or []}
    if len(nodes) != len(gir.get("nodes") or []):
        issues.append(_mk("GRAPH_DUPLICATE_NODE", "ERROR", "节点 UID 重复", path="#/nodes"))
    seen_edges = set()
    ref_orders = {}
    for e in gir.get("edges") or []:
        eid = e.get("edge_uid")
        src, tgt = (e.get("source") or {}), (e.get("target") or {})
        if e.get("kind") not in ("data_reference", "control_dependency", "assembly",
                                 "lineage", "condition", "unknown"):
            issues.append(_mk("GRAPH_EDGE_BAD_KIND", "ERROR", "边种类非法：%r" % e.get("kind"),
                              path="#/edges", edge_id=eid))
        if src.get("node_uid") not in nodes or tgt.get("node_uid") not in nodes:
            issues.append(_mk("GRAPH_EDGE_DANGLING", "ERROR", "边端点不存在",
                              path="#/edges", edge_id=eid))
            continue
        if src.get("node_uid") == tgt.get("node_uid"):
            issues.append(_mk("GRAPH_SELF_LOOP", "ERROR", "自环边", path="#/edges", edge_id=eid))
        key = (src.get("node_uid"), tgt.get("node_uid"), e.get("kind"))
        if key in seen_edges:
            issues.append(_mk("GRAPH_DUPLICATE_EDGE", "ERROR", "重复边（会放大权重）",
                              path="#/edges", edge_id=eid))
        seen_edges.add(key)
        if e.get("kind") == "data_reference":
            tport = tgt.get("port_id")
            ports = {p.get("port_id"): p for p in nodes[tgt["node_uid"]].get("input_ports") or []}
            if not tport or tport not in ports:
                issues.append(_mk("GRAPH_TARGET_PORT_UNKNOWN", "WARN",
                                  "目标端口 %r 未登记：不得据此落物理连线" % tport,
                                  path="#/edges", edge_id=eid, fix="补端口契约或保持 UNVERIFIED"))
            elif ports[tport].get("payload_type") and e.get("payload_type") \
                    and ports[tport]["payload_type"] != e.get("payload_type"):
                issues.append(_mk("GRAPH_PORT_TYPE_MISMATCH", "ERROR", "端口类型不匹配",
                                  path="#/edges", edge_id=eid))
            if e.get("reference_order") is not None:
                slot = (tgt.get("node_uid"), tport)
                if e["reference_order"] in ref_orders.setdefault(slot, {}):
                    issues.append(_mk("GRAPH_REFERENCE_ORDER_DUP", "ERROR",
                                      "同一输入槽位参考顺序重复", path="#/edges", edge_id=eid))
                ref_orders[slot][e["reference_order"]] = eid
    issues.extend(_cycles(gir))
    return issues


def _cycles(gir):
    adj = {}
    for e in gir.get("edges") or []:
        s, t = (e.get("source") or {}).get("node_uid"), (e.get("target") or {}).get("node_uid")
        if s and t and s != t:
            adj.setdefault(s, []).append(t)
    declared = {tuple(p) for p in gir.get("allowed_cycles") or []}
    out, state = [], {}

    def walk(nid, stack):
        state[nid] = 1
        for nxt in adj.get(nid, []):
            if state.get(nxt) == 1:
                cycle = tuple(stack[stack.index(nxt):] + [nxt]) if nxt in stack else (nid, nxt)
                if cycle in declared:
                    continue
                return stack + [nid, nxt]
            if state.get(nxt) is None:
                got = walk(nxt, stack + [nid])
                if got:
                    return got
        state[nid] = 2
        return None

    for nid in list(adj):
        if state.get(nid) is None:
            found = walk(nid, [])
            if found:
                out.append(_mk("GRAPH_CYCLE", "ERROR", "依赖成环：%s" % " → ".join(found),
                               path="#/edges", fix="显式登记 allowed_cycles 或断开"))
                break
    return out


def _adj(gir, reverse=False):
    adj = {}
    for e in gir.get("edges") or []:
        s, t = (e.get("source") or {}).get("node_uid"), (e.get("target") or {}).get("node_uid")
        if not s or not t:
            continue
        a, b = (t, s) if reverse else (s, t)
        adj.setdefault(a, []).append(b)
    return adj


def upstream(gir, node_uid, depth=1):
    """只读：向上游追溯（depth=None 表示不限）。"""
    adj, seen, frontier = _adj(gir, reverse=True), set(), [(node_uid, 0)]
    out = []
    while frontier:
        cur, d = frontier.pop(0)
        if depth is not None and d >= depth:
            continue
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                out.append(nxt)
                frontier.append((nxt, d + 1))
    return out


def downstream(gir, node_uid, depth=1):
    adj, seen, frontier = _adj(gir), set(), [(node_uid, 0)]
    out = []
    while frontier:
        cur, d = frontier.pop(0)
        if depth is not None and d >= depth:
            continue
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                out.append(nxt)
                frontier.append((nxt, d + 1))
    return out


def path(gir, source_uid, target_uid):
    adj, prev, queue = _adj(gir), {source_uid: None}, [source_uid]
    while queue:
        cur = queue.pop(0)
        if cur == target_uid:
            chain = [cur]
            while prev[chain[-1]] is not None:
                chain.append(prev[chain[-1]])
            return list(reversed(chain))
        for nxt in adj.get(cur, []):
            if nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    return None


def edge_references(gir, node_uid, input_port=None):
    out = []
    for e in gir.get("edges") or []:
        tgt = e.get("target") or {}
        if tgt.get("node_uid") == node_uid and (input_port is None or tgt.get("port_id") == input_port):
            out.append(e)
    return sorted(out, key=lambda e: (e.get("reference_order") is None, e.get("reference_order") or 0))


def linkable(edge):
    """只有 data_reference 允许落平台引用线；其余返回 (False, 原因)。"""
    kind = edge.get("kind")
    if kind in LINKABLE_KINDS:
        if (edge.get("platform_mapping") or {}).get("status") == "MISMATCH":
            return False, "PLATFORM_MAPPING_MISMATCH"
        return True, "DATA_REFERENCE"
    if kind == "assembly" and (edge.get("platform_mapping") or {}).get("approved") is True:
        return True, "ASSEMBLY_APPROVED"
    return False, "NOT_A_DATA_REFERENCE:%s" % kind


def diff(before, after):
    bn = {n["node_uid"] for n in before.get("nodes") or []}
    an = {n["node_uid"] for n in after.get("nodes") or []}
    be = {e["edge_uid"]: e for e in before.get("edges") or []}
    ae = {e["edge_uid"]: e for e in after.get("edges") or []}
    order_changed = []
    edges_changed = []
    for eid in sorted(set(be) & set(ae)):
        fields = sorted(key for key in set(be[eid]) | set(ae[eid])
                        if key != "reference_order" and be[eid].get(key) != ae[eid].get(key))
        if fields:
            edges_changed.append({"edge_uid": eid, "changed_fields": fields,
                                  "before": be[eid], "after": ae[eid]})
        if be[eid].get("reference_order") != ae[eid].get("reference_order"):
            order_changed.append({"edge_uid": eid,
                                  "before": be[eid].get("reference_order"),
                                  "after": ae[eid].get("reference_order")})
    return {"nodes_added": sorted(an - bn), "nodes_removed": sorted(bn - an),
            "edges_added": sorted(set(ae) - set(be)), "edges_removed": sorted(set(be) - set(ae)),
            "reference_order_changed": order_changed, "edges_changed": edges_changed}


def summary(gir):
    kinds = {}
    for e in gir.get("edges") or []:
        kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
    return {"graph_id": gir.get("graph_id"), "revision": gir.get("revision"),
            "nodes": len(gir.get("nodes") or []), "edges": len(gir.get("edges") or []),
            "edge_kinds": kinds, "loss_report": len(gir.get("loss_report") or [])}


def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def self_test():
    legacy = {"nodes": [{"id": "shot__a", "node_type": "text", "role": "prompt"},
                        {"id": "shot__a__img", "node_type": "image", "role": "candidate_image"},
                        {"id": "shot__a__sel", "node_type": "text", "role": "selection"}],
              "edges": [{"source": "shot__a", "target": "shot__a__img", "purpose": "reference"},
                        {"source": "shot__a__img", "target": "shot__a__sel", "purpose": "dependency"}],
              "groups": []}
    gir = build_legacy_v1(legacy)
    checks = []
    checks.append(("版本号", gir["schema_version"] == VERSION))
    checks.append(("边种类映射", [e["kind"] for e in gir["edges"]] == ["data_reference", "control_dependency"]))
    checks.append(("无损失", gir["loss_report"] == []))
    checks.append(("只有 data_reference 可落线",
                   linkable(gir["edges"][0])[0] and not linkable(gir["edges"][1])[0]))
    issues = validate(gir)
    checks.append(("基线无 ERROR", not [i for i in issues if i["severity"] == "ERROR"]))
    # 端点缺失
    bad = json.loads(json.dumps(gir)); bad["edges"][0]["target"]["node_uid"] = "nope"
    checks.append(("端点缺失被抓", any(i["code"] == "GRAPH_EDGE_DANGLING" for i in validate(bad))))
    # 未知 purpose
    lossy = build_legacy_v1({"nodes": legacy["nodes"], "edges": [
        {"source": "shot__a", "target": "shot__a__img", "purpose": "mystery"}], "groups": []})
    checks.append(("未知 purpose 标 LOSSY 且 kind=unknown",
                   lossy["edges"][0]["kind"] == "unknown" and lossy["loss_report"]))
    # 端口未知 → WARN 且不落线
    unk = json.loads(json.dumps(gir)); unk["edges"][0]["target"]["port_id"] = None
    checks.append(("端口未知给 WARN", any(i["code"] == "GRAPH_TARGET_PORT_UNKNOWN"
                                          for i in validate(unk))))
    # diff
    changed = json.loads(json.dumps(gir)); changed["edges"][0]["reference_order"] = 2
    d = diff(gir, changed)
    checks.append(("diff 抓顺序变化", d["reference_order_changed"]))
    # 环
    cyc = json.loads(json.dumps(gir)); cyc["edges"].append(
        {"edge_uid": "E9", "kind": "control_dependency",
         "source": {"node_uid": "shot__a__img"}, "target": {"node_uid": "shot__a"}})
    checks.append(("环被抓", any(i["code"] == "GRAPH_CYCLE" for i in validate(cyc))))
    checks.append(("端口注册表：audio=UNKNOWN", _ports("audio") == ([], [])))
    checks.append(("上游可查", upstream(gir, "shot__a__sel") == ["shot__a__img"]))
    checks.append(("路径可查", path(gir, "shot__a", "shot__a__sel") == ["shot__a", "shot__a__img", "shot__a__sel"]))
    # 旧图没有端口信息：按节点查（端口未证实时不假装知道槽位）
    checks.append(("引用边可查（按节点）", bool(edge_references(gir, "shot__a__img"))))
    bad = 0
    for label, ok in checks:
        if not ok:
            bad += 1
            print("[FAIL] %s" % label)
        else:
            print("[PASS] %s" % label)
    print("自检：%d 项，%d 失败" % (len(checks), bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="Workflow Graph IR v2")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build"); b.add_argument("--in", dest="inp", required=True); b.add_argument("--out")
    v = sub.add_parser("validate"); v.add_argument("--graph", required=True)
    s = sub.add_parser("summary"); s.add_argument("--graph", required=True)
    u = sub.add_parser("upstream"); u.add_argument("--graph", required=True); u.add_argument("--node", required=True)
    dn = sub.add_parser("downstream"); dn.add_argument("--graph", required=True); dn.add_argument("--node", required=True)
    pa = sub.add_parser("path"); pa.add_argument("--graph", required=True); pa.add_argument("--from", dest="src", required=True); pa.add_argument("--to", dest="dst", required=True)
    d = sub.add_parser("diff"); d.add_argument("--before", required=True); d.add_argument("--after", required=True)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd == "build":
        gir = build_legacy_v1(_load(args.inp))
        text = json.dumps(gir, ensure_ascii=False, indent=2, sort_keys=True)
        if args.out:
            io.open(args.out, "w", encoding="utf-8", newline="\n").write(text + "\n")
        print(text)
        issues = validate(gir)
        return RC_FAIL if any(i["severity"] == "ERROR" for i in issues) else (
            RC_WARN if issues else RC_OK)
    if args.cmd == "validate":
        issues = validate(_load(args.graph))
        print(json.dumps({"issues": issues}, ensure_ascii=False, indent=2))
        return RC_FAIL if any(i["severity"] == "ERROR" for i in issues) else (RC_WARN if issues else RC_OK)
    if args.cmd == "summary":
        print(json.dumps(summary(_load(args.graph)), ensure_ascii=False, indent=2))
        return RC_OK
    if args.cmd == "upstream":
        print(json.dumps(upstream(_load(args.graph), args.node, depth=None), ensure_ascii=False))
        return RC_OK
    if args.cmd == "downstream":
        print(json.dumps(downstream(_load(args.graph), args.node, depth=None), ensure_ascii=False))
        return RC_OK
    if args.cmd == "path":
        print(json.dumps(path(_load(args.graph), args.src, args.dst), ensure_ascii=False))
        return RC_OK
    if args.cmd == "diff":
        print(json.dumps(diff(_load(args.before), _load(args.after)), ensure_ascii=False, indent=2))
        return RC_OK
    ap.print_help()
    return RC_USAGE


if __name__ == "__main__":
    sys.exit(main())
