# -*- coding: utf-8 -*-
"""P1 回归：Workflow Graph IR v2（构建 / 校验 / 落线闸门 / 差异）。

对应任务书 T-P1-02/03/04/05 与不变量 I-03/I-04/I-05。
"""
import copy
import unittest

from scripts.compile_libtv_commands import compile_commands
from scripts.workflow_graph_ir import (VERSION, build_legacy_v1, diff, edge_references,
                                       linkable, path, summary, upstream, validate)


def legacy():
    return {
        "nodes": [
            {"id": "shot_01__prompt", "node_type": "text", "role": "prompt"},
            {"id": "shot_01__image", "node_type": "image", "role": "candidate_image"},
            {"id": "shot_01__sel", "node_type": "text", "role": "selection"},
        ],
        "edges": [
            {"source": "shot_01__prompt", "target": "shot_01__image", "purpose": "reference"},
            {"source": "shot_01__image", "target": "shot_01__sel", "purpose": "dependency"},
        ],
        "groups": [],
    }


class GraphIRTest(unittest.TestCase):
    def test_version_and_kinds(self):
        gir = build_legacy_v1(legacy())
        self.assertEqual(gir["schema_version"], VERSION)
        self.assertEqual([e["kind"] for e in gir["edges"]], ["data_reference", "control_dependency"])

    def test_only_data_reference_is_linkable(self):
        gir = build_legacy_v1(legacy())
        self.assertTrue(linkable(gir["edges"][0])[0])
        ok, reason = linkable(gir["edges"][1])
        self.assertFalse(ok)
        self.assertIn("NOT_A_DATA_REFERENCE", reason)

    def test_unknown_purpose_is_lossy(self):
        g = legacy()
        g["edges"][0]["purpose"] = "mystery"
        gir = build_legacy_v1(g)
        self.assertEqual(gir["edges"][0]["kind"], "unknown")
        self.assertTrue(gir["loss_report"])

    def test_validate_catches_dangling_and_dup(self):
        gir = build_legacy_v1(legacy())
        bad = copy.deepcopy(gir)
        bad["edges"][0]["target"]["node_uid"] = "missing"
        self.assertTrue(any(i["code"] == "GRAPH_EDGE_DANGLING" for i in validate(bad)))
        dup = copy.deepcopy(gir)
        dup["edges"].append(copy.deepcopy(dup["edges"][0]))
        self.assertTrue(any(i["code"] == "GRAPH_DUPLICATE_EDGE" for i in validate(dup)))

    def test_unknown_port_is_warn_not_pass(self):
        gir = build_legacy_v1(legacy())
        gir["edges"][0]["target"]["port_id"] = None
        issues = validate(gir)
        self.assertTrue(any(i["code"] == "GRAPH_TARGET_PORT_UNKNOWN" for i in issues))
        self.assertFalse(any(i["severity"] == "ERROR" for i in issues))

    def test_diff_tracks_reference_order(self):
        gir = build_legacy_v1(legacy())
        changed = copy.deepcopy(gir)
        changed["edges"][0]["reference_order"] = 1
        self.assertTrue(diff(gir, changed)["reference_order_changed"])

    def test_analyzer_traversal(self):
        gir = build_legacy_v1(legacy())
        self.assertEqual(upstream(gir, "shot_01__sel"), ["shot_01__image"])
        self.assertEqual(path(gir, "shot_01__prompt", "shot_01__sel"),
                         ["shot_01__prompt", "shot_01__image", "shot_01__sel"])
        self.assertTrue(edge_references(gir, "shot_01__image"))
        # 端口未证实时不假装知道槽位（I-04）
        self.assertEqual(edge_references(gir, "shot_01__image", "reference_image"), [])

    def test_unknown_platform_type_has_no_ports(self):
        g = {"nodes": [{"id": "a1", "node_type": "audio", "role": "audio"}], "edges": [], "groups": []}
        gir = build_legacy_v1(g)
        self.assertEqual(gir["nodes"][0]["input_ports"], [])
        self.assertTrue(any(l["status"] == "UNKNOWN" for l in gir["loss_report"]))

    def test_summary_counts(self):
        s = summary(build_legacy_v1(legacy()))
        self.assertEqual((s["nodes"], s["edges"]), (3, 2))

    def test_compile_links_only_data_reference(self):
        """I-05：逻辑依赖不得变成物理连线。"""
        graph = legacy()
        out = compile_commands(graph, [])
        links = [c for c in out["commands"] if c["kind"] == "node_link"]
        self.assertEqual(len(links), 1, links)
        self.assertEqual(links[0]["edge_kind"], "data_reference")
        self.assertEqual(len(out["skipped_links"]), 1)
        self.assertEqual(out["skipped_links"][0]["kind"], "control_dependency")


if __name__ == "__main__":
    unittest.main()
