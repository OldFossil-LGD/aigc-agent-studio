# -*- coding: utf-8 -*-
"""P0-01 回归：video→video 引用边必须返回三态，且绝不抛 NameError。

对应实施任务书 T-P0-01 / 审查报告 P0-01。
四种情形：合法资源 / 禁止的生成产物 / action 不可知 / 端点不存在。
"""
import unittest

from scripts.graph_plan_lint import check_edges


def _plan(edges, nodes=None):
    return {"nodes": nodes or [
        {"node_id": "A", "node_type": "video", "role": "shot", "action": "video_resource"},
        {"node_id": "B", "node_type": "video", "role": "shot", "action": "video_resource"},
    ], "edges": edges}


def codes(rows):
    return [r[1] for r in rows]


class VideoReferenceActionTest(unittest.TestCase):
    def test_resource_is_pass(self):
        rows = check_edges(_plan([{"source_id": "A", "target_id": "B", "kind": "reference"}]))
        self.assertIn("EDGE_V2V_RESOURCE", codes(rows))
        self.assertNotIn("FAIL", [r[0] for r in rows])

    def test_generate_is_fail(self):
        nodes = [{"node_id": "A", "node_type": "video", "role": "shot", "action": "video_generate"},
                 {"node_id": "B", "node_type": "video", "role": "shot", "action": "video_resource"}]
        rows = check_edges(_plan([{"source_id": "A", "target_id": "B", "kind": "reference"}], nodes))
        self.assertIn("EDGE_V2V_REF_FORBIDDEN", codes(rows))
        self.assertIn("FAIL", [r[0] for r in rows])

    def test_unknown_action_is_undet(self):
        nodes = [{"node_id": "A", "node_type": "video", "role": "shot"},
                 {"node_id": "B", "node_type": "video", "role": "shot"}]
        rows = check_edges(_plan([{"source_id": "A", "target_id": "B", "kind": "reference"}], nodes))
        self.assertIn("EDGE_V2V_UNDETERMINED", codes(rows))
        self.assertIn("UNDET", [r[0] for r in rows])

    def test_action_from_nested_params(self):
        nodes = [{"node_id": "A", "node_type": "video", "role": "shot",
                  "params": {"action": "video_resource"}},
                 {"node_id": "B", "node_type": "video", "role": "shot"}]
        rows = check_edges(_plan([{"source_id": "A", "target_id": "B", "kind": "reference"}], nodes))
        self.assertIn("EDGE_V2V_RESOURCE", codes(rows))

    def test_dangling_does_not_raise(self):
        rows = check_edges(_plan([{"source_id": "X", "target_id": "Y", "kind": "reference"}]))
        self.assertIn("EDGE_DANGLING", codes(rows))
        self.assertIn("FAIL", [r[0] for r in rows])

    def test_non_reference_video_edge_still_passes(self):
        rows = check_edges(_plan([{"source_id": "A", "target_id": "B", "kind": "dependency"}]))
        self.assertNotIn("FAIL", [r[0] for r in rows])


if __name__ == "__main__":
    unittest.main()
