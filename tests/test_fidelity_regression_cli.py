"""Exercise the previously broken standalone fidelity entry point."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

class FidelityCLIRegressionTests(unittest.TestCase):
    def test_public_synthetic_manifest_executes_all_cases(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'evals/fidelity/manifest.json').read_text(encoding='utf-8'))
        result = subprocess.run([sys.executable, '-B', str(root / 'scripts/fidelity_regression.py')], cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['status'], 'PASS')
        self.assertFalse(receipt['failed'])
        self.assertEqual(sum(name.startswith('fixture:') for name, passed in receipt['cases']), len(manifest['cases']))
        self.assertTrue(all(passed for name, passed in receipt['cases']))

if __name__ == '__main__':
    unittest.main()
