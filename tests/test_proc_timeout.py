"""A hung external process must become a failure, not an unbounded wait."""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import proc

SLEEP = [sys.executable, '-c', 'import time; time.sleep(5)']


class ProcTimeoutTests(unittest.TestCase):
    def test_timeout_returns_a_failed_result_quickly(self):
        started = time.time()
        result = proc.run(SLEEP, capture_output=True, text=True, timeout=1)
        elapsed = time.time() - started
        self.assertEqual(result.returncode, proc.TIMEOUT_RC)
        self.assertLess(elapsed, 2.5, 'timeout took too long to surface')
        self.assertIn('timed out', result.stderr)

    def test_text_mode_returns_text(self):
        result = proc.run(SLEEP, capture_output=True, text=True, timeout=1)
        self.assertIsInstance(result.stdout, str)
        self.assertIsInstance(result.stderr, str)

    def test_byte_mode_returns_bytes(self):
        result = proc.run(SLEEP, capture_output=True, timeout=1)
        self.assertIsInstance(result.stdout, bytes)
        self.assertIsInstance(result.stderr, bytes)

    def test_normal_run_is_unchanged(self):
        result = proc.run([sys.executable, '-c', 'print("ok")'],
                          capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_nonzero_exit_is_passed_through(self):
        result = proc.run([sys.executable, '-c', 'raise SystemExit(3)'], timeout=30)
        self.assertEqual(result.returncode, 3)


if __name__ == '__main__':
    unittest.main()
