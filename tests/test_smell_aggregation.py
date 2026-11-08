import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ai_smell_check


class SmellAggregationTests(unittest.TestCase):
    def scan(self, second):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "clean.md").write_text("```\n老人坐在窗边。\n```\n", encoding="utf-8")
            (folder / "second.md").write_text(second, encoding="utf-8")
            return subprocess.run([sys.executable, str(ROOT / "scripts/ai_smell_check.py"), str(folder)], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))

    def test_mixed_missing_blocks_is_incomplete(self):
        result = self.scan("# No prompt blocks")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertNotIn("全部 PASS", result.stdout)

    def test_all_clean_files_still_pass(self):
        result = self.scan("```\n雨点落在屋檐。\n```\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_detected_hits_keep_existing_exit_code(self):
        result = self.scan("```\n电影感构图。\n```\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_clean_file_does_not_mask_read_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "clean.md"
            source.write_text("```\n雨点落在屋檐。\n```\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                code = ai_smell_check.report([str(source), str(Path(temp) / "missing.md")])
            self.assertEqual(code, 2)
            self.assertNotIn("全部 PASS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
