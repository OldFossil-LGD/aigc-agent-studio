"""A broken health check must never read as a clean result."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import lib_doctor

PATTERN = r"悬空指针（引用了不存在的册）===+\s*\n\s*([^\n]+)"


class HealthSubcheckTests(unittest.TestCase):
    def run_with(self, returncode, stdout):
        fake = SimpleNamespace(returncode=returncode, stdout=stdout, stderr='')
        with patch.object(lib_doctor.subprocess, 'run', return_value=fake):
            return lib_doctor._health_subcheck('dangling', PATTERN)

    def test_crash_is_an_infrastructure_failure(self):
        self.assertEqual(self.run_with(7, '')['status'], 'BROKEN')

    def test_empty_output_is_not_a_pass(self):
        self.assertEqual(self.run_with(0, '')['status'], 'BROKEN')

    def test_changed_output_format_is_not_a_pass(self):
        self.assertEqual(self.run_with(0, '=== 悬空指针（新格式）===\n  无\n')['status'], 'BROKEN')

    def test_clean_looking_output_with_bad_exit_code_is_not_a_pass(self):
        result = self.run_with(3, '=== 悬空指针（引用了不存在的册）===\n  无\n')
        self.assertEqual(result['status'], 'BROKEN')

    def test_reported_problem_is_found(self):
        result = self.run_with(1, '=== 悬空指针（引用了不存在的册）===\n  a.md -> b.md\n')
        self.assertEqual(result['status'], 'FOUND')
        self.assertIn('a.md', result['detail'])


class DoctorIntegrationTests(unittest.TestCase):
    def test_broken_health_check_makes_the_doctor_fail(self):
        broken = {'status': 'BROKEN', 'detail': 'injected failure'}
        # 自检扫描本身由 test_gate_sweep 的 6 个用例覆盖；这里只验证"子检查坏了
        # 会不会让整体判红"，跑整套自检只会把回归时间拉长而不增加证明力。
        with patch.object(lib_doctor, '_health_subcheck', return_value=broken), \
                patch.object(lib_doctor, '_run_selftests', return_value=([], [], [])), \
                redirect_stdout(io.StringIO()):
            bad, _ = lib_doctor.doctor()
        self.assertGreater(bad, 0)


if __name__ == '__main__':
    unittest.main()
