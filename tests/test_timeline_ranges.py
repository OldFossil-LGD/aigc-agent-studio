import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audit_prompt


class TimelineRangeTests(unittest.TestCase):
    def run_timeline(self, ranges):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "shots.md"
            source.write_text("\n".join(
                "| 镜%d | %s |" % (index, time_range)
                for index, time_range in enumerate(ranges, 1)
            ), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts/audit_prompt.py"), "timeline", str(source)],
                capture_output=True, text=True, encoding="utf-8",
                env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
            )

    def test_clock_ranges_preserve_minutes_and_seconds(self):
        for text, expected in [
            ("00:00-00:04", (0, 4)),
            ("00:59–01:03", (59, 63)),
        ]:
            with self.subTest(text=text):
                self.assertEqual(audit_prompt._first_range(text)[:2], expected)

    def test_first_range_uses_leftmost_complete_interval(self):
        for text in ["0–4（参考00:59–01:03）", "00:00–00:04（参考5–9）"]:
            with self.subTest(text=text):
                self.assertEqual(audit_prompt._first_range(text)[:2], (0, 4))

    def test_clock_cli_reports_actual_total(self):
        result = self.run_timeline(["00:00–00:04", "00:04–00:08"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0.0 → 8.0 秒", result.stdout)

    def test_clock_gaps_and_overlaps_fail(self):
        for second in ["00:05–00:08", "00:03–00:08"]:
            with self.subTest(second=second):
                result = self.run_timeline(["00:00–00:04", second])
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_zero_and_backward_ranges_fail(self):
        for ranges in [["0-0"], ["0-4", "4-3"]]:
            with self.subTest(ranges=ranges):
                result = self.run_timeline(ranges)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("[PASS]", result.stdout)

    def test_negative_and_nonfinite_values_fail(self):
        for text in ["0--1", "-1-4", "0-" + "9" * 400]:
            with self.subTest(text=text):
                result = self.run_timeline([text])
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_legacy_numeric_syntax_remains_supported(self):
        for text in ["0-5", "0.0–5.0s", "0到5秒", "0至5", "+0~+5", "0—5"]:
            with self.subTest(text=text):
                result = self.run_timeline([text])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("0.0 → 5.0 秒", result.stdout)

    def test_partial_scan_does_not_report_pass(self):
        result = self.run_timeline(["0-4", "时间待定"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        empty = self.run_timeline(["时间待定"])
        self.assertEqual(empty.returncode, 3, empty.stdout + empty.stderr)

    def test_invalid_clock_does_not_fall_back_to_partial_numbers(self):
        for text in ["00:61-00:64", "00:00-00:04.5", "00:00:00-00:00:04", "-00:00-00:04"]:
            with self.subTest(text=text):
                result = self.run_timeline([text])
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
