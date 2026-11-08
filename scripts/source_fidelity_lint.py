#!/usr/bin/env python3
"""Gate reverse/mirror plans against a source graph, in both directions.

The band is two-sided on purpose:

    0.95 <= plan/source        -> nothing from the source was dropped
           plan/source <= 1.10  -> nothing material was invented

The one-sided version this replaces let a 6x-larger "normalised production
graph" pass the node and edge checks, which is how a faithful-mirror claim
could ride on a plan that was never a mirror.

Inputs are `libtv project <uuid>` readbacks or compiler graph plans carrying
`nodes` and `edges`. Node type is read from `type` or `node_type`, because
readbacks use the first and compiler plans use the second.

Read-only: this never calls LibTV, never triggers generation.

Exit codes: 0 PASS, 1 FAIL, 2 usage, 3 not_verified.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys

try:
    from scripts.reverse_contract import mode_errors, normalize_mode
except ImportError:
    from reverse_contract import mode_errors, normalize_mode


RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY = 0, 1, 2, 3

KNOWN_TYPES = ("image", "video", "group", "script", "storyboard", "audio", "video-clip")

MIRROR_MODES = ("source_replica", "copy_reverse")


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def emit(result, path=None):
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def node_type(node):
    """Readbacks write `type`, compiler plans write `node_type`."""
    return node.get("type") or node.get("node_type")


def graph_stats(graph):
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    by_id = {node.get("id"): node for node in nodes}
    type_counts = collections.Counter(node_type(node) for node in nodes if node_type(node))
    untyped = sum(1 for node in nodes if not node_type(node))
    edge_pairs = collections.Counter()
    for edge in edges:
        source_type = node_type(by_id.get(edge.get("source")) or {})
        target_type = node_type(by_id.get(edge.get("target")) or {})
        edge_pairs[(source_type, target_type)] += 1
    lineage = collections.Counter()
    no_lineage = 0
    for node in nodes:
        source_node_id = node.get("source_node_id")
        if source_node_id:
            lineage[str(source_node_id)] += 1
        else:
            no_lineage += 1
    return {
        "node_total": len(nodes),
        "edge_total": len(edges),
        "untyped_nodes": untyped,
        "type_counts": dict(type_counts),
        "edge_pair_counts": {
            "%s->%s" % (key[0], key[1]): value for key, value in edge_pairs.items()
        },
        "node_ids": sorted(str(node.get("id")) for node in nodes if node.get("id")),
        "lineage_ids": sorted(lineage),
        "nodes_without_lineage": no_lineage,
        "duplicate_lineage_ids": sorted(key for key, count in lineage.items() if count > 1),
    }


def ratio(plan, source):
    if source == 0:
        return 1.0 if plan == 0 else None
    return plan / source


def band_failures(code_low, code_high, size, plan_count, source_count, min_ratio, max_ratio):
    """Return the (0-2) band failures for one dimension."""
    current = ratio(plan_count, source_count)
    out = []
    if current is None or current < min_ratio:
        out.append({"code": code_low, size: source_count, "plan": plan_count, "ratio": current, "minimum": min_ratio})
    elif current > max_ratio:
        out.append({"code": code_high, size: source_count, "plan": plan_count, "ratio": current, "maximum": max_ratio})
    return current, out


def lineage_failures(source, plan):
    """Mirror plans must account for every source node exactly once."""
    failures = []
    if plan["nodes_without_lineage"]:
        failures.append(
            {
                "code": "FIDELITY_NO_LINEAGE",
                "nodes_without_lineage": plan["nodes_without_lineage"],
                "message": "mirror plan nodes must carry source_node_id pointing at the source node they mirror.",
            }
        )
    if plan.get("duplicate_lineage_ids"):
        failures.append({"code": "FIDELITY_DUPLICATE_LINEAGE",
                         "sample": plan["duplicate_lineage_ids"][:10]})
    source_ids = set(source["node_ids"])
    linked = set(plan["lineage_ids"])
    mapped = source_ids & linked
    missing = sorted(source_ids - linked)
    extra = sorted(linked - source_ids)
    coverage = (len(mapped) / len(source_ids)) if source_ids else 1.0
    if missing:
        failures.append(
            {
                "code": "FIDELITY_UNMAPPED_SOURCE_NODES",
                "missing": len(missing),
                "coverage": coverage,
                "sample": missing[:10],
            }
        )
    if extra:
        failures.append(
            {
                "code": "FIDELITY_EXTRA_PLAN_NODES",
                "extra": len(extra),
                "sample": extra[:10],
                "message": "plan claims lineage to source nodes that do not exist.",
            }
        )
    return failures, {"coverage": coverage, "mapped": len(mapped), "missing": len(missing), "extra": len(extra)}


def mirror_topology_failures(source_graph, plan_graph, minimum):
    """Compare directed edge multisets after mapping plan IDs to source IDs."""
    for name, graph in (("source", source_graph), ("plan", plan_graph)):
        nodes = graph.get("nodes") or []
        ids = [str(node.get("id")) for node in nodes if node.get("id") is not None]
        if len(ids) != len(nodes) or len(set(ids)) != len(ids):
            return [{"code": "FIDELITY_NODE_IDS_INVALID", "graph": name}], None
        known = set(ids)
        dangling = [edge for edge in graph.get("edges") or []
                    if str(edge.get("source")) not in known or str(edge.get("target")) not in known]
        if dangling:
            return [{"code": "FIDELITY_DANGLING_EDGES", "graph": name,
                     "count": len(dangling), "sample": dangling[:10]}], None
    mapping = {str(node["id"]): str(node["source_node_id"])
               for node in plan_graph.get("nodes") or []}
    expected = collections.Counter((str(edge["source"]), str(edge["target"]))
                                   for edge in source_graph.get("edges") or [])
    actual = collections.Counter((mapping[str(edge["source"])], mapping[str(edge["target"])])
                                 for edge in plan_graph.get("edges") or [])
    matched = sum((expected & actual).values())
    missing = expected - actual
    extra = actual - expected
    coverage = ratio(matched, sum(expected.values()))
    report = {"matched_edges": matched, "missing_edges": sum(missing.values()),
              "extra_edges": sum(extra.values()), "source_coverage": coverage, "minimum": minimum}
    failures = []
    if coverage < minimum:
        failures.append({"code": "FIDELITY_EDGE_TOPOLOGY", **report,
                         "missing_sample": [{"source": pair[0], "target": pair[1], "count": count}
                                            for pair, count in sorted(missing.items())[:10]],
                         "extra_sample": [{"source": pair[0], "target": pair[1], "count": count}
                                          for pair, count in sorted(extra.items())[:10]]})
    return failures, report


def evaluate(
    source_graph,
    plan_graph,
    *,
    mode="source_replica",
    deliverable="auto",
    lineage="auto",
    min_node_ratio=0.95,
    max_node_ratio=1.10,
    min_edge_ratio=0.95,
    max_edge_ratio=1.10,
    min_type_ratio=0.90,
    max_type_ratio=1.10,
    min_group_ratio=0.80,
    max_group_ratio=1.10,
    source_metrics=None,
    plan_metrics=None,
    warnings=None,
):
    """Return the gate result dict (status / failures / rows) without filesystem access."""
    warnings = list(warnings or [])
    if deliverable == "auto":
        deliverable = "mirror" if mode in MIRROR_MODES else "production_plan"
    if lineage == "auto":
        lineage = "on" if deliverable == "mirror" else "off"

    source = graph_stats(source_graph)
    if source["node_total"] == 0 and source["edge_total"] == 0:
        return {
            "mode": mode,
            "deliverable": deliverable,
            "status": "NOT_VERIFIED",
            "warnings": warnings,
            "source": source,
            "failures": [{"code": "SOURCE_GRAPH_UNAVAILABLE"}],
            "message": "源图无节点与边，缺失基线时既不判 PASS 也不判 FAIL。",
        }

    plan = graph_stats(plan_graph)
    failures = []

    if plan["untyped_nodes"]:
        warnings.append(
            {
                "code": "PLAN_NODES_UNTYPED",
                "nodes": plan["untyped_nodes"],
                "message": "plan nodes carry neither `type` nor `node_type`; type comparison is blind to them.",
            }
        )

    node_ratio, node_failures = band_failures(
        "FIDELITY_NODE_TOTAL", "FIDELITY_OVERBUILD_NODE_TOTAL",
        "source", plan["node_total"], source["node_total"], min_node_ratio, max_node_ratio,
    )
    failures.extend(node_failures)
    edge_ratio, edge_failures = band_failures(
        "FIDELITY_EDGE_TOTAL", "FIDELITY_OVERBUILD_EDGE_TOTAL",
        "source", plan["edge_total"], source["edge_total"], min_edge_ratio, max_edge_ratio,
    )
    failures.extend(edge_failures)

    type_rows = {}
    for node_type_name, source_count in source["type_counts"].items():
        if node_type_name not in KNOWN_TYPES:
            continue
        minimum = min_group_ratio if node_type_name == "group" else min_type_ratio
        maximum = max_group_ratio if node_type_name == "group" else max_type_ratio
        plan_count = plan["type_counts"].get(node_type_name, 0)
        current, rows = band_failures(
            "FIDELITY_TYPE_%s" % node_type_name.upper(),
            "FIDELITY_TYPE_OVERBUILD_%s" % node_type_name.upper(),
            "source", plan_count, source_count, minimum, maximum,
        )
        type_rows[node_type_name] = {"source": source_count, "plan": plan_count, "ratio": current, "minimum": minimum, "maximum": maximum}
        failures.extend(rows)

    edge_rows = {}
    for pair, source_count in source["edge_pair_counts"].items():
        plan_count = plan["edge_pair_counts"].get(pair, 0)
        current, rows = band_failures(
            "FIDELITY_EDGE_%s" % pair.replace("->", "_TO_").replace("None", "UNKNOWN").upper(),
            "FIDELITY_EDGE_OVERBUILD_%s" % pair.replace("->", "_TO_").replace("None", "UNKNOWN").upper(),
            "source", plan_count, source_count, min_edge_ratio, max_edge_ratio,
        )
        edge_rows[pair] = {"source": source_count, "plan": plan_count, "ratio": current, "minimum": min_edge_ratio, "maximum": max_edge_ratio}
        failures.extend(rows)

    extra_rows = {}
    if source_metrics and plan_metrics:
        for key, source_value in source_metrics.items():
            if not isinstance(source_value, (int, float)):
                continue
            plan_value = plan_metrics.get(key, 0)
            current, rows = band_failures(
                "FIDELITY_METRIC_%s" % key.upper(),
                "FIDELITY_METRIC_OVERBUILD_%s" % key.upper(),
                "source", plan_value, source_value, min_type_ratio, max_type_ratio,
            )
            extra_rows[key] = {"source": source_value, "plan": plan_value, "ratio": current}
            failures.extend(rows)

    lineage_report = None
    topology_report = None
    if lineage == "on":
        lineage_rows, lineage_report = lineage_failures(source, plan)
        failures.extend(lineage_rows)
        if deliverable == "mirror" and not lineage_rows:
            topology_failures, topology_report = mirror_topology_failures(
                source_graph, plan_graph, min_edge_ratio)
            failures.extend(topology_failures)

    return {
        "mode": mode,
        "deliverable": deliverable,
        "lineage": lineage,
        "status": "FAIL" if failures else "PASS",
        "warnings": warnings,
        "source": {key: value for key, value in source.items() if key not in ("node_ids", "lineage_ids", "duplicate_lineage_ids")},
        "plan": {key: value for key, value in plan.items() if key not in ("node_ids", "lineage_ids")},
        "node_ratio": node_ratio,
        "edge_ratio": edge_ratio,
        "type_fidelity": type_rows,
        "edge_fidelity": edge_rows,
        "extra_metric_fidelity": extra_rows,
        "lineage_report": lineage_report,
        "topology_fidelity": topology_report,
        "failures": failures,
    }


def _fake_graph(counts, *, typed=True, lineage=True, prefix="n"):
    """Build a tiny graph: counts = {type: how many}."""
    nodes, edges = [], []
    index = 0
    for type_name, how_many in counts.items():
        for _ in range(how_many):
            node = {"id": "%s%d" % (prefix, index)}
            if typed:
                node["type"] = type_name
            else:
                node["node_type"] = type_name
            if lineage:
                node["source_node_id"] = "%s%d" % (prefix, index)
            nodes.append(node)
            index += 1
    # chain the nodes so edges exist and the pair matrix is non-trivial
    for left, right in zip(nodes, nodes[1:]):
        edges.append({"id": "e_%s_%s" % (left["id"], right["id"]), "source": left["id"], "target": right["id"]})
    return {"nodes": nodes, "edges": edges}


def self_test() -> int:
    cases = []
    source = _fake_graph({"image": 4, "video": 2, "group": 1})

    same = evaluate(source, _fake_graph({"image": 4, "video": 2, "group": 1}), mode="copy_reverse")
    cases.append(("mirror_identity_passes", same["status"] == "PASS"))

    swapped = evaluate(source, _fake_graph({"image": 4, "video": 2, "group": 1}, typed=False), mode="copy_reverse")
    cases.append(("node_type_alias_is_normalised", swapped["status"] == "PASS"))

    over = evaluate(source, _fake_graph({"image": 12, "video": 6, "group": 1}), mode="copy_reverse")
    cases.append(("overbuild_fails", over["status"] == "FAIL" and any(f["code"] == "FIDELITY_OVERBUILD_NODE_TOTAL" for f in over["failures"])))

    under = evaluate(source, _fake_graph({"image": 2, "video": 1, "group": 1}), mode="copy_reverse")
    cases.append(("underbuild_fails", under["status"] == "FAIL" and any(f["code"] == "FIDELITY_NODE_TOTAL" for f in under["failures"])))

    unlinked = evaluate(source, _fake_graph({"image": 4, "video": 2, "group": 1}, lineage=False), mode="copy_reverse")
    cases.append(("mirror_without_lineage_fails", unlinked["status"] == "FAIL" and any(f["code"] == "FIDELITY_NO_LINEAGE" for f in unlinked["failures"])))

    plan_mode = evaluate(source, _fake_graph({"image": 12, "video": 6, "group": 1}, lineage=False), mode="production_build", deliverable="production_plan")
    cases.append(("plan_mode_skips_lineage", plan_mode["lineage"] == "off"))

    empty = evaluate({"nodes": [], "edges": []}, _fake_graph({"image": 1}), mode="copy_reverse")
    cases.append(("empty_source_not_verified", empty["status"] == "NOT_VERIFIED" and empty["failures"][0]["code"] == "SOURCE_GRAPH_UNAVAILABLE"))

    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail", "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return RC_OK if not failed else RC_FAIL


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    parser.add_argument("--plan")
    parser.add_argument("--json-out")
    parser.add_argument("--mode", choices=["source_replica", "copy_reverse", "content_reverse", "film_reverse"], default="source_replica")
    parser.add_argument("--deliverable", choices=["auto", "mirror", "production_plan"], default="auto")
    parser.add_argument("--lineage", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--min-node-ratio", type=float, default=0.95)
    parser.add_argument("--max-node-ratio", type=float, default=1.10)
    parser.add_argument("--min-edge-ratio", type=float, default=0.95)
    parser.add_argument("--max-edge-ratio", type=float, default=1.10)
    parser.add_argument("--min-type-ratio", type=float, default=0.90)
    parser.add_argument("--max-type-ratio", type=float, default=1.10)
    parser.add_argument("--min-group-ratio", type=float, default=0.80)
    parser.add_argument("--max-group-ratio", type=float, default=1.10)
    parser.add_argument("--source-metrics")
    parser.add_argument("--plan-metrics")
    parser.add_argument("--contract")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.source or not args.plan:
        parser.error("--source and --plan are required unless --self-test")

    mode, warnings = normalize_mode(args.mode, "source_replica")
    if args.contract:
        contract = load_json(args.contract)
        contract = contract.get("production_contract", contract)
        for error in mode_errors(contract):
            result = {"mode": mode, "status": "FAIL", "failures": [{"code": error}], "warnings": warnings}
            emit(result, args.json_out)
            return RC_FAIL

    if mode == "content_reverse":
        result = {
            "mode": mode,
            "status": "SKIP",
            "message": "content_reverse is measured against the finished film, not the source production graph.",
            "warnings": warnings,
        }
        emit(result, args.json_out)
        return RC_OK

    result = evaluate(
        load_json(args.source),
        load_json(args.plan),
        mode=mode,
        deliverable=args.deliverable,
        lineage=args.lineage,
        min_node_ratio=args.min_node_ratio,
        max_node_ratio=args.max_node_ratio,
        min_edge_ratio=args.min_edge_ratio,
        max_edge_ratio=args.max_edge_ratio,
        min_type_ratio=args.min_type_ratio,
        max_type_ratio=args.max_type_ratio,
        min_group_ratio=args.min_group_ratio,
        max_group_ratio=args.max_group_ratio,
        source_metrics=load_json(args.source_metrics) if args.source_metrics else None,
        plan_metrics=load_json(args.plan_metrics) if args.plan_metrics else None,
        warnings=warnings,
    )
    emit(result, args.json_out)
    if result["status"] == "PASS":
        return RC_OK
    if result["status"] == "NOT_VERIFIED":
        return RC_EMPTY
    return RC_FAIL


if __name__ == "__main__":
    sys.exit(main())
