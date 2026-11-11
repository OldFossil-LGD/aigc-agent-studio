"""The gate sweep must fail closed on both 'script failed' and 'script missing'."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import lib_doctor


def fake(returncode, stdout=''):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr='')


class GateSweepTests(unittest.TestCase):
    def sweep(self, scripts, results, discovered=None):
        side = [results[name] for name in scripts]

        def runner(*args, **kwargs):
            return side.pop(0)

        with patch.object(lib_doctor.subprocess, 'run', side_effect=runner), \
                patch.object(lib_doctor, '_scripts_with_selftest',
                             return_value=list(scripts) if discovered is None else discovered):
            return lib_doctor._run_selftests(list(scripts))

    def test_failing_self_test_is_a_failure(self):
        fails, skipped, unregistered = self.sweep(['a.py'], {'a.py': fake(1)})
        self.assertEqual(fails, ['a.py'])
        self.assertEqual(unregistered, [])

    def test_declared_missing_tool_is_a_tracked_skip(self):
        fails, skipped, _ = self.sweep(['a.py'], {'a.py': fake(4, '{"self_test": "warn", "reason": "tool unavailable"}')})
        self.assertEqual(fails, [])
        self.assertEqual(skipped, ['a.py'])

    def test_exit_3_without_the_declaration_is_still_a_failure(self):
        fails, skipped, _ = self.sweep(['a.py'], {'a.py': fake(3, '{"reason": "something else"}')})
        self.assertEqual(fails, ['a.py'])
        self.assertEqual(skipped, [])

    def test_timeout_is_a_failure(self):
        def runner(*args, **kwargs):
            raise lib_doctor.subprocess.TimeoutExpired(cmd='x', timeout=1)
        with patch.object(lib_doctor.subprocess, 'run', side_effect=runner), \
                patch.object(lib_doctor, '_scripts_with_selftest', return_value=['a.py']):
            fails, skipped, _ = lib_doctor._run_selftests(['a.py'])
        self.assertEqual(fails, ['a.py(超时)'])

    def test_unregistered_self_test_is_reported(self):
        fails, _, unregistered = self.sweep(['a.py'], {'a.py': fake(0)}, discovered=['a.py', 'b.py'])
        self.assertEqual(fails, [])
        self.assertEqual(unregistered, ['b.py'])

    def test_exempt_script_is_not_reported_as_unregistered(self):
        _, _, unregistered = self.sweep(['a.py'], {'a.py': fake(0)},
                                        discovered=['a.py', 'lib_doctor.py'])
        self.assertEqual(unregistered, [])


if __name__ == '__main__':
    unittest.main()
