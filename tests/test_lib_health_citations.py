"""Regression: the orphan check must read `references/x.md` citations."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import lib_health


class CitationRecognitionTests(unittest.TestCase):
    def test_references_prefix_is_a_citation(self):
        found = lib_health.CITATION_RE.findall('最后执行 `references/final-delivery-audit.md` 的逐项审阅')
        self.assertEqual(['final-delivery-audit.md'], found)

    def test_bare_backticked_name_is_a_citation(self):
        self.assertEqual(['run-sheet.md'], lib_health.CITATION_RE.findall('`run-sheet.md`'))

    def test_plain_text_mention_is_not_a_citation(self):
        self.assertEqual([], lib_health.CITATION_RE.findall('见 references/run-sheet.md 一节'))

    def test_other_paths_are_not_citations(self):
        self.assertEqual([], lib_health.CITATION_RE.findall('`docs/run-sheet.md`'))


if __name__ == '__main__':
    unittest.main()
