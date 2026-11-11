"""Strict mode must not keep printing WARN while returning a failure code.

Real run: --verify-only --strict-effective returned rc=1 but the line said [WARN],
so a reader of the log would think it merely warned.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import libtv_canvas_build as canvas


class MissingArtifactLabelTests(unittest.TestCase):
    def test_default_mode_says_warn(self):
        line = canvas._missing_artifact_line(['资产_甲'], False)
        self.assertIn('[WARN]', line)
        self.assertIn('资产_甲', line)
        self.assertNotIn('[FAIL]', line)

    def test_strict_mode_says_fail(self):
        line = canvas._missing_artifact_line(['资产_甲'], True)
        self.assertIn('[FAIL]', line)
        self.assertIn('资产_甲', line)
        self.assertNotIn('[WARN]', line)


if __name__ == '__main__':
    unittest.main()
