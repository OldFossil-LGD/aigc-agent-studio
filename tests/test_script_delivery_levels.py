import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import script_lint


class ScriptDeliveryLevelTests(unittest.TestCase):
    def document(self, level):
        required = {
            "L0": {1, 2, 4, 5, 6, 7, 8},
            "L1": {1, 2, 3, 4, 5, 6, 7, 8, 9, 11},
            "L2": set(range(1, 13)),
        }[level]
        parts = re.split(r"(?=^## M\d+ )", script_lint.GOOD, flags=re.M)
        selected = [parts[0]]
        for part in parts[1:]:
            number = int(re.match(r"## M(\d+)", part).group(1))
            if number in required:
                selected.append(part)
        text = "".join(selected)
        if level == "L0":
            text = text.replace("## M1 抬头", "本稿为 L0 可拍最小版\n\n## M1 抬头")
        return text

    def command(self, text, *arguments):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "script.md"
            source.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts/script_lint.py"), str(source), *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
            )

    def test_l1_standard_delivery_passes_with_explicit_level(self):
        result = self.command(self.document("L1"), "--level", "L1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_l0_minimum_delivery_passes_with_visible_declaration(self):
        result = self.command(self.document("L0"), "--level", "L0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_l0_requires_visible_declaration(self):
        text = self.document("L0").replace("本稿为 L0 可拍最小版", "")
        result = self.command(text, "--level", "L0")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("本稿为 L0 可拍最小版", result.stdout)

    def test_default_keeps_full_delivery_requirements(self):
        result = self.command(self.document("L1"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("M10", result.stdout)
        self.assertIn("M12", result.stdout)

    def test_explicit_l2_and_existing_function_default_still_pass(self):
        result = self.command(self.document("L2"), "--level", "L2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        fails, warns, blank, _ = script_lint.lint_full(script_lint.GOOD)
        self.assertEqual((fails, warns, blank), ([], [], []))

    def test_l1_still_requires_its_handoff_module(self):
        text = self.document("L1").replace("## M11 交接契约", "## 交接信息")
        result = self.command(text, "--level", "L1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("M11", result.stdout)

    def test_selected_optional_modules_are_validated(self):
        text = self.document("L1") + "\n## M12 诊断记录\n需要复核。\n"
        result = self.command(text, "--level", "L1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("副作用", result.stdout)

    def test_story_words_do_not_create_optional_modules(self):
        for level in ("L0", "L1"):
            with self.subTest(level=level):
                text = self.document(level).replace(
                    "## M8 剧本正文",
                    "## M8 剧本正文\n医生把诊断报告和交接契约放在桌上。",
                )
                result = self.command(text, "--level", level)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_each_level_rejects_each_missing_required_module(self):
        for level in ("L0", "L1", "L2"):
            text = self.document(level)
            numbers = re.findall(r"^## M(\d+) ", text, flags=re.M)
            for number in numbers:
                with self.subTest(level=level, module=number):
                    incomplete = re.sub(
                        r"^## M" + number + r" ",
                        "## 内容 ",
                        text,
                        count=1,
                        flags=re.M,
                    )
                    result = self.command(incomplete, "--level", level)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("M" + number, result.stdout)

    def test_l0_keeps_module_order_check(self):
        text = self.document("L0")
        text = text.replace("## M1 抬头", "## M2 抬头")
        text = text.replace("## M2 前提", "## M1 前提")
        result = self.command(text, "--level", "L0")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("模块顺序乱", result.stdout)

    def test_invalid_or_missing_level_is_usage_error(self):
        for arguments in [("--level", "L9"), ("--level",)]:
            with self.subTest(arguments=arguments):
                result = self.command(self.document("L1"), *arguments)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_body_mode_rejects_module_level_option(self):
        result = self.command(script_lint.BODY_ONLY, "--mode", "body", "--level", "L1")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
