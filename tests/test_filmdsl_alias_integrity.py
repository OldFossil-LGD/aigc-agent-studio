import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import filmdsl_bridge

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(filmdsl_bridge.FIXTURES) / "base"


class FilmDSLAliasTests(unittest.TestCase):
    def document(self):
        art = filmdsl_bridge.load_artifacts(str(FIXTURE))
        doc, issues = filmdsl_bridge.export(art)
        self.assertFalse([row for row in issues if row["level"] == "fail"])
        return json.loads(json.dumps(doc)), art

    def test_shots_only_tampering_fails_actual_check_cli(self):
        doc, _ = self.document()
        doc["shots"][0]["narrative_layer"]["narrative_action"] = "UNRELATED_REWRITE"
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "view.json"
            source.write_text(json.dumps(doc), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/filmdsl_bridge.py"), "check", "--filmdsl", str(source), "--artifacts", str(FIXTURE)], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("DROPPED_FIELD", result.stdout)

    def test_conflicting_aliases_fail_even_without_artifacts(self):
        for field in ["clips", "shots"]:
            doc, _ = self.document()
            doc[field] = []
            issues = filmdsl_bridge.validate(doc, None)
            self.assertIn("DROPPED_FIELD", [row["code"] for row in issues])

    def test_single_alias_historical_documents_still_validate(self):
        for removed in ["clips", "shots"]:
            doc, art = self.document()
            del doc[removed]
            self.assertFalse([row for row in filmdsl_bridge.validate(doc, art) if row["level"] == "fail"])


if __name__ == "__main__":
    unittest.main()
