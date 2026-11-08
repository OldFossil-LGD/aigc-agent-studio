import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import storyboard_lint

META = "```\n—— 故事板参数 ——\n风格锚点、一致性锚点、禁止项、纯灰度\n【实测回写】\n```\n"
PROMPT = "```\n输出模式：原生组图 | 平台=即梦 | 张数=1\n第1格：老人坐在窗边。\n```\n"


class StoryboardScopeTests(unittest.TestCase):
    def test_metadata_only_is_not_verified_by_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "board.md"
            source.write_text(META, encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/storyboard_lint.py"), str(source)], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertNotIn("[PASS]", result.stdout)

    def test_metadata_is_excluded_from_prompt_count(self):
        self.assertEqual(storyboard_lint.lint(META + PROMPT)[3], 1)

    def test_metadata_does_not_supply_prompt_requirements(self):
        fails, warns, notes, count = storyboard_lint.lint(META + PROMPT)
        self.assertFalse(fails)
        self.assertTrue(any("风格锚点" in message for message in warns), warns)
        self.assertTrue(any("一致性锚点" in message for message in warns), warns)
        self.assertTrue(any("纯灰度" in message for message in warns), warns)


if __name__ == "__main__":
    unittest.main()
