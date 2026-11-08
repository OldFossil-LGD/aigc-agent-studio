import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import libtv_orchestrate as orch


class OrchestratorPlanningTests(unittest.TestCase):
    def video(self):
        return {"id": "v", "nodeType": "video", "run": True, "prompt": "fixture", "params": {"model": "A", "count": 3, "settings": {"duration": 4, "enableSound": "off"}}}

    def compile(self, nodes, contract):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name, data in (("spec", {"project_id": "offline_fixture", "nodes": nodes}), ("contract", contract), ("prices", {"video": {"per_second": 2}})):
                (folder / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
            with patch.dict(os.environ, {"ORCH_PRICES": str(folder / "prices.json")}), contextlib.redirect_stdout(io.StringIO()):
                rc = orch.cmd_compile(["--spec", str(folder / "spec.json"), "--contract", str(folder / "contract.json"), "--approve", "--out", str(folder / "plan.json")])
            return rc, json.loads((folder / "plan.json").read_text(encoding="utf-8"))

    def test_video_budget_uses_node_count(self):
        self.assertEqual(orch.price_of(self.video(), {"video": {"per_second": 2, "count": 7}}), 24)

    def test_reference_bounds_use_selected_model_contract(self):
        node = self.video()
        node.update(prompt="fixture {{ref}}", refs=["ref"])
        node["params"]["modeType"] = "mixed2video"
        contract = {"models": {"A": {"properties": {"modeType": {"items": {"mixed2video": [0, 0]}}}}, "B": {"properties": {"modeType": {"items": {"mixed2video": [0, 2]}}}}}}
        findings = orch.check_node(node, contract, "offline_fixture", False, {"ref": "image", "v": "video"})
        self.assertTrue(any(x["code"] == "K23" and x["level"] == "FAIL" for x in findings))
        node["params"]["model"] = "B"
        self.assertFalse(any(x["code"] == "K23" for x in orch.check_node(node, contract, "offline_fixture", False, {"ref": "image", "v": "video"})))

    def test_contract_failure_keeps_paid_gate_closed(self):
        node = self.video()
        node["params"]["settings"]["duration"] = 100
        rc, plan = self.compile([node], {"properties": {"duration": {"min": 1, "max": 30, "step": 1}}})
        self.assertEqual(rc, orch.RC_FAIL)
        self.assertTrue(plan["gate"]["approved"])
        self.assertFalse(plan["gate"]["paid_released"])

    def test_cycle_keeps_paid_gate_closed(self):
        node = self.video()
        node.update(refs=["v"], prompt="fixture {{v}}")
        rc, plan = self.compile([node], {})
        self.assertEqual(rc, orch.RC_FAIL)
        self.assertFalse(plan["gate"]["paid_released"])

    def test_valid_approved_plan_retains_release(self):
        rc, plan = self.compile([self.video()], {"properties": {"duration": {"min": 1, "max": 30, "step": 1}}})
        self.assertNotEqual(rc, orch.RC_FAIL)
        self.assertTrue(plan["gate"]["paid_released"])
        self.assertEqual(plan["budget"]["total"], 24)


if __name__ == "__main__":
    unittest.main()
