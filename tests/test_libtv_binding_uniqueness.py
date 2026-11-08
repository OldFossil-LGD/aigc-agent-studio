# -*- coding: utf-8 -*-
"""P0-02 回归：逻辑 ID → LibTV 平台名必须一一对应，引用与建图同名。

对应实施任务书 T-P0-02：`shot__a` 与 `shot_a` 曾落成同一个画布名。
"""
import unittest

from scripts.compile_libtv_commands import compile_commands


def _graph(prompt_blocks=None):
    nodes = [
        {"id": "shot__a", "node_type": "text", "role": "prompt", "shot_id": "shot_a"},
        {"id": "shot_a", "node_type": "text", "role": "prompt", "shot_id": "shot_a"},
        {"id": "shot__a__image", "node_type": "image", "role": "candidate_image", "shot_id": "shot_a"},
    ]
    edges = [{"source": "shot__a", "target": "shot__a__image", "purpose": "reference"},
             {"source": "shot_a", "target": "shot__a__image", "purpose": "reference"}]
    prompts = [{"node_id": "shot__a", "role": "prompt", "status": "READY",
                "blocks": prompt_blocks or {"visual": '见 {{Node "shot__a__image"}}'}}]
    return {"nodes": nodes, "edges": edges, "groups": [{"id": "g1", "name": "G1",
                                                       "node_ids": ["shot__a", "shot_a", "shot__a__image"]}]}, prompts


class BindingUniquenessTest(unittest.TestCase):
    def test_collision_produces_distinct_names(self):
        graph, prompts = _graph()
        out = compile_commands(graph, prompts)
        names = [c["name"] for c in out["commands"] if c["kind"] == "node_create"]
        self.assertEqual(len(names), len(set(names)), names)

    def test_binding_map_is_complete_and_injective(self):
        graph, prompts = _graph()
        out = compile_commands(graph, prompts)
        bm = out["binding_map"]
        self.assertEqual(set(bm), {"shot__a", "shot_a", "shot__a__image"})
        self.assertEqual(len(set(bm.values())), len(bm), bm)

    def test_compile_is_deterministic(self):
        graph, prompts = _graph()
        a = compile_commands(graph, prompts)
        b = compile_commands(graph, prompts)
        self.assertEqual(a["binding_map"], b["binding_map"])
        self.assertEqual([c.get("name") for c in a["commands"]], [c.get("name") for c in b["commands"]])

    def test_prompt_reference_uses_platform_name(self):
        graph, prompts = _graph()
        out = compile_commands(graph, prompts)
        bm = out["binding_map"]
        prompt_cmd = [c for c in out["commands"] if c["kind"] == "node_create" and c["name"] == bm["shot__a"]][0]
        self.assertIn('{{Node "%s"}}' % bm["shot__a__image"], prompt_cmd["prompt"])
        self.assertNotIn("shot__a__image\"", prompt_cmd["prompt"].replace('{{Node "%s"}}' % bm["shot__a__image"], ""))

    def test_links_point_at_existing_created_names(self):
        graph, prompts = _graph()
        out = compile_commands(graph, prompts)
        created = {c["name"] for c in out["commands"] if c["kind"] == "node_create"}
        for c in out["commands"]:
            if c["kind"] == "node_link":
                self.assertIn(c["left"], created)
                self.assertIn(c["target"], created)

    def test_unique_ids_keep_readable_name(self):
        graph = {"nodes": [{"id": "shot_01__prompt", "node_type": "text", "role": "prompt"}],
                 "edges": [], "groups": []}
        out = compile_commands(graph, [])
        self.assertEqual(out["binding_map"]["shot_01__prompt"], "shot_01_prompt")


if __name__ == "__main__":
    unittest.main()
