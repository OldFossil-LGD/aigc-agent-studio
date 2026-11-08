"""Offline orchestration must propagate failures and require effective references."""
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import asset_manifest, stage_gate, studio_run


class StudioRunFailureTests(unittest.TestCase):
    def test_late_failure_blocks_and_stops_downstream_steps(self):
        for failed_step in [('production_ir.py', 'render'),
                            ('prompt_ast.py', 'build'),
                            ('workflow_graph_ir.py', 'build')]:
            with self.subTest(failed_step=failed_step), tempfile.TemporaryDirectory() as temp:
                output = Path(temp)
                (output / 'plan').mkdir()
                (output / 'plan/03_shot_graph_plan.json').write_text('{}', encoding='utf-8')
                calls = []

                def execute(script, args):
                    key = (script, args[0])
                    calls.append(key)
                    return {'script': script, 'exit': 1 if key == failed_step else 0,
                            'stdout_tail': [], 'stderr_tail': []}

                with patch.object(studio_run, '_run', side_effect=execute), \
                        contextlib.redirect_stdout(io.StringIO()):
                    code = studio_run.run(artifacts=temp, out=temp)
                report = json.loads((output / '00_run_report.json').read_text(encoding='utf-8'))
                self.assertEqual(code, 1)
                self.assertEqual(report['status'], 'BLOCK')
                self.assertTrue(report['blocked_at'])
                self.assertEqual(calls[-1], failed_step)
                self.assertEqual(report['steps'][-1]['exit'], 1)

    def test_child_output_is_utf8_even_when_parent_locale_is_legacy(self):
        env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='utf-8')
        code = (
            "import json; from scripts import studio_run; "
            "print(json.dumps(studio_run._run('prompt_ast.py', ['--self-test'])))"
        )
        result = subprocess.run(
            [sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
            env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        step = json.loads(result.stdout)
        self.assertEqual(step['exit'], 0)
        self.assertTrue(any('自检' in line for line in step['stdout_tail']))

    def test_supported_warning_codes_continue(self):
        with tempfile.TemporaryDirectory() as temp:
            def execute(script, args):
                return {'script': script, 'exit': 4 if script == 'production_ir.py' and args[0] == 'build' else 0,
                        'stdout_tail': [], 'stderr_tail': []}

            with patch.object(studio_run, '_run', side_effect=execute), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = studio_run.run(artifacts=temp, out=temp)
            self.assertEqual(code, 0)

    def test_real_script_entry_produces_offline_artifacts(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(studio_run.self_test(), 0)


class ReferenceEvidenceTests(unittest.TestCase):
    def test_manifest_rejects_missing_binding_evidence(self):
        for field in ['effective', 'node_key']:
            with self.subTest(field=field):
                doc = asset_manifest._base_doc()
                doc['shots'][0]['reference_plan']['resolved'][0].pop(field)
                self.assertFalse(asset_manifest.analyze(doc)['ok'])

    def test_manifest_requires_boolean_true_effective(self):
        for value in [None, 0, 1, 'true', 'false']:
            with self.subTest(value=value):
                doc = asset_manifest._base_doc()
                doc['shots'][0]['reference_plan']['resolved'][0]['effective'] = value
                self.assertFalse(asset_manifest.analyze(doc)['ok'])


    def test_only_explicit_true_marks_reference_effective(self):
        for value in [None, False, 0, 1, 'true', 'false']:
            with self.subTest(effective=value), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'refs').mkdir()
                row = {'shot': 's1', 'node_key': 'n1', 'effective': value}
                (root / 'refs/resolved.json').write_text(
                    json.dumps({'shots': [row]}), encoding='utf-8')
                self.assertEqual(stage_gate.run(temp, 'S5.5')[0]['status'], 'FAIL')

    def test_missing_effective_is_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'refs').mkdir()
            (root / 'refs/resolved.json').write_text(
                json.dumps({'shots': [{'shot': 's1', 'node_key': 'n1'}]}), encoding='utf-8')
            self.assertEqual(stage_gate.run(temp, 'S5.5')[0]['status'], 'FAIL')

    def test_explicit_true_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'refs').mkdir()
            (root / 'refs/resolved.json').write_text(
                json.dumps({'shots': [{'shot': 's1', 'node_key': 'n1', 'effective': True}]}),
                encoding='utf-8')
            self.assertEqual(stage_gate.run(temp, 'S5.5')[0]['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
