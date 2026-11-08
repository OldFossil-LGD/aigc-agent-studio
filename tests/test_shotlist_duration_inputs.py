import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import shotlist_lint

ROOT = Path(__file__).resolve().parents[1]


class ShotlistDurationTests(unittest.TestCase):
    def test_parser_preserves_duration_sign(self):
        self.assertEqual(shotlist_lint._to_float("-2.0s"), -2.0)
        self.assertEqual(shotlist_lint._to_float("+2.0秒"), 2.0)

    def test_nonpositive_durations_fail_real_cli_without_traceback(self):
        for durations in [("0", "0"), ("-2.0s", "6"), ("-2.0s", "-6秒")]:
            with self.subTest(durations=durations), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "shots.md"
                text = "| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |\n|---|---|---|---|---|\n| 镜1 | 大远景 | %s | 建立 | FIRST |\n| 镜2 | 大特写 | %s | 收束 | SECOND |\n" % durations
                source.write_text(text, encoding="utf-8")
                result = subprocess.run([sys.executable, str(ROOT / "scripts/shotlist_lint.py"), str(source)], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("[FAIL]", result.stdout)
                self.assertNotIn("[PASS]", result.stdout)


if __name__ == "__main__":
    unittest.main()
