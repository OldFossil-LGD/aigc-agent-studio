import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


class WiringIntegrityTests(unittest.TestCase):
    def run_plan(self, doc, *args):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "plan.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            return subprocess.run([sys.executable, str(ROOT / "scripts/wiring_plan.py"), str(source), *args], capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=5)

    def test_report_rejects_missing_parent_endpoint(self):
        doc = {"props": [{"id": "P", "name": "P"}], "assets": [{"asset_id": "A", "kind": "prop", "subject": "P", "role": "closeup", "parent": "MISSING"}]}
        result = self.run_plan(doc, "--report")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("MISSING", result.stdout)

    def test_explain_cycle_returns_failure_instead_of_hanging(self):
        doc = {"props": [{"id": "P1", "name": "P1"}, {"id": "P2", "name": "P2"}], "assets": [{"asset_id": "A", "kind": "prop", "subject": "P1", "role": "closeup", "parent": "B"}, {"asset_id": "B", "kind": "prop", "subject": "P2", "role": "closeup", "parent": "A"}]}
        result = self.run_plan(doc, "--explain", "资产_P1_近距版", "--json")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("有环", result.stdout)

    def test_direct_explain_is_bounded_for_cyclic_input(self):
        code = "import sys;sys.path.insert(0,sys.argv[1]);import wiring_plan,json;print(json.dumps(wiring_plan.explain({'a':{},'b':{}},[('a','b','derive',''),('b','a','derive','')],'a')))"
        result = subprocess.run([sys.executable, "-c", code, str(ROOT / "scripts")], capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["cycle"], "a")


if __name__ == "__main__":
    unittest.main()
