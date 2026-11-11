"""Guards added after the pre-commit audit (2026-11-12).

Each case below failed in a way that produced a wrong verdict or lost data:
fail-open schema validation, in-place session overwrite, export paths that
clobber each other, an incomplete immutable-revision check, and detection
failures that read as "nothing found".
"""
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import film_qc_gate as qc
import grill_session as session_mod
import work_units


class ContractTargetTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / 'x.contract.json'

    def tearDown(self):
        self.dir.cleanup()

    def test_new_path_is_used_as_is(self):
        target, conflict = session_mod.resolve_contract_target(self.path, {'revision': 1})
        self.assertEqual(target, self.path)
        self.assertIsNone(conflict)

    def test_same_revision_same_content_is_idempotent(self):
        self.path.write_text(json.dumps({'revision': 1, 'a': 1}), encoding='utf-8')
        target, conflict = session_mod.resolve_contract_target(self.path, {'revision': 1, 'a': 1})
        self.assertIsNone(conflict)

    def test_same_revision_different_content_is_refused(self):
        self.path.write_text(json.dumps({'revision': 1, 'a': 1}), encoding='utf-8')
        _, conflict = session_mod.resolve_contract_target(self.path, {'revision': 1, 'a': 2})
        self.assertIsNotNone(conflict)

    def test_existing_suffixed_target_is_refused(self):
        self.path.write_text(json.dumps({'revision': 1}), encoding='utf-8')
        (Path(self.dir.name) / 'x.contract.r2.json').write_text('{}', encoding='utf-8')
        _, conflict = session_mod.resolve_contract_target(self.path, {'revision': 2})
        self.assertIsNotNone(conflict)


class SaveSessionTests(unittest.TestCase):
    def test_write_is_complete_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 's.json'
            session_mod.save_session(target, {'a': 1})
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'a': 1})
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.endswith('.tmp')]
            self.assertEqual(leftovers, [])

    def test_start_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / 's.json')
            first = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                                    'start', '--out', out, '--request', 'r'],
                                   cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            second = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                                     'start', '--out', out, '--request', 'r'],
                                    cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(first.returncode, 0)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn('SESSION_EXISTS', second.stdout)


class TempAndLedgerCollisionTests(unittest.TestCase):
    def test_save_session_uses_an_unpredictable_temp_name(self):
        # 只看"事后没有 .tmp"证明不了什么——旧实现成功时也不会留下它。
        # 这里拦住 os.replace，直接看写入时用的临时名。
        seen = []
        real_replace = session_mod.os.replace

        def spy(src, dst):
            seen.append(Path(src).name)
            return real_replace(src, dst)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 's.json'
            with unittest.mock.patch.object(session_mod.os, 'replace', side_effect=spy):
                session_mod.save_session(target, {'a': 1})
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], 's.json.tmp')
        self.assertTrue(seen[0].startswith('s.json.'))
        self.assertGreater(len(seen[0]), len('s.json.tmp'))

    def test_identical_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 's.json'
            contract = str(Path(tmp) / 'c.json')
            subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                            'start', '--out', str(out), '--request', 'r'],
                           cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                                   'finish', '--session', str(out),
                                   '--contract', contract, '--ledger', contract, '--json'],
                                  cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            self.assertIn('EXPORT_PATH_COLLISION', done.stdout + done.stderr)

    def test_ledger_cannot_land_on_a_published_contract_after_renaming(self):
        # 已有 c.json 的旧修订 → 新修订会被改名到 c.r<N>.json，三路径因此互不相同；
        # 若不额外拦，台账会把 c.json（旧修订）覆盖掉。
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 's.json'
            contract = Path(tmp) / 'c.json'
            contract.write_text(json.dumps({'revision': 999, 'decisions': []}), encoding='utf-8')
            subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                            'start', '--out', str(out), '--request', 'r'],
                           cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                                   'finish', '--session', str(out),
                                   '--contract', str(contract), '--ledger', str(contract),
                                   '--json'],
                                  cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            self.assertIn('LEDGER_CONFLICT', done.stdout + done.stderr)
            self.assertEqual(json.loads(contract.read_text(encoding='utf-8'))['revision'], 999)


class HardlinkAliasTests(unittest.TestCase):
    def test_same_file_detects_a_hardlink_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / 'a.json'
            left.write_text('{}', encoding='utf-8')
            right = Path(tmp) / 'b.json'
            try:
                import os
                os.link(left, right)
            except (OSError, AttributeError, NotImplementedError):
                self.skipTest('该文件系统不支持硬链接')
            self.assertFalse(str(left) == str(right))
            self.assertTrue(session_mod.same_file(left, right))

    def test_ledger_cannot_alias_the_contract_through_a_hardlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 's.json'
            contract = Path(tmp) / 'c.json'
            ledger = Path(tmp) / 'l.json'
            contract.write_text(json.dumps({'revision': 999, 'decisions': []}), encoding='utf-8')
            try:
                import os
                os.link(contract, ledger)
            except (OSError, AttributeError, NotImplementedError):
                self.skipTest('该文件系统不支持硬链接')
            subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                            'start', '--out', str(out), '--request', 'r'],
                           cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'grill_session.py'),
                                   'finish', '--session', str(out),
                                   '--contract', str(contract), '--ledger', str(ledger), '--json'],
                                  cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
            self.assertIn('LEDGER_CONFLICT', done.stdout + done.stderr)
            self.assertEqual(json.loads(contract.read_text(encoding='utf-8'))['revision'], 999)


class DetectionFailureTests(unittest.TestCase):
    def test_unreadable_media_reports_a_problem_not_an_empty_result(self):
        rows, problem = qc.black_segments('C:/definitely-not-a-video.mp4')
        self.assertEqual(rows, [])
        self.assertIsNotNone(problem, 'detection failure must not look like "no black frames"')

    def test_hard_cuts_returns_none_when_detection_fails(self):
        self.assertIsNone(qc.hard_cuts('C:/definitely-not-a-video.mp4'))


class CliResultTests(unittest.TestCase):
    def test_run_cli_uses_the_result_object(self):
        code, payload, raw = work_units.run_cli(sys.executable,
                                                ['-c', 'import json;print(json.dumps({"ok": 1}))'])
        self.assertEqual(code, 0)
        self.assertEqual(payload, {'ok': 1})


if __name__ == '__main__':
    unittest.main()
