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
                 str(ROOT / 'samples/papercut_empty_shot_intent.json'), '--draft', '--out', str(output)],
                cwd=temp, env=env, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            contract = json.loads((output / '01_production_contract.json').read_text(encoding='utf-8'))
            self.assertEqual(contract['production_contract']['task_type'], 'prompt_only')
            self.assertTrue((output / '04_prompt_packages.jsonl').is_file())
            self.assertFalse((output / '05_platform_execution_plan.json').exists())
            self.assertFalse((output / '08_libtv_command_plan.json').exists())

    def test_formal_cli_and_allow_gate_fail_require_station_zero(self):
        for flags in ([], ['--allow-gate-fail']):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / 'out'
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts/compile_production.py'),
                     str(ROOT / 'samples/papercut_empty_shot_intent.json'), '--out', str(output), *flags],
                    capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 1)
                self.assertIn('GRILL_REQUIRED', result.stderr)
                self.assertFalse((output / '01_production_contract.json').exists())

    def test_draft_still_validates_a_supplied_station_zero(self):
        for script in ('compile_production.py', 'compile_intent_delivery.py'):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as temp:
                bad = Path(temp) / 'bad.json'
                bad.write_text(json.dumps({'grill_format': 'invalid', 'entries': []}), encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts' / script),
                     str(ROOT / 'samples/papercut_empty_shot_intent.json'), '--out', str(Path(temp) / 'out'),
                     '--draft', '--grill', str(bad)], capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 1)
                self.assertIn('GRILL_INVALID', result.stderr)


if __name__ == '__main__':
    unittest.main()
