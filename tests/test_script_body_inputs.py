import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import script_lint


class ScriptBodyInputTests(unittest.TestCase):
    def command(self, text):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "body.md"
            source.write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, str(ROOT / "scripts/script_lint.py"), str(source), "--mode", "body"], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))

    def test_no_scene_body_returns_not_verified(self):
        result = self.command("# 剧本正文\n老人放下杯子。\n")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("没扫到场景标题", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_empty_body_preserves_four_part_result(self):
        fails, warns, blank, infos = script_lint.lint_body("")
        self.assertEqual((fails, warns, infos), ([], [], []))
        self.assertTrue(blank)

    def test_valid_standalone_body_still_passes(self):
        result = self.command(script_lint.BODY_ONLY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
