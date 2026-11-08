"""The reverse-pipeline CLI must preserve production and source gate failures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReversePipelineStatusTests(unittest.TestCase):
    def execute(self, description, flags=()):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            data = {'goal': 'Synthetic pipeline status test', 'duration_sec': 5,
                    'entities': [{'id': 'hero', 'kind': 'character', 'description': description}],
                    'shots': [{'id': 's1', 'duration_sec': 5, 'description': 'A person waits'}],
                    'delivery': {'ignition_allowed': False}}
            source = base / 'input.json'
            source.write_text(json.dumps(data), encoding='utf-8')
            output = base / 'out'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/reverse_pipeline.py'),
                str(source), '--out', str(output)] + list(flags), cwd=temp,
                env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1'),
                capture_output=True, text=True, encoding='utf-8')
            summary = json.loads((output / '13_reverse_pipeline_summary.json').read_text(encoding='utf-8'))
            gate = json.loads((output / '06_gate_results.json').read_text(encoding='utf-8'))
            return result, summary, gate

    def test_production_failure_cannot_be_reported_as_pipeline_pass(self):
        result, summary, gate = self.execute(None)
        self.assertEqual(gate['status'], 'FAIL')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(summary['status'], 'FAIL')
        self.assertEqual(summary.get('production_gate'), gate)

    def test_explicit_allow_fail_preserves_failure_in_summary(self):
        result, summary, gate = self.execute(None, ['--allow-gate-fail'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(summary['status'], 'FAIL')
        self.assertEqual(summary.get('production_gate'), gate)

    def test_valid_production_can_still_pass(self):
        result, summary, gate = self.execute('Blue-coated adult')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(summary['status'], 'PASS')
        self.assertEqual(summary.get('production_gate'), gate)

    def test_partial_source_gate_arguments_are_rejected(self):
        result, summary, gate = self.execute('Blue-coated adult', ['--source', 'source.json'])
        self.assertEqual(gate['status'], 'PASS')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(summary['status'], 'FAIL')
        self.assertEqual(summary['source_gate']['failures'][0]['code'], 'SOURCE_ARGS_INCOMPLETE')

if __name__ == '__main__':
    unittest.main()
