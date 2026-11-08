import json
import tempfile
import unittest
from pathlib import Path

import scripts.production_regression as production_regression
from scripts.compile_production import compile_production
from scripts.production_regression import _fixture, _negative_fixture, run_regression


class ProductionRegressionTests(unittest.TestCase):
    def test_run_regression_passes_with_blocked_negative(self):
        result = run_regression()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["no_ignition"])

        positive = result["positive"]
        negative = result["negative"]

        self.assertEqual(positive["expected"], "PASS")
        self.assertEqual(positive["status"], "PASS")
        self.assertEqual(positive["gate_status"], "PASS")
        self.assertEqual(positive["failure_codes"], [])
        self.assertEqual(positive["artifact_issues"], [])
        self.assertFalse(positive["platform_run"])
        self.assertFalse(positive["command_run"])

        self.assertEqual(negative["expected"], "FAIL")
        self.assertEqual(negative["status"], "PASS")
        self.assertEqual(negative["gate_status"], "FAIL")
        self.assertIn("PROMPT_UNRESOLVED", negative["failure_codes"])
        self.assertEqual(negative["artifact_issues"], [])
        self.assertFalse(negative["platform_run"])
        self.assertFalse(negative["command_run"])

    def test_regression_exercises_negative_case(self):
        original = production_regression._negative_fixture
        production_regression._negative_fixture = production_regression._fixture
        try:
            result = run_regression()
        finally:
            production_regression._negative_fixture = original
        self.assertEqual(result["status"], "FAIL")

    def test_valid_compile_preserves_entity_description_and_no_run(self):
        fixture = _fixture()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = compile_production(fixture, out)
            self.assertEqual(result["gate"]["status"], "PASS")

            prompt_rows = [
                json.loads(line)
                for line in (out / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            asset_prompts = [row for row in prompt_rows if row["role"] in {"asset_anchor", "asset_refine"}]
            self.assertTrue(
                any("银发老人" in json.dumps(row["blocks"], ensure_ascii=False) for row in asset_prompts)
            )

            platform = json.loads((out / "05_platform_execution_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(platform["steps"])
            self.assertTrue(all(step["run"] is False for step in platform["steps"]))

            commands = json.loads((out / "08_libtv_command_plan.json").read_text(encoding="utf-8"))
            self.assertFalse(commands["safety"]["run"])
            self.assertTrue(all(command["run"] is False for command in commands["commands"]))
            self.assertTrue(
                any("银发老人" in str(command["prompt"]) for command in commands["commands"] if "prompt" in command)
            )

    def test_missing_entity_description_is_rejected(self):
        fixture = _negative_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = compile_production(fixture, out)
            self.assertNotEqual(result["gate"]["status"], "PASS")

            unresolved = []
            for line in (out / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    unresolved.extend(json.loads(line).get("unresolved", []))
            self.assertTrue(
                any("missing_entity_description" in item or "missing_entity_identity" in item for item in unresolved)
            )
            self.assertTrue(
                any(
                    item.get("code") in {"PROMPT_UNRESOLVED", "PROMPT_NOT_READY"}
                    for item in result["gate"]["failures"]
                )
            )

    def test_missing_artifact_fails_regression(self):
        original = production_regression.compile_production

        def faulty(data, out):
            result = original(data, out)
            (out / "03_shot_graph_plan.json").unlink()
            return result

        production_regression.compile_production = faulty
        try:
            result = run_regression()
        finally:
            production_regression.compile_production = original
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any("03_shot_graph_plan.json" in issue for case in (result["positive"], result["negative"]) for issue in case["artifact_issues"])
        )

    def test_unsafe_negative_platform_plan_fails_no_ignition(self):
        original = production_regression.compile_production

        def unsafe(data, out):
            result = original(data, out)
            is_negative = any(
                entity.get("id") == "elder" and "description" not in entity
                for entity in data.get("entities", [])
            )
            if is_negative:
                path = out / "05_platform_execution_plan.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload["steps"]:
                    payload["steps"][0]["run"] = True
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

        production_regression.compile_production = unsafe
        try:
            result = run_regression()
        finally:
            production_regression.compile_production = original
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["no_ignition"])
        self.assertFalse(result["positive"]["platform_run"])
        self.assertFalse(result["positive"]["command_run"])
        self.assertTrue(result["negative"]["platform_run"])
        self.assertFalse(result["negative"]["command_run"])

    def test_unsafe_negative_command_plan_fails_no_ignition(self):
        original = production_regression.compile_production

        def unsafe(data, out):
            result = original(data, out)
            is_negative = any(
                entity.get("id") == "elder" and "description" not in entity
                for entity in data.get("entities", [])
            )
            if is_negative:
                path = out / "08_libtv_command_plan.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["safety"]["run"] = True
                if payload["commands"]:
                    payload["commands"][0]["run"] = True
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

        production_regression.compile_production = unsafe
        try:
            result = run_regression()
        finally:
            production_regression.compile_production = original
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["no_ignition"])
        self.assertFalse(result["positive"]["platform_run"])
        self.assertFalse(result["positive"]["command_run"])
        self.assertFalse(result["negative"]["platform_run"])
        self.assertTrue(result["negative"]["command_run"])


if __name__ == "__main__":
    unittest.main()
