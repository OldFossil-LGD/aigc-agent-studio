import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_asset_graph import compile_asset_graph
from scripts.apply_libtv_plan import build_commands
from scripts.compile_production import compile_production
from scripts.compile_production_contract import compile_contract
from scripts.compile_prompt_packages import compile_prompt_packages
from scripts.compile_shot_graph import compile_shot_graph
from scripts.production_capability_gate import evaluate
from scripts.compile_text_input import parse_text_input


class ProductionCompilerTests(unittest.TestCase):
    def test_compile_contract_fills_required_fields(self):
        result = compile_contract({"goal": "两分钟苗族风筝短片", "duration_sec": 120})
        contract = result["production_contract"]
        self.assertEqual(contract["duration_sec"], 120)
        self.assertEqual(contract["production_mode"], "production_build")
        self.assertFalse(contract["delivery"]["ignition_allowed"])
        self.assertTrue(result["assumptions"])

    def test_reused_character_requires_iteration_chain(self):
        contract = {
            "entities": [{"id": "elder", "kind": "character", "reuse_count": 3}],
            "shots": [{"id": "shot_01"}],
        }
        plan = compile_asset_graph(contract)
        self.assertTrue(plan["assets"][0]["requires_iteration"])
        self.assertTrue(plan["iteration_chains"])

    def test_asset_group_uses_real_asset_node_ids(self):
        contract = {"shots": [{"id": "shot_01", "duration_sec": 5}]}
        assets = {
            "assets": [{"id": "elder", "kind": "character", "requires_iteration": True}],
            "iteration_chains": [],
        }
        graph = compile_shot_graph(contract, assets)
        asset_group = next(g for g in graph["groups"] if g["id"] == "group__assets")
        self.assertEqual(
            asset_group["node_ids"],
            ["elder__asset_anchor", "elder__asset_refine_a", "elder__asset_refine_b"],
        )
        asset_edges = [
            edge for edge in graph["edges"] if edge["source"] == "elder__asset_refine_b"
        ]
        self.assertTrue(asset_edges)
        self.assertTrue(all(edge["target"].endswith("candidate_image_A") for edge in asset_edges))

    def test_gate_fails_asset_without_shot_link(self):
        result = evaluate(
            {"production_mode": "production_build", "delivery": {"ignition_allowed": False}},
            {
                "assets": [{"id": "elder", "requires_iteration": False}],
                "iteration_chains": [],
            },
            {"shots": [], "nodes": [], "edges": []},
            [],
        )
        self.assertTrue(any(item["code"] == "MISSING_ASSET_TO_SHOT_LINK" for item in result["failures"]))

    def test_each_shot_has_required_roles(self):
        contract = {"shots": [{"id": "shot_01", "duration_sec": 5, "risk": "high"}]}
        assets = {"assets": []}
        graph = compile_shot_graph(contract, assets)
        roles = {node["role"] for node in graph["nodes"] if node["shot_id"] == "shot_01"}
        required = {
            "storyboard",
            "prompt",
            "scene_ref",
            "identity_ref",
            "composition_ref",
            "candidate_image",
            "refined_image",
            "video_candidate",
            "selection",
            "audio",
            "assembly",
        }
        self.assertTrue(required.issubset(roles))

    def test_video_prompt_has_required_blocks(self):
        contract = {"duration_sec": 120, "visual_style": "写实纪录片"}
        assets = {"assets": []}
        graph = {
            "edges": [
                {"source": "shot_01__scene_ref", "target": "shot_01__video_candidate_A", "purpose": "scene"}
            ],
            "nodes": [
                {
                    "id": "shot_01__video_candidate_A",
                    "role": "video_candidate",
                    "shot_id": "shot_01",
                    "node_type": "video",
                }
            ]
        }
        package = compile_prompt_packages(contract, assets, graph)[0]
        self.assertEqual(package["status"], "READY")
        self.assertIn("continuity", package["blocks"])
        self.assertIn("material_roles", package["blocks"])
        self.assertTrue(any("{{Node" in item for item in package["blocks"]["material_roles"]))

    def test_text_node_command_carries_content(self):
        from scripts.compile_libtv_commands import compile_commands

        graph = {
            "groups": [{"id": "g1", "name": "group", "node_ids": ["t1"]}],
            "nodes": [{"id": "t1", "node_type": "text", "role": "storyboard", "shot_id": "shot_01"}],
            "edges": [],
        }
        prompts = [{"node_id": "t1", "role": "storyboard", "status": "READY", "blocks": {"shot_contract": "x"}}]
        plan = compile_commands(graph, prompts, "P")
        node_command = next(c for c in plan["commands"] if c.get("kind") == "node_create")
        self.assertEqual(node_command["content"], ["shot_contract: x"])

    def test_gate_fails_missing_roles(self):
        result = evaluate(
            {"production_mode": "production_build", "delivery": {"ignition_allowed": False}},
            {"assets": [], "iteration_chains": []},
            {
                "shots": [{"id": "shot_01"}],
                "nodes": [{"id": "shot_01__storyboard", "shot_id": "shot_01", "role": "storyboard"}],
            },
            [],
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "MISSING_SHOT_ROLE" for item in result["failures"]))

    def test_pipeline_writes_all_artifacts_and_passes(self):
        fixture = {
            "goal": "两分钟无源画布生产验收片",
            "duration_sec": 120,
            "production_mode": "production_build",
            "entities": [{"id": "elder", "kind": "character", "reuse_count": 3, "description": "银色宇航服，左脸疤痕"}],
            "shots": [{"id": "shot_01", "duration_sec": 120, "risk": "high"}],
            "delivery": {"ignition_allowed": False},
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = compile_production(fixture, out)
            self.assertEqual(result["gate"]["status"], "PASS")
            for name in [
                "01_production_contract.json",
                "02_asset_graph_plan.json",
                "03_shot_graph_plan.json",
                "04_prompt_packages.jsonl",
                "05_platform_execution_plan.json",
                "06_gate_results.json",
                "07_regression_ledger.json",
                "08_libtv_command_plan.json",
            ]:
                self.assertTrue((out / name).exists(), name)
            plan = json.loads((out / "05_platform_execution_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(all(step["run"] is False for step in plan["steps"]))
            commands = json.loads((out / "08_libtv_command_plan.json").read_text(encoding="utf-8"))
            self.assertFalse(commands["safety"]["run"])
            self.assertTrue(all(command.get("run", False) is False for command in commands["commands"]))
            cli_commands = build_commands(commands, "00000000-0000-0000-0000-000000000000")
            self.assertTrue(cli_commands)
            self.assertTrue(all("--run" not in command for command in cli_commands))

    def test_text_script_parses_shot_lines(self):
        text = "镜头1 5秒 晨雾梯田航拍\n镜头2 6秒 阿婆扎竹篾骨架\n镜头3 4秒 风筝起飞"
        data = parse_text_input(text, duration_sec=15)
        self.assertEqual(len(data["shots"]), 3)
        self.assertEqual(data["shots"][0]["id"], "shot_01")
        self.assertIn("晨雾", data["shots"][0]["description"])

    def test_text_pipeline_writes_command_plan(self):
        text = "镜头1 60秒 一个人在村寨放飞风筝\n镜头2 60秒 风筝升空"
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "script.txt"
            out = Path(tmp) / "out"
            inp.write_text(text, encoding="utf-8")
            data = parse_text_input(text, goal="两分钟测试片", duration_sec=120)
            result = compile_production(data, out)
            self.assertTrue((out / "08_libtv_command_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
