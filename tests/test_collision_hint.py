"""A hash-suffixed planned name usually means collision renaming, not a missing node.

build_binding_map renames ALL colliding names (no first-come winner), so adding one
duplicate asset renames the node that was already built. The plain "missing node"
message left users guessing; the hint names the cause.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import libtv_canvas_build as canvas


class CollisionHintTests(unittest.TestCase):
    def test_plain_missing_names_get_no_hint(self):
        self.assertEqual(canvas._collision_hint(['资产_道具一_detail']), '')

    def test_suffixed_names_get_the_cause(self):
        hint = canvas._collision_hint(['资产_道具一_detail_b62a4d'])
        self.assertIn('同名', hint)
        self.assertIn('资产_道具一_detail_b62a4d', hint)

    def test_mixed_names_still_explain_the_suffixed_ones(self):
        hint = canvas._collision_hint(['资产_甲', '资产_乙_842f4a'])
        self.assertIn('资产_乙_842f4a', hint)
        self.assertNotIn('资产_甲', hint)


if __name__ == '__main__':
    unittest.main()
