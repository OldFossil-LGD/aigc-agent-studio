import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import source_fidelity_lint

ROOT = Path(__file__).resolve().parents[1]


def graph_pair(count=3):
    source = {"nodes": [{"id": "s%d" % i, "type": "image"} for i in range(count)], "edges": [{"source": "s%d" % i, "target": "s%d" % (i + 1)} for i in range(count - 1)]}
    plan = {"nodes": [{"id": "p%d" % i, "node_type": "image", "source_node_id": "s%d" % i} for i in range(count)], "edges": [{"source": "p%d" % i, "target": "p%d" % (i + 1)} for i in range(count - 1)]}
    return source, plan


class MirrorTopologyTests(unittest.TestCase):
    def test_rewired_chain_fails_actual_cli(self):
        source, plan = graph_pair()
        plan["edges"] = [{"source": "p0", "target": "p2"}, {"source": "p2", "target": "p1"}]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            a, b = folder / "source.json", folder / "plan.json"
            a.write_text(json.dumps(source), encoding="utf-8")
            b.write_text(json.dumps(plan), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/source_fidelity_lint.py"), "--source", str(a), "--plan", str(b), "--mode", "copy_reverse"], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertIn("FIDELITY_EDGE_TOPOLOGY", [row["code"] for row in report["failures"]])

    def test_renamed_identical_mirror_passes(self):
        source, plan = graph_pair()
        self.assertEqual(source_fidelity_lint.evaluate(source, plan)["status"], "PASS")

    def test_duplicate_lineage_fails_even_with_count_band_room(self):
        source, plan = graph_pair(20)
        plan["nodes"].append({"id": "duplicate", "type": "image", "source_node_id": "s0"})
        report = source_fidelity_lint.evaluate(source, plan)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("FIDELITY_DUPLICATE_LINEAGE", [row["code"] for row in report["failures"]])

    def test_parallel_edge_multiplicity_is_checked(self):
        source, plan = graph_pair()
        source["edges"].append(copy.deepcopy(source["edges"][0]))
        plan["edges"].append(copy.deepcopy(plan["edges"][1]))
        self.assertEqual(source_fidelity_lint.evaluate(source, plan)["status"], "FAIL")

    def test_existing_edge_coverage_threshold_remains_effective(self):
        source, plan = graph_pair(21)
        plan["edges"].pop()
        self.assertEqual(source_fidelity_lint.evaluate(source, plan)["status"], "PASS")
        self.assertEqual(source_fidelity_lint.evaluate(source, plan, min_edge_ratio=1.0)["status"], "FAIL")

    def test_production_plan_can_restructure_without_mirror_claim(self):
        source, plan = graph_pair()
        plan["edges"] = [{"source": "p0", "target": "p2"}, {"source": "p2", "target": "p1"}]
        self.assertEqual(source_fidelity_lint.evaluate(source, plan, mode="production_build", deliverable="production_plan")["status"], "PASS")


    def test_legacy_stats_without_duplicate_field_remain_supported(self):
        source, plan = graph_pair()
        source_stats = source_fidelity_lint.graph_stats(source)
        plan_stats = source_fidelity_lint.graph_stats(plan)
        source_stats.pop("duplicate_lineage_ids", None)
        plan_stats.pop("duplicate_lineage_ids", None)
        failures, report = source_fidelity_lint.lineage_failures(source_stats, plan_stats)
        self.assertEqual(failures, [])
        self.assertEqual(report["coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
