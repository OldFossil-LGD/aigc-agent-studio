"""Compiler script and module entrypoints accept the same intent handoff."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductionCLITests(unittest.TestCase):
    def test_direct_script_accepts_intent_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'out'
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            env.pop('PYTHONPATH', None)
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/compile_production.py'),
                 str(ROOT / 'samples/papercut_empty_shot_intent.json'), '--out', str(output)],
                cwd=temp, env=env, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            contract = json.loads((output / '01_production_contract.json').read_text(encoding='utf-8'))
            self.assertEqual(contract['production_contract']['task_type'], 'prompt_only')
            self.assertTrue((output / '04_prompt_packages.jsonl').is_file())
            self.assertFalse((output / '05_platform_execution_plan.json').exists())
            self.assertFalse((output / '08_libtv_command_plan.json').exists())


if __name__ == '__main__':
    unittest.main()
