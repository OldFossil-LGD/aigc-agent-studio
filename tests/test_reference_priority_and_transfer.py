import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cap_image_refs
import cross_work_transfer


class ReferencePriorityTests(unittest.TestCase):
    def test_versioned_character_keeps_priority_at_cap(self):
        for character_id in ["C1", "C1__v2"]:
            with self.subTest(character_id=character_id), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                source = folder / "graph.json"
                assets = folder / "assets.json"
                output = folder / "capped.json"
                char_source = "C1__v2__asset_anchor"
                sources = ["P%d__asset_anchor" % i for i in range(7)] + [char_source]
                graph = {"nodes": [{"id": "S1__candidate_image_A", "role": "candidate_image"}], "edges": [{"source": item, "target": "S1__candidate_image_A"} for item in sources]}
                plan = {"assets": [{"id": "P%d" % i, "kind": "prop"} for i in range(7)] + [{"id": character_id, "kind": "character"}]}
                source.write_text(json.dumps(graph), encoding="utf-8")
                assets.write_text(json.dumps(plan), encoding="utf-8")
                with patch.object(sys, "argv", ["cap", str(source), "--assets", str(assets), "--out", str(output)]), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cap_image_refs.main(), 0)
                edges = json.loads(output.read_text(encoding="utf-8"))["edges"]
                self.assertEqual(len(edges), 7)
                self.assertIn(char_source, [edge["source"] for edge in edges])


class MissingTransferEvidenceTests(unittest.TestCase):
    def test_missing_exact_fields_are_not_transferable(self):
        result = cross_work_transfer.score([{}], [{}])
        for field in cross_work_transfer.EXACT_FIELDS:
            self.assertEqual(result["verdicts"][field], "no_signal")
            self.assertIsNone(result["metrics"][field]["hit_rate"])
            self.assertEqual(result["metrics"][field]["hits"], 0)

    def test_missing_counts_are_not_zero_observations(self):
        result = cross_work_transfer.score([{"imageList": 0}], [{}])
        self.assertIsNone(result["metrics"]["imageList"]["mae"])
        self.assertEqual(result["verdicts"]["imageList"], "no_signal")

    def test_complete_evidence_retains_success(self):
        row = {"model": "model-A", "enableSound": False, "imageList": 0}
        result = cross_work_transfer.score([row], [row])
        self.assertEqual(result["verdicts"]["model"], "transferable")
        self.assertEqual(result["verdicts"]["enableSound"], "transferable")
        self.assertEqual(result["verdicts"]["imageList"], "transferable")


if __name__ == "__main__":
    unittest.main()
