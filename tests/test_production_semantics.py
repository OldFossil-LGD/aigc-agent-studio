import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_production_contract import compile_contract
from scripts.compile_asset_graph import compile_asset_graph
from scripts.compile_shot_graph import compile_shot_graph
from scripts.compile_prompt_packages import compile_prompt_packages
from scripts.production_capability_gate import evaluate
from scripts.compile_production import compile_production
from scripts.compile_libtv_commands import compile_commands


class ProductionSemanticsTests(unittest.TestCase):
    def test_single_shot_duration_and_ratio_propagate_to_commands(self):
        fixture = {
            "goal": "17秒竖屏测试",
            "duration_sec": 17,
            "aspect_ratio": "9:16",
            "production_mode": "production_build",
            "entities": [{"id": "hero", "kind": "character", "reuse_count": 1, "description": "红袍老僧"}],
            "shots": [{"id": "shot_01", "duration_sec": 17, "risk": "medium"}],
            "delivery": {"ignition_allowed": False},
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = compile_production(fixture, out)
            self.assertEqual(result["gate"]["status"], "PASS")
            contract = result["contract"]
            self.assertEqual(contract["duration_sec"], 17)
            self.assertEqual(contract["aspect_ratio"], "9:16")
            for node in result["graph"]["nodes"]:
                if node.get("node_type") == "video":
                    self.assertEqual(node["settings"]["duration"], 17)
                    self.assertEqual(node["settings"]["ratio"], "9:16")
            commands = json.loads((out / "08_libtv_command_plan.json").read_text(encoding="utf-8"))
            for command in commands["commands"]:
                if command.get("kind") == "node_create" and command.get("node_type") == "video":
                    self.assertEqual(command["settings"]["duration"], 17)
                    self.assertEqual(command["settings"]["ratio"], "9:16")

    def test_invalid_durations_are_rejected(self):
        with self.assertRaises(ValueError):
            compile_contract({"goal": "x", "duration_sec": 0})
        with self.assertRaises(ValueError):
            compile_contract({"goal": "x", "duration_sec": -3})
        with self.assertRaises(ValueError):
            compile_contract({"goal": "x", "shots": [{"id": "s1", "duration_sec": 0}]})

    def test_total_duration_mismatch_is_blocking(self):
        result = evaluate(
            {"production_mode": "production_build", "duration_sec": 120, "aspect_ratio": "16:9",
             "shots": [{"id": "shot_01", "duration_sec": 5}], "delivery": {"ignition_allowed": False}},
            {"assets": [], "iteration_chains": []},
            {"shots": [{"id": "shot_01", "duration_sec": 5}], "nodes": [], "edges": []},
            [],
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("DURATION" in f["code"] and "MISMATCH" in f["code"] for f in result["failures"]))

    def test_asset_identity_changes_prompt_body(self):
        def build(description):
            contract = {
                "goal": "test",
                "duration_sec": 10,
                "aspect_ratio": "16:9",
                "entities": [{"id": "hero", "kind": "character", "name": "hero", "description": description, "reuse_count": 1}],
                "shots": [{"id": "shot_01", "duration_sec": 10}],
            }
            assets = compile_asset_graph(contract)
            graph = compile_shot_graph(contract, assets)
            return compile_prompt_packages(contract, assets, graph)
        first = build("银色宇航服，左脸疤痕")
        second = build("木制念珠，右手缺指")
        first_identity = next(p["blocks"]["identity"] for p in first if p["role"] == "asset_anchor")
        second_identity = next(p["blocks"]["identity"] for p in second if p["role"] == "asset_anchor")
        self.assertNotEqual(first_identity, second_identity)
        self.assertIn("银色宇航服", first_identity)
        self.assertIn("木制念珠", second_identity)

    def test_missing_entity_description_is_unresolved_not_ready(self):
        contract = {
            "goal": "test",
            "duration_sec": 10,
            "aspect_ratio": "16:9",
            "entities": [{"id": "hero", "kind": "character", "name": "hero", "reuse_count": 1}],
            "shots": [{"id": "shot_01", "duration_sec": 10}],
        }
        assets = compile_asset_graph(contract)
        graph = compile_shot_graph(contract, assets)
        packages = compile_prompt_packages(contract, assets, graph)
        asset_pkg = next(p for p in packages if p["role"] == "asset_anchor")
        self.assertEqual(asset_pkg["status"], "INCOMPLETE")
        self.assertTrue(asset_pkg["unresolved"])

    def test_empty_blocks_are_not_green(self):
        package = {
            "node_id": "n",
            "role": "video_candidate",
            "node_type": "video",
            "blocks": {},
            "missing_blocks": [],
            "status": "READY",
            "unresolved": [],
        }
        res = evaluate(
            {"production_mode": "production_build", "duration_sec": 10, "aspect_ratio": "16:9",
             "shots": [{"id": "shot_01", "duration_sec": 10}], "delivery": {"ignition_allowed": False}},
            {"assets": [], "iteration_chains": []},
            {"shots": [{"id": "shot_01"}], "nodes": [{"id": "n", "role": "video_candidate", "shot_id": "shot_01", "node_type": "video"}], "edges": []},
            [package],
        )
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(f["code"] in {"PROMPT_BLOCK_EMPTY", "PROMPT_STATUS_INCONSISTENT"} for f in res["failures"]))
        self.assertFalse(res["checks"]["prompt_packages"])

    def test_missing_package_makes_checks_false(self):
        res = evaluate(
            {"production_mode": "production_build", "duration_sec": 10, "aspect_ratio": "16:9",
             "shots": [{"id": "shot_01", "duration_sec": 10}], "delivery": {"ignition_allowed": False}},
            {"assets": [], "iteration_chains": []},
            {"shots": [{"id": "shot_01"}], "nodes": [{"id": "n", "role": "video_candidate", "shot_id": "shot_01", "node_type": "video"}], "edges": []},
            [],
        )
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(f["code"] == "MISSING_PROMPT_PACKAGE" for f in res["failures"]))
        self.assertFalse(res["checks"]["prompt_packages"])

    def test_mode_alias_normalized_and_schema_modes_canonical(self):
        from scripts.reverse_contract import normalize_mode
        mode, warnings = normalize_mode("film_reverse")
        self.assertEqual(mode, "content_reverse")
        self.assertTrue(any("DEPRECATED_MODE" in w for w in warnings))

    def test_draft_status_when_questions_present(self):
        result = compile_contract({"goal": "test", "mode": "source_replica"})
        self.assertEqual(result["status"], "DRAFT")
        self.assertEqual(result["production_contract"]["status"], "DRAFT")
        self.assertTrue(result["questions"])

    def test_ready_status_when_no_questions(self):
        result = compile_contract({"goal": "test"})
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["production_contract"]["status"], "READY")


if __name__ == "__main__":
    unittest.main()