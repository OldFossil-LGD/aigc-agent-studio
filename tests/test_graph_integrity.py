import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_production_contract import compile_contract
from scripts.compile_asset_graph import compile_asset_graph
from scripts.compile_shot_graph import compile_shot_graph
from scripts.compile_prompt_packages import compile_prompt_packages
from scripts.production_capability_gate import evaluate


def build_plan(fixture=None, mutate_graph=None, mutate_contract=None, dedupe_graph=False):
    if fixture is None:
        fixture = {
            "goal": "合成审计输入",
            "duration_sec": 10,
            "aspect_ratio": "16:9",
            "entities": [{"id": "hero", "name": "航天员", "kind": "character", "description": "银色宇航服，左脸疤痕", "reuse_count": 1}],
            "shots": [{"id": "s1", "duration_sec": 10, "description": "航天员缓慢转身"}],
            "delivery": {"ignition_allowed": False},
        }
    data = copy.deepcopy(fixture)
    contract_result = compile_contract(data)
    contract = contract_result["production_contract"]
    if mutate_contract is not None:
        mutate_contract(contract)
    assets = compile_asset_graph(contract)
    graph = compile_shot_graph(contract, assets)
    if mutate_graph is not None:
        mutate_graph(graph, contract, assets)
    if dedupe_graph:
        seen = set()
        unique_nodes = []
        for node in graph.get("nodes") or []:
            nid = node.get("id") if isinstance(node, dict) else None
            if nid in seen:
                continue
            seen.add(nid)
            unique_nodes.append(node)
        graph["nodes"] = unique_nodes
    prompts = compile_prompt_packages(contract, assets, graph)
    return contract, assets, graph, prompts


class GraphIntegrityTests(unittest.TestCase):
    def test_normal_plan_pass(self):
        contract, assets, graph, prompts = build_plan()
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["checks"]["graph_integrity"])
        self.assertFalse(result["checks"]["graph_integrity_skipped"])

    def test_dangling_source_fails(self):
        def mutate(graph, contract, assets):
            graph["edges"].append({"source": "NONEXISTENT", "target": "global__final_composite", "purpose": "invalid_probe"})
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("DANGLING_EDGE", codes)

    def test_dangling_target_fails(self):
        def mutate(graph, contract, assets):
            graph["edges"].append({"source": "s1__storyboard", "target": "NONEXISTENT", "purpose": "invalid_probe"})
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("DANGLING_EDGE", codes)

    def test_duplicate_node_id_fails(self):
        def mutate(graph, contract, assets):
            if graph.get("nodes"):
                graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("DUPLICATE_NODE_ID", codes)

    def test_invalid_node_id_fails(self):
        def mutate(graph, contract, assets):
            if graph.get("nodes"):
                graph["nodes"][0]["id"] = ""
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("INVALID_NODE_ID", codes)

    def test_duplicate_contract_shot_id_even_if_graph_deduped(self):
        def mutate_contract(contract):
            if contract.get("shots"):
                contract["shots"].append(copy.deepcopy(contract["shots"][0]))
        contract, assets, graph, prompts = build_plan(mutate_contract=mutate_contract, dedupe_graph=True)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("DUPLICATE_SHOT_ID", codes)

    def test_invalid_contract_shot_id_fails(self):
        def mutate_contract(contract):
            if contract.get("shots"):
                contract["shots"][0]["id"] = "   "
        contract, assets, graph, prompts = build_plan(mutate_contract=mutate_contract)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("INVALID_SHOT_ID", codes)

    def test_duplicate_contract_entity_id_even_if_graph_deduped(self):
        def mutate_contract(contract):
            if contract.get("entities"):
                contract["entities"].append(copy.deepcopy(contract["entities"][0]))
        contract, assets, graph, prompts = build_plan(mutate_contract=mutate_contract, dedupe_graph=True)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("DUPLICATE_ENTITY_ID", codes)

    def test_invalid_contract_entity_id_fails(self):
        def mutate_contract(contract):
            if contract.get("entities"):
                contract["entities"][0]["id"] = None
        contract, assets, graph, prompts = build_plan(mutate_contract=mutate_contract)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("INVALID_ENTITY_ID", codes)

    def test_simple_cycle_fails(self):
        def mutate(graph, contract, assets):
            graph["edges"].append({"source": "s1__prompt", "target": "s1__storyboard", "purpose": "invalid_probe"})
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("GRAPH_CYCLE", codes)

    def test_self_loop_fails(self):
        def mutate(graph, contract, assets):
            graph["edges"].append({"source": "s1__storyboard", "target": "s1__storyboard", "purpose": "invalid_probe"})
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("GRAPH_CYCLE", codes)

    def test_empty_shot_plan_pass(self):
        fixture = {
            "goal": "空镜测试",
            "duration_sec": 10,
            "aspect_ratio": "16:9",
            "entities": [{"id": "scene_asset", "kind": "scene", "description": "晨雾梯田", "reuse_count": 1}],
            "shots": [{"id": "s1", "duration_sec": 10, "shot_kind": "empty", "description": "空镜"}],
            "delivery": {"ignition_allowed": False},
        }
        contract, assets, graph, prompts = build_plan(fixture=fixture)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["checks"]["graph_integrity"])

    def test_silent_shot_plan_pass(self):
        fixture = {
            "goal": "静默测试",
            "duration_sec": 10,
            "aspect_ratio": "16:9",
            "entities": [{"id": "scene_asset", "kind": "scene", "description": "晨雾梯田", "reuse_count": 1}],
            "shots": [{"id": "s1", "duration_sec": 10, "shot_kind": "silent", "description": "静默镜头"}],
            "delivery": {"ignition_allowed": False},
        }
        contract, assets, graph, prompts = build_plan(fixture=fixture)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["checks"]["graph_integrity"])

    def test_mirror_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source_graph.json"
            src.write_text(json.dumps({"nodes": [{"id": "n1", "type": "text"}], "edges": []}, ensure_ascii=False), encoding="utf-8")
            contract = {
                "mode": "production_build",
                "deliverable": "mirror",
                "source_graph_path": str(src),
                "duration_sec": 10,
            }
            assets = {"assets": [], "iteration_chains": []}
            graph = {"nodes": [{"id": "n1", "source_node_id": "n1", "node_type": "text", "role": "mirror"}], "edges": [], "deliverable": "mirror"}
            prompts = []
            result = evaluate(contract, assets, graph, prompts)
            self.assertEqual(result["status"], "PASS")
            self.assertIsNone(result["checks"]["graph_integrity"])
            self.assertTrue(result["checks"]["graph_integrity_skipped"])
            self.assertTrue(any(w.get("code") == "MIRROR_GRAPH_INTEGRITY_SKIPPED" for w in result["warnings"]))

    def test_dict_node_id_fails(self):
        contract, assets, graph, prompts = build_plan()
        if graph.get("nodes"):
            graph["nodes"][0]["id"] = {"invalid": "id"}
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("INVALID_NODE_ID", codes)

    def test_dict_edge_source_fails(self):
        def mutate(graph, contract, assets):
            graph["edges"].append({"source": {"invalid": "source"}, "target": "global__final_composite", "purpose": "invalid_probe"})
        contract, assets, graph, prompts = build_plan(mutate_graph=mutate)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["graph_integrity"])
        codes = {f["code"] for f in result["failures"]}
        self.assertIn("DANGLING_EDGE", codes)

    def test_skeleton_only_skipped(self):
        def mutate_contract(contract):
            contract["mode"] = "content_reverse"
            contract["production_mode"] = "content_reverse"
            contract["skeleton_only"] = True
            contract["source_film"] = "SYNTHETIC"
            contract["source_access"] = "public_media"
            contract["work_profile"] = {"fixture_only": True}
        contract, assets, graph, prompts = build_plan(mutate_contract=mutate_contract)
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(result["checks"]["graph_integrity"])
        self.assertTrue(result["checks"]["graph_integrity_skipped"])


if __name__ == "__main__":
    unittest.main()
