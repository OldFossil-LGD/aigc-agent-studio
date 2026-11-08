import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import constraint_semantics
import offline_package_lint


class EnglishConstraintTests(unittest.TestCase):
    def test_english_prohibitions_honour_forbidden_concept(self):
        for text in ["No narration.", "Do not use narration.", "Never use narration.", "Without narration.", "NOT narration."]:
            with self.subTest(text=text):
                self.assertTrue(constraint_semantics.evaluate_constraint(text, {"forbidden": ["narration"]})["ok"])

    def test_negated_overhead_does_not_satisfy_requirement(self):
        for text in ["Do not use overhead.", "No overhead.", "Must not use overhead."]:
            with self.subTest(text=text):
                self.assertFalse(constraint_semantics.evaluate_constraint(text, {"required_all": ["overhead"]})["ok"])

    def test_word_boundary_and_sentence_boundary(self):
        for text in ["Piano narration.", "No music. Narration begins."]:
            with self.subTest(text=text):
                self.assertFalse(constraint_semantics.evaluate_constraint(text, {"forbidden": ["narration"]})["ok"])

    def test_chinese_whitespace_and_english_synonyms(self):
        self.assertTrue(constraint_semantics.evaluate_constraint("正 上 方 俯 视", {"required_all": ["overhead"]})["ok"])
        self.assertTrue(constraint_semantics.evaluate_constraint("Top down camera.", {"required_all": ["俯拍"]})["ok"])


class OfflinePackageStatusTests(unittest.TestCase):
    def test_missing_directory_is_usage_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(offline_package_lint.main([str(Path(__file__).parent / "directory-that-does-not-exist")]), 2)

    def test_nonpassing_status_is_preserved(self):
        for rc in [1, 2, 3, 4]:
            with self.subTest(rc=rc), patch.object(offline_package_lint, "lint", return_value=[{"name": "child", "rc": rc, "detail": "evidence"}]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(offline_package_lint.main(["package"]), rc)

    def test_not_applicable_with_pass_is_allowed(self):
        rows = [{"name": "child", "rc": rc, "detail": "evidence"} for rc in [0, 5]]
        with patch.object(offline_package_lint, "lint", return_value=rows), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(offline_package_lint.main(["package"]), 0)


if __name__ == "__main__":
    unittest.main()
